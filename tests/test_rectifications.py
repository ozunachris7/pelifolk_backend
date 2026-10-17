from decimal import Decimal
from sqlalchemy import select,func
from src.core.models import EventModel,EventWeightModel,HistoryRectificationModel,AuditModel,RoleModel,RolePermissionModel
from tests.conftest import login
from tests.test_animals import animal
from tests.test_health import create_case


def entries(client,h,a):return client.get('/api/v1/animals/'+a['id']+'/timeline',headers=h).json()['items']
def entry(client,h,a,title):return next(i for i in entries(client,h,a) if i['title']==title)
def context(client,h,a,e):return client.get('/api/v1/animals/'+a['id']+'/rectifications',headers=h,params={'entry_id':e['id']})
def save(client,h,a,e,c,**values):
    return client.post('/api/v1/animals/'+a['id']+'/rectifications',headers=h,json={
        'entry_id':e['id'],'expected_version':c['version'],'snapshot_token':c['snapshot_token'],
        'reason':'Se verifica un error de transcripción en el registro original.',**values})


def test_weight_replacement_preserves_original_and_updates_effective_reports(api):
    client,factory=api;h=login(client);a=animal(client,h,birth_date='2020-01-01')
    old=client.post('/api/v1/weights',headers=h,json={'animal_id':a['id'],'date':'2024-01-01','weight_kg':'25'}).json()
    e=entry(client,h,a,'Pesaje');c=context(client,h,a,e).json()
    assert c['replacement_mode']=='weight'
    r=save(client,h,a,e,c,mode='weight',weight={**c['initial'],'weight_kg':'26.5'})
    assert r.status_code==201,r.text;new=r.json()['replacement_event_id']
    with factory() as db:
        assert db.get(EventWeightModel,old['id']).weight_kg==Decimal('25')
        assert db.get(EventModel,new).replaced_event_id==old['id']
        assert db.scalar(select(func.count()).select_from(HistoryRectificationModel))==1
    current=client.get('/api/v1/weights/animals/'+a['id']+'/history',headers=h).json()['items']
    assert len(current)==1 and current[0]['weight_kg']=='26.50'
    e2=entry(client,h,a,'Pesaje');assert e2['has_rectifications']
    chain=context(client,h,a,e2).json();assert chain['entries'][0]['original']==c['source']
    assert chain['entries'][0]['corrected']['weight_kg']=='26.5'
    assert save(client,h,a,e,c,mode='weight',weight={**c['initial'],'weight_kg':'27'}).status_code==409
    r2=save(client,h,a,e2,chain,mode='weight',weight={**chain['initial'],'weight_kg':'27'})
    assert r2.status_code==201,r2.text
    assert len(context(client,h,a,entry(client,h,a,'Pesaje')).json()['entries'])==2
    report=client.get('/api/v1/reports/weights',headers=h,params={'animal_id':a['id']})
    assert report.status_code==200,report.text
    assert report.json()['items'][0]['weight_kg']=='27.00'
    assert client.get('/api/v1/audit',headers=h,params={'table':'history_rectifications','module':'weights'}).json()['total']==2


def test_clarification_is_immutable_and_optimistic_version_protects_notes(api):
    client,factory=api;h=login(client);a=animal(client,h,birth_date='2020-01-01')
    e=entry(client,h,a,'Alta en el sistema');c=context(client,h,a,e).json()
    r=save(client,h,a,e,c,mode='clarification',clarification='Aclaración conservada junto al registro original del animal.')
    assert r.status_code==201,r.text
    assert save(client,h,a,e,c,mode='clarification',clarification='Otra aclaración desde una ventana desactualizada.').status_code==409
    loaded=context(client,h,a,e).json();assert loaded['version']==1 and loaded['entries'][0]['recorded_by'].startswith('Owner')
    assert save(client,h,a,e,loaded,mode='clarification',clarification='Se agrega una segunda aclaración; la anterior permanece.').status_code==201
    for method in ('put','patch','delete'):
        assert client.request(method,'/api/v1/animals/'+a['id']+'/rectifications',headers=h,json={}).status_code==405
    assert len(context(client,h,a,e).json()['entries'])==2
    assert entry(client,h,a,'Alta en el sistema')['has_rectifications']
    assert not entry(client,h,a,'Fecha de nacimiento registrada')['has_rectifications']


def test_weight_constraints_and_animal_identity_are_preserved(api):
    client,factory=api;h=login(client);a=animal(client,h,birth_date='2024-01-01');b=animal(client,h)
    for day in ('2024-01-02','2024-01-03'):
        assert client.post('/api/v1/weights',headers=h,json={'animal_id':a['id'],'date':day,'weight_kg':'20'}).status_code==201
    e=next(i for i in entries(client,h,a) if i['title']=='Pesaje' and i['date']=='2024-01-02');c=context(client,h,a,e).json()
    for data,status in [({'date':'2024-01-03'},409),({'date':'2023-01-01'},422),({'animal_id':b['id']},422),({'weight_kg':'0'},422)]:
        r=save(client,h,a,e,c,mode='weight',weight={**c['initial'],**data});assert r.status_code==status,r.text
    with factory() as db:assert db.scalar(select(func.count()).select_from(HistoryRectificationModel))==0


