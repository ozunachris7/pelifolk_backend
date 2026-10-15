from datetime import datetime
from sqlalchemy import select
from src.core.models import RoleModel,RolePermissionModel,EventModel
from tests.conftest import login
from tests.test_animals import animal
from tests.test_weanings import wean


def history(client,h,a,**params):
    return client.get('/api/v1/animals/'+a['id']+'/timeline',headers=h,params=params)


def test_timeline_dates_permissions_and_no_double_weaning(api):
    client,factory=api;h=login(client)
    a=animal(client,h,name='Estrella',birth_date='2024-01-01')
    w=wean(client,h,a);assert w.status_code==201
    assert client.post('/api/v1/health/observations',headers=h,json={'animal_id':a['id'],'date':'2024-02-01','observation':'Observación privada'}).status_code==201
    assert client.post('/api/v1/animals/'+a['id']+'/decisions',headers=h,json={'date':'2024-03-02','kind':'retain_breeding','reason':'Conservar'}).status_code==201
    r=history(client,h,a,date_to='2024-03-02',limit=2);assert r.status_code==200,r.text
    data=r.json();assert data['total']==4 and len(data['items'])==2
    assert data['items'][0]['title']=='Decisión registrada' and data['items'][1]['title']=='Destete'
    assert data['items'][1]['notes']=='Destete registrado.'
    assert {'label':'Edad al registrar','value':'60 días'} in data['items'][1]['details']
    assert data['items'][1]['recorded_by']
    second=history(client,h,a,date_to='2024-03-02',offset=2,limit=2).json()
    assert second['items'][0]['title']=='Observación'
    assert history(client,h,a,module='weights').json()['total']==1
    assert history(client,h,a,date_from='2024-03-01',date_to='2024-03-01').json()['total']==1
    worker=login(client,'worker@example.com')
    assert history(client,worker,a).status_code==403
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'))
        db.add(RolePermissionModel(role_id=role.id,permission='animals:read'))
    restricted=history(client,worker,a).json()
    assert restricted['modules']==['animals'] and 'Observación privada' not in str(restricted)
    assert {i['kind'] for i in restricted['items']}=={'birth_date','registration','decision'}
    assert history(client,worker,a,module='health').status_code==403
    assert history(client,h,a,date_from='2024-04-01',date_to='2024-01-01').status_code==422
    assert history(client,h,a,limit=101).status_code==422
    assert history(client,h,a,module='bad').status_code==422
    assert client.get('/api/v1/animals/'+a['id']+'/timeline').status_code==401
    assert client.get('/api/v1/animals/00000000-0000-4000-8000-000000000099/timeline',headers=h).status_code==404


def test_timeline_case_followups_and_replaced_events(api):
    client,factory=api;h=login(client);a=animal(client,h,name='Luna',birth_date='2020-01-01')
    c=client.post('/api/v1/health/cases',headers=h,json={'animal_id':a['id'],'start_date':'2024-02-01','reason':'Caso registrado'});assert c.status_code==201,c.text
    c=c.json()
    d=client.post('/api/v1/health/cases/'+c['id']+'/diagnoses',headers=h,json={'date':'2024-02-02','diagnosis':'Diagnóstico registrado','severity':'mild'});assert d.status_code==201,d.text
    f=client.post('/api/v1/health/cases/'+c['id']+'/followups',headers=h,json={'date':'2024-02-03','evolution':'improved','notes':'Mejoría registrada','next_review_date':'2024-02-05'});assert f.status_code==201,f.text
    # A recorded status transition belongs to the audit date, not a guessed clinical timestamp.
    assert client.patch('/api/v1/health/cases/'+c['id']+'/status',headers=h,json={'expected_status':'open','status':'closed','closed_date':'2024-02-03'}).status_code==200
    items=history(client,h,a,module='health').json()['items']
    assert {i['kind'] for i in items}=={'case_open','case_change','followup','event'}
    assert next(i for i in items if i['kind']=='case_open')['recorded_by']
    with factory.begin() as db:
        replacement=EventModel(animal_id=a['id'],event_type_id=1,date=datetime(2024,2,4),user_id=db.get(EventModel,d.json()['id']).user_id,role_id=db.get(EventModel,d.json()['id']).role_id,replaced_event_id=d.json()['id'])
        db.add(replacement)
    # Replacement has no observation subtype: filter to diagnosis day to verify the obsolete record is absent.
    assert history(client,h,a,module='health',date_from='2024-02-02',date_to='2024-02-02').json()['total']==0


