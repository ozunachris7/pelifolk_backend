from datetime import date,timedelta
from sqlalchemy import select,func
from src.core.models import AuditModel,EventModel,EventWeightModel,EventWeaningModel
from tests.conftest import login
from tests.test_animals import animal
from tests.test_weights import post as weigh


def wean(client,h,a,**values):
    return client.post('/api/v1/weanings',headers=h,json={
        'animal_id':a['id'],'date':'2024-03-01','weight_kg':'18.50','notes':'  Destete registrado.  ',**values})


def test_records_weaning_weight_age_mother_and_history(api):
    client,factory=api;h=login(client)
    mother=animal(client,h,name='Luna',birth_date='2022-01-01')
    child=animal(client,h,name='Aurora',mother_id=mother['id'],birth_date='2024-01-01')
    options=client.get('/api/v1/weanings/animal-options?q=aurora',headers=h).json()
    assert options[0]['mother']['id']==mother['id']
    response=wean(client,h,child);assert response.status_code==201,response.text
    w=response.json();assert w['age_days']==60 and w['mother']['id']==mother['id'] and w['notes']=='Destete registrado.'
    weights=client.get('/api/v1/weights/animals/'+child['id']+'/history',headers=h).json()
    assert len(weights['items'])==1 and weights['items'][0]['is_weaning'] and weights['items'][0]['weight_kg']=='18.50'
    assert wean(client,h,child).status_code==409
    assert client.get('/api/v1/weanings/animal-options?q=aurora',headers=h).json()==[]
    assert client.get('/api/v1/weanings?q=aurora',headers=h).json()['total']==1
    assert client.get('/api/v1/weanings/animals/'+child['id'],headers=h).json()['id']==w['id']
    with factory() as db:
        audit=db.scalar(select(AuditModel).where(AuditModel.table=='event_weanings',AuditModel.record_id==w['id']))
        assert audit.new_values['mother_id']==mother['id'] and audit.new_values['weight_reused'] is False
        assert db.scalar(select(func.count()).select_from(EventWeightModel))==1
    assert client.get('/api/v1/audit?module=weights&table=event_weanings',headers=h).json()['total']==1


def test_reuses_matching_daily_weight_without_overwriting_notes(api):
    client,factory=api;h=login(client);child=animal(client,h,name='Aurora',birth_date='2024-01-01')
    previous=weigh(client,h,child['id'],'2024-03-01','18.50',notes='Pesaje anterior').json()
    assert wean(client,h,child,weight_kg='19').status_code==409
    with factory() as db:assert db.scalar(select(func.count()).select_from(EventWeaningModel))==0
    response=wean(client,h,child);assert response.status_code==201,response.text
    assert response.json()['id']==previous['id']
    weights=client.get('/api/v1/weights/animals/'+child['id']+'/history',headers=h).json()['items']
    assert len(weights)==1 and weights[0]['notes']=='Pesaje anterior' and weights[0]['is_weaning']
    with factory() as db:
        audit=db.scalar(select(AuditModel).where(AuditModel.table=='event_weanings'))
        assert audit.new_values['weight_reused'] is True


def test_unknown_birth_and_historical_mother_are_not_invented_or_rewritten(api):
    client,_=api;h=login(client);mother=animal(client,h,name='Luna');other=animal(client,h,name='Otra madre')
    child=animal(client,h,name='Aurora',mother_id=mother['id'])
    r=wean(client,h,child);assert r.status_code==201,r.text
    assert r.json()['age_days'] is None
    assert client.put('/api/v1/animals/'+child['id'],headers=h,json={'name':'Aurora','sex':'female','mother_id':other['id']}).status_code==200
    saved=client.get('/api/v1/weanings/animals/'+child['id'],headers=h).json()
    assert saved['mother']['id']==mother['id'] and saved['age_days'] is None


def test_validation_dates_exit_and_permissions_are_atomic(api):
    client,factory=api;h=login(client);worker=login(client,'worker@example.com')
    a=animal(client,h,birth_date='2024-01-01')
    for values in [{'date':'2024-01-01'},{'date':'2023-12-31'},{'date':str(date.today()+timedelta(days=1))},
                   {'weight_kg':'0'},{'weight_kg':'1.234'},{'user_id':'fake'}]:
        assert wean(client,h,a,**values).status_code==422
    assert wean(client,worker,a).status_code==403
    for endpoint in ['/weanings','/weanings/animal-options','/weanings/animals/'+a['id']]:
        assert client.get('/api/v1'+endpoint,headers=worker).status_code==403
        assert client.get('/api/v1'+endpoint).status_code==401
    with factory() as db:assert db.scalar(select(func.count()).select_from(EventModel))==0
    assert wean(client,h,a).status_code==201
    assert client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'date':'2024-02-01','exit_type':'sale','reason':'Venta'}).status_code==422
    assert client.put('/api/v1/animals/'+a['id'],headers=h,json={'name':'Luna','sex':'female','birth_date':'2024-04-01'}).status_code==422
    for method in ['put','delete']:
        assert getattr(client,method)('/api/v1/weanings',headers=h).status_code==405
