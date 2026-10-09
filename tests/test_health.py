from datetime import date, timedelta
from uuid import uuid4
from sqlalchemy import select, func
from src.core.models import AuditModel, EventModel, HealthCaseModel
from tests.conftest import login
from tests.test_animals import animal


def create_case(client, headers, animal_id, **values):
    return client.post('/api/v1/health/cases', headers=headers, json={'animal_id':animal_id,'reason':'  Cojera  ','start_date':'2024-01-01',**values})


def transition(client, headers, case_id, expected, status, **values):
    return client.patch('/api/v1/health/cases/'+case_id+'/status', headers=headers, json={'expected_status':expected,'status':status,**values})


def test_observation_case_history_and_audit(api):
    client, factory = api
    owner=login(client)
    saved=animal(client,owner,birth_date='2023-01-01',siniiga='MX123')
    observation=client.post('/api/v1/health/observations',headers=owner,json={'animal_id':saved['id'],'date':'2024-01-01','observation':'  Camina con dificultad  '})
    assert observation.status_code==201, observation.text
    assert observation.json()['observation']=='Camina con dificultad'
    case=create_case(client,owner,saved['id'],notes='Revisar extremidades')
    assert case.status_code==201,case.text
    case=case.json(); assert case['status']=='open' and case['reason']=='Cojera'
    assert transition(client,owner,case['id'],'open','under_treatment').status_code==200
    assert transition(client,owner,case['id'],'under_treatment','closed',closed_date='2024-01-03').status_code==200
    assert transition(client,owner,case['id'],'closed','open').status_code==200
    detail=client.get('/api/v1/health/cases/'+case['id'],headers=owner).json()
    assert detail['case']['closed_date'] is None
    assert [a['status'] for a in detail['activity']]==['open','under_treatment','closed','open']
    assert detail['activity'][2]['closed_date']=='2024-01-03'
    history=client.get('/api/v1/health/animals/'+saved['id']+'/history',headers=owner).json()
    assert len(history['observations'])==1 and len(history['cases'])==1
    assert client.get('/api/v1/health/cases?q=mx123&status=open&limit=1',headers=owner).json()['total']==1
    assert client.get('/api/v1/health/cases?status=closed',headers=owner).json()['total']==0
    assert client.get('/api/v1/health/observations?q=mx123',headers=owner).json()['items'][0]['id']==observation.json()['id']
    assert client.get('/api/v1/health/animal-options?q=mx123',headers=owner).json()[0]['id']==saved['id']
    with factory() as db:
        event=db.get(EventModel,observation.json()['id'])
        assert event.event_type_id==1 and event.role_id and event.user_id
        assert db.scalar(select(AuditModel).where(AuditModel.record_id==event.id)).new_values['observation']=='Camina con dificultad'


def test_validation_permissions_and_conflicts(api):
    client,factory=api
    owner,worker=login(client),login(client,'worker@example.com')
    saved=animal(client,owner,birth_date='2023-01-01')
    assert client.get('/api/v1/health/cases').status_code==401
    for path in ['cases','observations','animal-options','animals/'+saved['id']+'/history']:
        assert client.get('/api/v1/health/'+path,headers=worker).status_code==403
    assert create_case(client,worker,saved['id']).status_code==403
    assert client.post('/api/v1/health/observations',headers=worker,json={'animal_id':saved['id'],'date':'2024-01-01','observation':'test'}).status_code==403
    assert create_case(client,owner,saved['id'],start_date='2022-01-01').status_code==422
    assert create_case(client,owner,saved['id'],start_date=str(date.today()+timedelta(days=1))).status_code==422
    assert create_case(client,owner,saved['id'],reason='  ').status_code==422
    assert create_case(client,owner,str(uuid4())).status_code==404
    assert client.post('/api/v1/health/observations',headers=owner,json={'animal_id':saved['id'],'date':'2022-01-01','observation':'test'}).status_code==422
    case=create_case(client,owner,saved['id']).json()
    for values in [{},{'closed_date':'2023-12-31'},{'closed_date':str(date.today()+timedelta(days=1))}]:
        assert transition(client,owner,case['id'],'open','closed',**values).status_code==422
    assert transition(client,owner,case['id'],'closed','open').status_code==409
    assert transition(client,owner,case['id'],'open','open').status_code==409
    assert transition(client,worker,case['id'],'open','under_treatment').status_code==403
    assert transition(client,owner,case['id'],'open','under_treatment',closed_date='2024-01-02').status_code==422
    assert client.put('/api/v1/animals/'+saved['id'],headers=owner,json={'name':'Luna','sex':'female','birth_date':'2024-01-02'}).status_code==422
    assert client.get('/api/v1/health/cases/'+str(uuid4()),headers=owner).status_code==404
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(EventModel))==0
        assert db.scalar(select(func.count()).select_from(HealthCaseModel))==1
        assert db.scalar(select(func.count()).select_from(AuditModel).where(AuditModel.table=='health_cases'))==1


