from datetime import date, timedelta
from sqlalchemy import select,func
from src.core.models import AnimalReactionModel, AuditModel, RoleModel,RolePermissionModel
from tests.conftest import login
from tests.test_animals import animal
from tests.test_doses import setup,dose

URL='/api/v1/health/reactions'
def report(client,h,a,**changes):
    return client.post(URL,headers=h,json={'animal_id':a['id'],'date':'2024-01-04','kind':'adverse_reaction','description':'Enrojecimiento observado tras aplicación; causa sin confirmar.',**changes})


def test_reports_preserve_original_and_audit_closure(api):
    client,factory=api;h=login(client);a=animal(client,h,birth_date='2020-01-01')
    r=report(client,h,a,suspected_agent='Agente aún sin identificar');assert r.status_code==201,r.text;r=r.json()
    assert r['status']=='open' and r['product_id'] is None and r['dose'] is None
    assert r['recorded_by'].startswith('Owner')
    close=URL+'/'+r['id']+'/closure'
    assert client.post(close,headers=h,json={'date':'2024-01-03','notes':'Revisado'}).status_code==422
    closed=client.post(close,headers=h,json={'date':'2024-01-05','notes':'Seguimiento concluido; se conserva el antecedente.'})
    assert closed.status_code==200,closed.text;c=closed.json()
    assert c['status']=='closed' and c['description']==r['description'] and c['recorded_by']==r['recorded_by']
    assert client.post(close,headers=h,json={'date':'2024-01-05','notes':'Otra vez'}).status_code==409
    assert client.get(URL,headers=h,params={'animal_id':a['id'],'status':'open'}).json()['total']==0
    assert client.get(URL,headers=h,params={'status':'closed'}).json()['total']==1
    with factory() as db:
        row=db.get(AnimalReactionModel,r['id']);assert row.role_id and row.closure_role_id and row.closed_by==row.user_id
        assert db.scalar(select(func.count()).select_from(AuditModel).where(AuditModel.table=='animal_reactions'))==2
    timeline=client.get('/api/v1/animals/'+a['id']+'/timeline?module=health',headers=h).json()['items']
    assert {i['kind'] for i in timeline}>={'reaction','reaction_closure'}
    assert next(i for i in timeline if i['kind']=='reaction')['notes']==r['description']
    assert client.get('/api/v1/audit?module=health&table=animal_reactions',headers=h).json()['total']==2
    assert client.delete(URL+'/'+r['id'],headers=h).status_code in (404,405)


def test_dose_links_require_same_animal_product_and_chronology(api):
    client,_=api;h=login(client);a,c,p,t=setup(client,h);d=dose(client,h,t,p).json()
    r=report(client,h,a,dose_id=d['id']);assert r.status_code==201,r.text
    assert r.json()['product_id']==p['id'] and r.json()['dose']['id']==d['id']
    assert report(client,h,a,dose_id=d['id'],date='2024-01-02').status_code==422
    assert report(client,h,a,dose_id=d['id'],product_id=a['id']).status_code==422
    other=animal(client,h,siniiga='OTHER-REACTION',birth_date='2020-01-01')
    assert report(client,h,other,dose_id=d['id']).status_code==422
    listing=client.get(URL+'/dose-options',headers=h,params={'animal_id':a['id']}).json()
    assert listing['total']==1 and listing['items'][0]['id']==d['id']
    assert client.get(URL+'/dose-options',headers=h,params={'animal_id':other['id']}).json()['total']==0
    assert client.get(URL+'/dose-options',headers=h,params={'animal_id':a['id'],'product_id':other['id']}).json()['total']==0


def test_reaction_permissions_and_invalid_inputs(api):
    client,factory=api;h=login(client);worker=login(client,'worker@example.com');a=animal(client,h,birth_date='2020-01-01')
    assert client.get(URL).status_code==401 and client.get(URL,headers=worker).status_code==403
    assert report(client,worker,a).status_code==403
    for values in ({'date':(date.today()+timedelta(days=1)).isoformat()},{'date':'2019-12-31'},
            {'kind':'confirmed_allergy'},{'description':' '},{'user_id':a['id']},{'product_id':a['id']},{'dose_id':a['id']}):
        assert report(client,h,a,**values).status_code==422,values
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'));db.add(RolePermissionModel(role_id=role.id,permission='health:read'))
    assert client.get(URL,headers=worker).status_code==200 and report(client,worker,a).status_code==403
    r=report(client,h,a,kind='suspected_allergy').json()
    assert client.post(URL+'/'+r['id']+'/closure',headers=worker,json={'date':'2024-01-05','notes':'Revisado'}).status_code==403
    timeline=client.get('/api/v1/animals/'+a['id']+'/timeline',headers=h).json()['items']
    assert next(i for i in timeline if i['kind']=='reaction')['title']=='Sospecha de alergia'
    assert client.get(URL+'?limit=101',headers=h).status_code==422


def test_reaction_dates_protect_birth_and_exit_but_closure_can_be_after_exit(api):
    client,_=api;h=login(client);a=animal(client,h,birth_date='2020-01-01');r=report(client,h,a).json()
    assert client.put('/api/v1/animals/'+a['id'],headers=h,json={'name':'Luna','sex':'female','birth_date':'2024-01-05'}).status_code==422
    exit_data={'animal_id':a['id'],'date':'2024-01-03','exit_type':'sale','reason':'Venta'}
    assert client.post('/api/v1/exits',headers=h,json=exit_data).status_code==422
    assert client.post('/api/v1/exits',headers=h,json={**exit_data,'date':'2024-01-05'}).status_code==201
    assert report(client,h,a,date='2024-01-06').status_code==409
    assert client.post(URL+'/'+r['id']+'/closure',headers=h,json={'date':'2024-01-06','notes':'Cierre administrativo posterior a la salida.'}).status_code==200


def test_historical_links_remain_available_for_inactive_products_and_replaced_instructions(api):
    from src.core.models import ProductModel,EventModel
    client,factory=api;h=login(client);a,c,p,t=setup(client,h);d=dose(client,h,t,p).json()
    with factory.begin() as db:
        db.get(ProductModel,p['id']).active=False
        old=db.get(EventModel,t['id'])
        db.add(EventModel(animal_id=a['id'],event_type_id=3,date=old.date,user_id=old.user_id,role_id=old.role_id,replaced_event_id=old.id))
    r=report(client,h,a,product_id=p['id'],dose_id=d['id'])
    assert r.status_code==201,r.text
    assert client.get(URL+'/dose-options',headers=h,params={'animal_id':a['id']}).json()['total']==1
    assert client.get(URL,headers=h,params={'q':'%'}).json()['total']==0
    assert client.get(URL,headers=h,params={'q':a['siniiga']}).json()['total']==1
    # Animal access alone does not reveal this clinical report through the integral timeline.
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'))
        if not db.get(RolePermissionModel,(role.id,'animals:read')):
            db.add(RolePermissionModel(role_id=role.id,permission='animals:read'))
    worker=login(client,'worker@example.com')
    timeline=client.get('/api/v1/animals/'+a['id']+'/timeline',headers=worker)
    assert timeline.status_code==200,timeline.text
    assert not any(i['kind'] in ('reaction','reaction_closure') for i in timeline.json()['items'])
