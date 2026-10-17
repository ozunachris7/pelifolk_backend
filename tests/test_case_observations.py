from sqlalchemy import select,func
from src.core.models import AuditModel,CaseObservationModel,EventModel,HealthCaseModel,RoleModel,RolePermissionModel
from tests.conftest import login
from tests.test_animals import animal


def observation(client,h,a,day='2024-02-01'):
    r=client.post('/api/v1/health/observations',headers=h,json={'animal_id':a['id'],'date':day,'observation':'Hallazgo original del trabajador.'})
    assert r.status_code==201,r.text
    return r.json()


def test_open_case_from_observation_preserves_original_and_authors(api):
    client,factory=api;owner=login(client);worker=login(client,'worker@example.com')
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'))
        db.add_all([RolePermissionModel(role_id=role.id,permission=p) for p in ['health:read','health:observations:create']])
    a=animal(client,owner,birth_date='2020-01-01');o=observation(client,worker,a)
    body={'animal_id':a['id'],'start_date':'2024-02-02','reason':'Caso derivado del hallazgo','observation_id':o['id']}
    result=client.post('/api/v1/health/cases',headers=owner,json=body);assert result.status_code==201,result.text
    case=result.json()
    detail=client.get('/api/v1/health/cases/'+case['id'],headers=owner).json()
    source=detail['observations'][0]
    assert source['id']==o['id'] and source['observation']==o['observation'] and source['recorded_by']==o['recorded_by']
    assert source['recorded_by'].startswith('Worker') and source['health_case']['id']==case['id']
    listing=client.get('/api/v1/health/observations',headers=owner).json()['items'][0]
    assert listing['health_case']['id']==case['id']
    assert client.get('/api/v1/health/animals/'+a['id']+'/history',headers=owner).json()['observations'][0]['health_case']['id']==case['id']
    assert client.post('/api/v1/health/cases',headers=owner,json=body).status_code==409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(HealthCaseModel))==1
        link=db.get(CaseObservationModel,o['id']);assert link.user_id!=db.get(EventModel,o['id']).user_id
        audit=db.scalar(select(AuditModel).where(AuditModel.table=='health_case_observations'))
        assert audit.new_values['health_case_id']==case['id'] and audit.record_id==o['id']
    assert client.get('/api/v1/audit?module=health&table=health_case_observations',headers=owner).json()['total']==1
    timeline=client.get('/api/v1/animals/'+a['id']+'/timeline?module=health',headers=owner).json()['items']
    assert {'label':'Caso sanitario vinculado','value':case['reason']} in next(i for i in timeline if i['title']=='Observación')['details']
    replacement=observation(client,owner,a,'2024-02-03')
    with factory.begin() as db:db.get(EventModel,replacement['id']).replaced_event_id=o['id']
    saved=client.get('/api/v1/health/cases/'+case['id'],headers=owner).json()['observations'][0]
    assert saved['id']==o['id'] and saved['observation']==o['observation'] and saved['recorded_by']==o['recorded_by']


def test_link_existing_options_same_animal_dates_and_idempotency(api):
    client,factory=api;h=login(client);a=animal(client,h);b=animal(client,h,name='Otra')
    o=observation(client,h,a)
    def case(animal,day):
        r=client.post('/api/v1/health/cases',headers=h,json={'animal_id':animal['id'],'start_date':day,'reason':'Seguimiento'});assert r.status_code==201;return r.json()
    old=case(a,'2024-01-01');valid=case(a,'2024-02-01');foreign=case(b,'2024-02-02')
    assert client.patch('/api/v1/health/cases/'+valid['id']+'/status',headers=h,json={'expected_status':'open','status':'closed','closed_date':'2024-02-03'}).status_code==200
    options=client.get('/api/v1/health/observations/'+o['id']+'/case-options',headers=h).json()
    assert [c['id'] for c in options]==[valid['id']]
    endpoint='/api/v1/health/observations/'+o['id']+'/case-link'
    assert client.post(endpoint,headers=h,json={'case_id':foreign['id']}).status_code==422
    assert client.post(endpoint,headers=h,json={'case_id':old['id']}).status_code==422
    linked=client.post(endpoint,headers=h,json={'case_id':valid['id']});assert linked.status_code==200 and linked.json()['status']=='closed'
    assert client.post(endpoint,headers=h,json={'case_id':valid['id']}).status_code==200
    other=case(a,'2024-02-03');assert client.post(endpoint,headers=h,json={'case_id':other['id']}).status_code==409
    with factory() as db:assert db.scalar(select(func.count()).select_from(AuditModel).where(AuditModel.table=='health_case_observations'))==1
    assert client.delete(endpoint,headers=h).status_code==405


def test_source_validation_and_read_only_access(api):
    client,factory=api;h=login(client);a=animal(client,h);o=observation(client,h,a)
    worker=login(client,'worker@example.com')
    for path in ['/case-options','/case-link']:
        endpoint='/api/v1/health/observations/'+o['id']+path
        action=client.get if path=='/case-options' else client.post
        kwargs={} if path=='/case-options' else {'json':{'case_id':'00000000-0000-4000-8000-000000000099'}}
        assert action(endpoint,headers=worker,**kwargs).status_code==403
        assert action(endpoint,**kwargs).status_code==401
    body={'animal_id':a['id'],'start_date':'2024-01-01','reason':'Caso','observation_id':o['id']}
    assert client.post('/api/v1/health/cases',headers=h,json=body).status_code==422
    with factory() as db:assert db.scalar(select(func.count()).select_from(HealthCaseModel))==0
    # Use a second valid observation as the replacement.
    replacement=observation(client,h,a,'2024-02-02')
    with factory.begin() as db:db.get(EventModel,replacement['id']).replaced_event_id=o['id']
    assert client.post('/api/v1/health/cases',headers=h,json={**body,'start_date':'2024-02-02'}).status_code==409
    assert client.get('/api/v1/health/observations/'+o['id']+'/case-options',headers=h).status_code==409
    assert client.post('/api/v1/health/cases',headers=h,json={**body,'start_date':'2024-02-02','observation_id':a['id']}).status_code==404