def test_empty_history_and_observation_birth_guard(api):
    client,factory=api;owner=login(client);saved=animal(client,owner)
    assert client.get('/api/v1/health/animals/'+saved['id']+'/history',headers=owner).json()['observations']==[]
    assert client.post('/api/v1/health/observations',headers=owner,json={'animal_id':saved['id'],'date':'2024-01-01','observation':'Registro'}).status_code==201
    assert client.put('/api/v1/animals/'+saved['id'],headers=owner,json={'name':'Luna','sex':'female','birth_date':'2024-01-02'}).status_code==422


def test_diagnoses_dates_closed_cases_history_permissions_and_audit(api):
    client,factory=api
    owner,worker=login(client),login(client,'worker@example.com')
    saved=animal(client,owner,birth_date='2023-01-01')
    case=create_case(client,owner,saved['id']).json()
    path='/api/v1/health/cases/'+case['id']+'/diagnoses'
    data={'date':'2024-01-03','diagnosis':'  Inflamación de extremidad derecha  ','severity':'moderate'}
    assert client.post(path,json=data).status_code==401
    assert client.post(path,headers=worker,json=data).status_code==403
    for invalid in [{'date':'2023-12-31'},{'date':str(date.today()+timedelta(days=1))},{'diagnosis':'  '},{'severity':'other'}]:
        assert client.post(path,headers=owner,json={**data,**invalid}).status_code==422
    response=client.post(path,headers=owner,json=data)
    assert response.status_code==201,response.text
    diagnosis=response.json()
    assert diagnosis['diagnosis']=='Inflamación de extremidad derecha'
    assert diagnosis['animal']['id']==saved['id'] and diagnosis['health_case_id']==case['id']
    assert diagnosis['recorded_by'].startswith('Owner')
    detail=client.get('/api/v1/health/cases/'+case['id'],headers=owner).json()
    assert detail['diagnoses'][0]['id']==diagnosis['id']
    history=client.get('/api/v1/health/animals/'+saved['id']+'/history',headers=owner).json()
    assert history['diagnoses'][0]['severity']=='moderate'
    assert transition(client,owner,case['id'],'open','closed',closed_date='2024-01-02').status_code==422
    assert transition(client,owner,case['id'],'open','closed',closed_date='2024-01-03').status_code==200
    assert client.post(path,headers=owner,json=data).status_code==409
    assert transition(client,owner,case['id'],'closed','open').status_code==200
    assert client.post(path,headers=owner,json={**data,'date':'2024-01-04','severity':'critical'}).status_code==201
    assert client.post('/api/v1/health/cases/'+str(uuid4())+'/diagnoses',headers=owner,json=data).status_code==404
    with factory() as db:
        event=db.get(EventModel,diagnosis['id'])
        assert event.animal_id==saved['id'] and event.event_type_id==2 and event.role_id
        audit=db.scalar(select(AuditModel).where(AuditModel.record_id==event.id))
        assert audit.new_values['severity']=='moderate' and audit.new_values['health_case_id']==case['id']
        assert db.scalar(select(func.count()).select_from(EventModel).where(EventModel.event_type_id==2))==2
