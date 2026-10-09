from datetime import date, timedelta
from sqlalchemy import select,func
from src.core.models import EventModel,AuditModel
from tests.conftest import login
from tests.test_animals import animal
from tests.test_health import create_case,transition


def product(client,headers,**values):
    return client.post('/api/v1/health/products',headers=headers,json={'name':'Producto de prueba','product_type_id':1,'unit_id':1,'withdrawal_days':7,**values})


def test_product_catalog_and_treatment_history(api):
    client,factory=api;owner=login(client);saved=animal(client,owner);case=create_case(client,owner,saved['id']).json()
    catalogs=client.get('/api/v1/health/catalogs',headers=owner).json()
    assert catalogs['units'][0]['code']=='ml'
    response=product(client,owner);assert response.status_code==201,response.text
    p=response.json();assert p['withdrawal_days']==7 and p['product_type_name']=='medicine'
    assert product(client,owner,name=' producto de prueba ').status_code==409
    path='/api/v1/health/cases/'+case['id']+'/treatments'
    data={'product_id':p['id'],'start_date':'2024-01-03','dose_value':'2.125','dose_unit_id':1,'route_id':1,'frequency_hours':12,'duration_days':3}
    response=client.post(path,headers=owner,json=data);assert response.status_code==201,response.text
    t=response.json();assert t['end_date']=='2024-01-06' and t['last_day']=='2024-01-05' and t['dose_value']=='2.125'
    detail=client.get('/api/v1/health/cases/'+case['id'],headers=owner).json()
    assert detail['case']['status']=='under_treatment' and detail['treatments'][0]['product']['id']==p['id']
    assert detail['activity'][-1]['status']=='under_treatment'
    history=client.get('/api/v1/health/animals/'+saved['id']+'/history',headers=owner).json()
    assert history['treatments'][0]['id']==t['id']
    assert transition(client,owner,case['id'],'under_treatment','closed',closed_date='2024-01-04').status_code==422
    assert transition(client,owner,case['id'],'under_treatment','closed',closed_date='2024-01-05').status_code==200
    assert client.post(path,headers=owner,json=data).status_code==409
    response=client.put('/api/v1/health/products/'+p['id'],headers=owner,json={'name':'Producto editado','product_type_id':1,'unit_id':1,'withdrawal_days':5,'active':False})
    assert response.status_code==200,response.text
    assert client.get('/api/v1/health/products?active=true',headers=owner).json()['total']==0
    assert client.get('/api/v1/health/products?q=editado&active=false',headers=owner).json()['total']==1
    assert client.get('/api/v1/health/cases/'+case['id'],headers=owner).json()['treatments'][0]['product']['active'] is False
    with factory() as db:
        event=db.get(EventModel,t['id']);assert event.animal_id==saved['id'] and event.event_type_id==3
        audit=db.scalar(select(AuditModel).where(AuditModel.record_id==t['id']));assert audit.new_values['dose_value']=='2.125'


def test_invalid_treatments_products_and_permissions_are_atomic(api):
    client,factory=api;owner,worker=login(client),login(client,'worker@example.com');saved=animal(client,owner);case=create_case(client,owner,saved['id']).json();p=product(client,owner).json()
    for path in ['/health/catalogs','/health/products']:
        assert client.get('/api/v1'+path,headers=worker).status_code==403
    assert product(client,worker).status_code==403
    assert product(client,owner,name='Other',unit_id=999).status_code==422
    assert product(client,owner,name='Other',withdrawal_days=-1).status_code==422
    path='/api/v1/health/cases/'+case['id']+'/treatments'
    data={'product_id':p['id'],'start_date':'2024-01-01','dose_value':'2','dose_unit_id':1,'route_id':1,'duration_days':1}
    assert client.post(path,headers=worker,json=data).status_code==403
    assert client.post(path,json=data).status_code==401
    for invalid in [{'start_date':'2023-12-31'},{'start_date':str(date.today()+timedelta(days=1))},{'dose_value':0},{'dose_value':'1.1234'},{'frequency_hours':0},{'duration_days':0},{'duration_days':1.5},{'route_id':999},{'dose_unit_id':999}]:
        assert client.post(path,headers=owner,json={**data,**invalid}).status_code==422
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(EventModel))==0
    assert client.get('/api/v1/health/cases/'+case['id'],headers=owner).json()['case']['status']=='open'
    assert client.post(path,headers=owner,json=data).status_code==201
    client.put('/api/v1/health/products/'+p['id'],headers=owner,json={'name':p['name'],'product_type_id':1,'unit_id':1,'withdrawal_days':7,'active':False})
    assert client.post(path,headers=owner,json=data).status_code==409