def test_timeline_group_context_finance_and_sale_are_not_duplicated(api):
    from tests.test_feeding import feed_setup
    from tests.test_allocations import expense
    from tests.test_finance import category
    client,factory=api;h=login(client);a=animal(client,h,birth_date='2020-01-01');b=animal(client,h,name='Otra',birth_date='2020-01-01')
    g=client.post('/api/v1/groups',headers=h,json={'name':'Crecimiento'}).json()
    assert client.post('/api/v1/groups/'+g['id']+'/assignments',headers=h,json={'animal_ids':[a['id'],b['id']],'effective_date':'2024-01-01'}).status_code==201
    feed=feed_setup(client,factory,h)
    assert client.post('/api/v1/feeding/feeds/'+feed['id']+'/prices',headers=h,json={'effective_from':'2024-01-01','unit_cost':'10'}).status_code==201
    for day in ('2024-02-01','2024-04-01'):
        assert client.post('/api/v1/feeding/consumptions',headers=h,json={'group_id':g['id'],'feed_id':feed['id'],'date':day,'quantity':'5'}).status_code==201
    assert client.post('/api/v1/groups/'+g['id']+'/animals/'+a['id']+'/remove',headers=h,json={'effective_date':'2024-03-01'}).status_code==200
    rows=history(client,h,a,module='feeding').json();assert rows['total']==1
    assert rows['items'][0]['title']=='Alimentación del lote' and 'no es una cantidad individual' in rows['items'][0]['notes']
    assert {'label':'Cantidad del lote completo','value':'5.00 kg'} in rows['items'][0]['details']
    assert history(client,h,a,module='groups').json()['total']==2
    case=client.post('/api/v1/health/cases',headers=h,json={'animal_id':a['id'],'start_date':'2024-06-01','reason':'Caso'}).json()
    e,_=expense(client,h)
    assert client.put('/api/v1/finance/expenses/'+e['id']+'/allocations',headers=h,json={'allocations':[{'kind':'animal','target_id':a['id'],'percentage':'50'},{'kind':'health_case','target_id':case['id'],'percentage':'50'}]}).status_code==200
    sale=client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'exit_type':'sale','date':'2024-07-01','reason':'Venta'}).json()
    cat=category(client,h,'income','Venta')
    assert client.post('/api/v1/finance/incomes',headers=h,json={'category_id':cat['id'],'date':'2024-07-02','amount':'1000','exit_event_id':sale['id']}).status_code==201
    financial=history(client,h,a,module='finance').json();assert financial['total']==2
    assert next(i for i in financial['items'] if i['kind']=='expense')['details'][0]['value']=='100.00'
    # Finance-only users may see attributed costs without gaining clinical details or exit reasons.
    worker=login(client,'worker@example.com')
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'))
        db.add_all([RolePermissionModel(role_id=role.id,permission=p) for p in ('animals:read','finance:read')])
    restricted=history(client,worker,a).json()
    assert len([i for i in restricted['items'] if i['module']=='finance'])==2
    assert not any(i['module'] in ('health','exits','groups','feeding') for i in restricted['items'])


def test_timeline_reproductive_roles_birth_and_prescribed_treatment(api):
    client,factory=api;h=login(client)
    female=animal(client,h,name='Luna',birth_date='2020-01-01');male=animal(client,h,name='Trueno',sex='male',birth_date='2020-01-01')
    assert client.post('/api/v1/breeding/matings',headers=h,json={'animal_id':female['id'],'male_id':male['id'],'date':'2024-01-01'}).status_code==201
    assert client.post('/api/v1/breeding/pregnancy-diagnoses',headers=h,json={'animal_id':female['id'],'date':'2024-02-01','result':'pregnant'}).status_code==201
    birth=client.post('/api/v1/breeding/births',headers=h,json={'animal_id':female['id'],'father_id':male['id'],'date':'2024-06-01','birth_type_id':1,'offspring':[{'name':'Estrella','sex':'female','birth_weight_kg':'3.2'}]}).json()
    child=birth['offspring'][0]['animal']
    assert history(client,h,female,module='breeding').json()['total']==3
    paternal=history(client,h,male,module='breeding').json();assert paternal['total']==2
    assert any(i['title']=='Parto con descendencia' for i in paternal['items'])
    own_birth=history(client,h,child,module='animals').json()['items']
    assert {'label':'Peso al nacer (kg)','value':'3.20'} in next(i for i in own_birth if i['kind']=='birth_date')['details']
    product=client.post('/api/v1/health/products',headers=h,json={'name':'Producto registrado','product_type_id':1,'unit_id':1,'withdrawal_days':5}).json()
    case=client.post('/api/v1/health/cases',headers=h,json={'animal_id':child['id'],'start_date':'2024-06-02','reason':'Caso registrado'}).json()
    treatment=client.post('/api/v1/health/cases/'+case['id']+'/treatments',headers=h,json={'product_id':product['id'],'start_date':'2024-06-02','dose_value':'1','dose_unit_id':1,'route_id':1,'duration_days':2})
    assert treatment.status_code==201,treatment.text
    row=next(i for i in history(client,h,child,module='health').json()['items'] if i['title']=='Tratamiento registrado')
    assert {'label':'Dosis indicada','value':'1.000 ml'} in row['details']
