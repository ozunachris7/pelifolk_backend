from sqlalchemy import select,func
from src.core.models import AnimalModel,AuditModel,ExitModel,EventModel
from tests.conftest import login
from tests.test_animals import animal


def test_mating_pregnancy_birth_offspring_and_history(api):
    client,factory=api;h=login(client)
    female=animal(client,h,name='Luna',birth_date='2020-01-01');male=animal(client,h,name='Trueno',sex='male',birth_date='2019-01-01')
    r=client.post('/api/v1/breeding/matings',headers=h,json={'animal_id':female['id'],'male_id':male['id'],'date':'2024-01-01'});assert r.status_code==201,r.text;mating=r.json()
    r=client.post('/api/v1/breeding/pregnancy-diagnoses',headers=h,json={'animal_id':female['id'],'date':'2024-02-01','result':'pregnant','mating_event_id':mating['id']});assert r.status_code==201,r.text
    data={'animal_id':female['id'],'father_id':male['id'],'date':'2024-06-01','birth_type_id':1,'offspring':[{'name':'Estrella','siniiga':'MXNEW1','sex':'female','birth_weight_kg':'3.25'},{'name':'Cría sin vida','sex':'male','alive':False}]}
    r=client.post('/api/v1/breeding/births',headers=h,json=data);assert r.status_code==201,r.text;birth=r.json();assert len(birth['offspring'])==2
    child=next(c for c in birth['offspring'] if c['alive'])
    detail=client.get('/api/v1/animals/'+child['animal']['id'],headers=h).json();assert detail['mother_id']==female['id'] and detail['father_id']==male['id'] and detail['birth_date']=='2024-06-01'
    assert client.get('/api/v1/breeding/animals/'+child['animal']['id']+'/history',headers=h).json()['items'][0]['id']==birth['id']
    assert client.get('/api/v1/breeding/events?kind=birth&q=luna',headers=h).json()['total']==1
    assert len(client.get('/api/v1/breeding/animals/'+female['id']+'/history',headers=h).json()['items'])==3
    assert client.get('/api/v1/breeding/animals/'+male['id']+'/history',headers=h).json()['items'][0]['kind']=='mating'
    assert client.post('/api/v1/breeding/births',headers=h,json=data).status_code==409
    assert client.put('/api/v1/animals/'+male['id'],headers=h,json={'name':'Trueno','sex':'female'}).status_code==422
    assert client.put('/api/v1/animals/'+child['animal']['id'],headers=h,json={'name':'Estrella','sex':'female','birth_date':'2024-06-02','mother_id':female['id'],'father_id':male['id']}).status_code==422
    with factory() as db:
        dead=next(c for c in birth['offspring'] if not c['alive']);assert db.scalar(select(EventModel.id).join(ExitModel,ExitModel.event_id==EventModel.id).where(EventModel.animal_id==dead['animal']['id']))
        assert db.scalar(select(AuditModel).where(AuditModel.record_id==birth['id'])).new_values['event_type_id']==7


def test_invalid_reproduction_is_atomic_and_protected(api):
    client,factory=api;h=login(client);worker=login(client,'worker@example.com')
    female=animal(client,h,birth_date='2020-01-01');male=animal(client,h,sex='male',birth_date='2020-01-01')
    assert client.get('/api/v1/breeding/events',headers=worker).status_code==403
    assert client.get('/api/v1/breeding/events').status_code==401
    d={'animal_id':male['id'],'male_id':female['id'],'date':'2024-01-01'}
    assert client.post('/api/v1/breeding/matings',headers=h,json=d).status_code==422
    birth={'animal_id':female['id'],'date':'2024-06-01','birth_type_id':1,'offspring':[{'name':'A','sex':'male','siniiga':'DUP'},{'name':'B','sex':'female','siniiga':'dup'}]}
    assert client.post('/api/v1/breeding/births',headers=h,json=birth).status_code==422
    assert client.post('/api/v1/breeding/births',headers=worker,json=birth).status_code==403
    other=animal(client,h,name='Existing',siniiga='EXIST')
    birth['offspring']=[{'name':'New','sex':'female'},{'name':'Conflict','sex':'male','siniiga':'EXIST'}]
    assert client.post('/api/v1/breeding/births',headers=h,json=birth).status_code==409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AnimalModel))==3
        assert db.scalar(select(func.count()).select_from(EventModel))==0
