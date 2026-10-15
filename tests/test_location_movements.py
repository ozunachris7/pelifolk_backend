from datetime import date, timedelta
from sqlalchemy import select
from src.core.models import AuditModel, RoleModel, RolePermissionModel, EventModel
from tests.conftest import login
from tests.test_animals import animal


def location(client,h,name):
    kinds=client.get('/api/v1/location-types',headers=h).json()
    kind=kinds[0] if kinds else client.post('/api/v1/location-types',headers=h,json={'name':'Corral'}).json()
    r=client.post('/api/v1/locations',headers=h,json={'name':name,'location_type_id':kind['id']});assert r.status_code==201,r.text
    return r.json()


def test_location_movements_current_history_lifecycle_and_birth_validation(api):
    client,factory=api;h=login(client);a=animal(client,h,birth_date='2020-01-01');l1=location(client,h,'Corral norte');l2=location(client,h,'Potrero sur')
    data={'animal_id':a['id'],'location_id':l1['id'],'date':'2024-01-01','reason':'Ingreso al corral'}
    r=client.post('/api/v1/locations/movements',headers=h,json=data);assert r.status_code==201,r.text;first=r.json()
    positions=client.get('/api/v1/locations/animal-positions',headers=h).json();assert positions['items'][0]['current_location']['id']==l1['id']
    assert client.get('/api/v1/animals/'+a['id'],headers=h).json()['current_location']['id']==l1['id']
    inactive={'name':l1['name'],'location_type_id':l1['location_type_id'],'active':False}
    assert client.put('/api/v1/locations/'+l1['id'],headers=h,json=inactive).status_code==409
    for change in [{'date':'2023-12-31'},{'date':'2024-01-01','location_id':l2['id']},{'date':'2024-01-02'},{'reason':' '},{'date':str(date.today()+timedelta(days=1))}]:
        assert client.post('/api/v1/locations/movements',headers=h,json={**data,**change}).status_code in (409,422)
    assert client.put('/api/v1/animals/'+a['id'],headers=h,json={'name':'Luna','sex':'female','birth_date':'2024-01-02'}).status_code==422
    r=client.post('/api/v1/locations/movements',headers=h,json={**data,'location_id':l2['id'],'date':'2024-01-03','reason':'Acceso a pastoreo'});assert r.status_code==201,r.text
    history=client.get('/api/v1/locations/animals/'+a['id']+'/history',headers=h,params={'limit':1}).json()
    assert history['total']==2 and history['items'][0]['from_location']['id']==l1['id'] and history['items'][0]['to_location']['id']==l2['id']
    assert client.put('/api/v1/locations/'+l1['id'],headers=h,json=inactive).status_code==200
    assert client.post('/api/v1/locations/movements',headers=h,json={**data,'date':'2024-01-04'}).status_code==409
    assert client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'exit_type':'sale','date':'2024-01-02','reason':'Venta'}).status_code==422
    assert client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'exit_type':'sale','date':'2024-01-04','reason':'Venta'}).status_code==201
    assert client.get('/api/v1/locations/animal-positions',headers=h).json()['total']==0
    old=client.get('/api/v1/locations/animal-positions',headers=h,params={'status':'exited'}).json()['items'][0]
    assert old['current_location'] is None and old['last_known_location']['id']==l2['id']
    assert client.get('/api/v1/animals/'+a['id'],headers=h).json()['current_location'] is None
    assert client.post('/api/v1/locations/movements',headers=h,json={**data,'location_id':l2['id'],'date':'2024-01-05'}).status_code==409
    with factory() as db:
        audit=db.scalar(select(AuditModel).where(AuditModel.record_id==first['id']))
        assert audit.new_values['location_id']==l1['id'] and audit.new_values['reason']=='Ingreso al corral'


def test_location_history_replacements_and_permissions(api):
    client,factory=api;h=login(client);a=animal(client,h);loc=location(client,h,'Corral')
    first=client.post('/api/v1/locations/movements',headers=h,json={'animal_id':a['id'],'location_id':loc['id'],'date':'2024-01-01','reason':'Registro inicial'}).json()
    with factory.begin() as db:
        source=db.get(EventModel,first['id']);replacement=EventModel(animal_id=a['id'],event_type_id=9,date=source.date,user_id=source.user_id,role_id=source.role_id,location_id=loc['id'],reason='Reemplazo',replaced_event_id=source.id);db.add(replacement)
    history=client.get('/api/v1/locations/animals/'+a['id']+'/history',headers=h).json();assert history['total']==1 and history['items'][0]['reason']=='Reemplazo'
    worker=login(client,'worker@example.com')
    paths=['/api/v1/locations/animal-positions','/api/v1/locations/animals/'+a['id']+'/history']
    for path in paths:assert client.get(path).status_code==401 and client.get(path,headers=worker).status_code==403
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'));db.add(RolePermissionModel(role_id=role.id,permission='locations:read'))
    for path in paths:assert client.get(path,headers=worker).status_code==200
    assert client.get('/api/v1/animals',headers=worker).status_code==403
    assert client.post('/api/v1/locations/movements',headers=worker,json={'animal_id':a['id'],'location_id':loc['id'],'date':'2024-01-03','reason':'Intento'}).status_code==403
    assert client.get(paths[0],headers=h,params={'limit':101}).status_code==422