def test_health_replacements_respect_links_and_case_state(api):
    client,factory=api;h=login(client);a=animal(client,h,birth_date='2020-01-01')
    o=client.post('/api/v1/health/observations',headers=h,json={'animal_id':a['id'],'date':'2024-01-01','observation':'Texto con error.'}).json()
    e=entry(client,h,a,'Observación');c=context(client,h,a,e).json()
    r=save(client,h,a,e,c,mode='observation',observation={**c['initial'],'observation':'Texto verificado que corrige la captura.'});assert r.status_code==201,r.text
    obs=client.get('/api/v1/health/observations',headers=h).json()['items'];assert len(obs)==1 and obs[0]['id']!=o['id']
    case=create_case(client,h,a['id'],observation_id=obs[0]['id']).json()
    e=entry(client,h,a,'Observación');c=context(client,h,a,e).json();assert c['replacement_mode'] is None and 'origen de un caso' in c['explanation']
    d=client.post('/api/v1/health/cases/'+case['id']+'/diagnoses',headers=h,json={'date':'2024-01-01','diagnosis':'Diagnóstico por verificar','severity':'mild'});assert d.status_code==201,d.text
    e=entry(client,h,a,'Diagnóstico');c=context(client,h,a,e).json()
    r=save(client,h,a,e,c,mode='diagnosis',diagnosis={**c['initial'],'diagnosis':'Diagnóstico corregido documentado.'});assert r.status_code==201,r.text
    detail=client.get('/api/v1/health/cases/'+case['id'],headers=h).json()
    assert len(detail['diagnoses'])==1 and detail['diagnoses'][0]['diagnosis']=='Diagnóstico corregido documentado.'


def test_rectification_requires_special_permission_and_source_permissions(api):
    client,factory=api;h=login(client);worker=login(client,'worker@example.com');a=animal(client,h)
    e=entry(client,h,a,'Alta en el sistema');c=context(client,h,a,e).json()
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'))
        db.add_all(RolePermissionModel(role_id=role.id,permission=p) for p in ['animals:read','animals:write'])
    assert save(client,worker,a,e,c,mode='clarification',clarification='Una nota sin el permiso especial de rectificación.').status_code==403
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'));db.add(RolePermissionModel(role_id=role.id,permission='history:rectify'))
    assert save(client,worker,a,e,c,mode='clarification',clarification='Una aclaración con los permisos requeridos.').status_code==201
    assert context(client,worker,a,e).json()['entries'][0]['recorded_by'].startswith('Worker')
    assert context(client,worker,a,{**e,'id':e['id'].replace(a['id'],str('00000000-0000-4000-8000-000000000001'))}).status_code==409


def test_weaning_and_sale_weight_are_clarification_only_and_noop_is_rejected(api):
    from tests.test_weanings import wean
    from tests.test_finance import category
    client,factory=api;h=login(client)
    a=animal(client,h,birth_date='2024-01-01');assert wean(client,h,a).status_code==201
    e=entry(client,h,a,'Destete');c=context(client,h,a,e).json()
    assert c['replacement_mode'] is None and 'destete' in c['explanation']
    assert save(client,h,a,e,c,mode='clarification',clarification='Se conserva el comprobante del destete y esta aclaración.').status_code==201
    b=animal(client,h,name='Venta',birth_date='2020-01-01')
    w=client.post('/api/v1/weights',headers=h,json={'animal_id':b['id'],'date':'2024-01-01','weight_kg':'25'}).json()
    e=entry(client,h,b,'Pesaje');c=context(client,h,b,e).json()
    assert save(client,h,b,e,c,mode='weight',weight=c['initial']).status_code==422
    sale=client.post('/api/v1/exits',headers=h,json={'animal_id':b['id'],'date':'2024-01-01','exit_type':'sale','reason':'Venta registrada'}).json()
    cat=category(client,h,'income','Ventas')
    income=client.post('/api/v1/finance/incomes',headers=h,json={'category_id':cat['id'],'exit_event_id':sale['id'],'pricing_mode':'per_kg','weight_event_id':w['id'],'price_per_kg':'10','date':'2024-01-01'})
    assert income.status_code==201,income.text
    c=context(client,h,b,e).json();assert c['replacement_mode'] is None and 'venta' in c['explanation']
    assert save(client,h,b,e,c,mode='weight',weight={'animal_id':b['id'],'date':'2024-01-01','weight_kg':'26'}).status_code==409
    assert client.get('/api/v1/finance/incomes/'+income.json()['id'],headers=h).json()['amount']=='250.00'


def test_health_notes_are_not_exposed_to_an_animal_only_reader(api):
    client,factory=api;h=login(client);worker=login(client,'worker@example.com');a=animal(client,h,birth_date='2020-01-01')
    client.post('/api/v1/health/observations',headers=h,json={'animal_id':a['id'],'date':'2024-01-01','observation':'Hallazgo sanitario privado.'})
    e=entry(client,h,a,'Observación');c=context(client,h,a,e).json()
    assert save(client,h,a,e,c,mode='clarification',clarification='Aclaración sanitaria privada para este registro.').status_code==201
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'))
        db.add_all(RolePermissionModel(role_id=role.id,permission=p) for p in ['animals:read','history:rectify','animals:write'])
    assert context(client,worker,a,e).status_code==409
    assert all(i['module']!='health' for i in entries(client,worker,a))
