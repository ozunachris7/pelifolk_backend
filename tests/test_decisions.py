from datetime import date,timedelta
from uuid import uuid4
from sqlalchemy import func,select
from src.core.models import AnimalDecisionModel,AuditModel
from tests.conftest import login
from tests.test_animals import animal


def add(client,h,a,**values):
    return client.post('/api/v1/animals/'+a['id']+'/decisions',headers=h,json={
        'date':'2024-01-03','kind':'retain_breeding','reason':'Buen crecimiento y antecedentes registrados.',**values})


def test_permanent_history_order_filter_and_audit(api):
    client,factory=api;h=login(client);a=animal(client,h)
    r=add(client,h,a);assert r.status_code==201,r.text
    saved=r.json()
    assert add(client,h,a,date='2024-01-04',kind='separate',reason=' Observación individual. ').status_code==201
    base='/api/v1/animals/'+a['id']+'/decisions'
    page=client.get(base+'?limit=1',headers=h).json()
    assert page['total']==2 and page['items'][0]['kind']=='separate'
    assert page['items'][0]['reason']=='Observación individual.'
    assert client.get(base+'?offset=1&limit=1',headers=h).json()['items'][0]['id']==saved['id']
    assert client.get(base+'?kind=retain_breeding',headers=h).json()['total']==1
    assert client.get('/api/v1/animals/'+a['id'],headers=h).json()['is_breeder'] is False
    with factory() as db:
        row=db.get(AnimalDecisionModel,saved['id']);assert row.role_id==saved['role_id']
        log=db.scalar(select(AuditModel).where(AuditModel.record_id==saved['id']))
        assert log.table=='animal_decisions' and log.new_values['reason']==saved['reason']
    assert client.get('/api/v1/audit?module=animals&table=animal_decisions',headers=h).json()['total']==2
    for method in ['put','delete']:
        assert getattr(client,method)(base,headers=h).status_code==405


def test_dates_exit_and_birth_edit_preserve_decision_history(api):
    client,_=api;h=login(client);a=animal(client,h,birth_date='2024-01-01')
    assert add(client,h,a,date='2023-12-31').status_code==422
    assert add(client,h,a,date='2024-01-03').status_code==201
    assert client.put('/api/v1/animals/'+a['id'],headers=h,json={'name':'Luna','sex':'female','birth_date':'2024-01-04'}).status_code==422
    exit_data={'animal_id':a['id'],'exit_type':'death','date':'2024-01-02','reason':'Baja registrada'}
    assert client.post('/api/v1/exits',headers=h,json=exit_data).status_code==422
    assert client.post('/api/v1/exits',headers=h,json={**exit_data,'date':'2024-01-04'}).status_code==201
    assert add(client,h,a,date='2024-01-05').status_code==409
    assert add(client,h,a,date='2024-01-04',kind='other').status_code==201
    assert client.get('/api/v1/animals/'+a['id']+'/decisions',headers=h).json()['total']==2


def test_permissions_validation_and_missing_animal(api):
    client,factory=api;h=login(client);worker=login(client,'worker@example.com');a=animal(client,h)
    base='/api/v1/animals/'+a['id']+'/decisions'
    assert client.get(base).status_code==401
    assert client.get(base,headers=worker).status_code==403
    assert add(client,worker,a).status_code==403
    for values in [{'reason':'  '},{'kind':'bad'},{'date':str(date.today()+timedelta(days=1))},{'user_id':'fake'}]:
        assert add(client,h,a,**values).status_code==422
    assert client.get(base+'?limit=101',headers=h).status_code==422
    assert client.get('/api/v1/animals/'+str(uuid4())+'/decisions',headers=h).status_code==404
    with factory() as db:assert db.scalar(select(func.count()).select_from(AnimalDecisionModel))==0
