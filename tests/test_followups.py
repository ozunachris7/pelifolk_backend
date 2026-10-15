from datetime import date,timedelta
from sqlalchemy import select,func
from src.core.models import CaseFollowupModel,AuditModel
from tests.conftest import login
from tests.test_animals import animal
from tests.test_health import create_case,transition
from tests.test_treatments import product


def add(client,h,case_id,**values):
    return client.post('/api/v1/health/cases/'+case_id+'/followups',headers=h,json={
        'date':'2024-01-03','evolution':'improved','notes':'Camina con menor dificultad.',
        'next_review_date':str(date.today()),**values})


def setup(client,h):
    a=animal(client,h);c=create_case(client,h,a['id']).json();return a,c


def test_history_audit_pending_and_close(api):
    client,factory=api;h=login(client);a,c=setup(client,h)
    r=add(client,h,c['id']);assert r.status_code==201,r.text
    record=r.json();assert record['notes']=='Camina con menor dificultad.'
    detail=client.get('/api/v1/health/cases/'+c['id'],headers=h).json()
    assert detail['followups'][0]['id']==record['id']
    assert client.get('/api/v1/health/animals/'+a['id']+'/history',headers=h).json()['followups'][0]['id']==record['id']
    reviews=client.get('/api/v1/health/reviews',headers=h).json()
    assert reviews['total']==1 and reviews['items'][0]['status']=='due'
    assert transition(client,h,c['id'],'open','closed',closed_date='2024-01-02').status_code==422
    assert transition(client,h,c['id'],'open','closed',closed_date='2024-01-03').status_code==200
    assert client.get('/api/v1/health/reviews?state=all',headers=h).json()['total']==0
    assert add(client,h,c['id']).status_code==409
    with factory() as db:
        audit=db.scalar(select(AuditModel).where(AuditModel.record_id==record['id']))
        assert audit.table=='health_case_followups' and audit.new_values['evolution']=='improved'
        assert db.scalar(select(func.count()).select_from(CaseFollowupModel))==1
    assert client.get('/api/v1/audit?module=health',headers=h).json()['total']>=2


def test_latest_by_clinical_date_and_cancelled_review(api):
    client,_=api;h=login(client);a,c=setup(client,h)
    assert add(client,h,c['id'],date='2024-01-05',next_review_date=str(date.today()+timedelta(days=3))).status_code==201
    assert add(client,h,c['id'],date='2024-01-04',next_review_date='2024-01-06').status_code==201
    assert client.get('/api/v1/health/reviews',headers=h).json()['total']==0
    page=client.get('/api/v1/health/reviews?state=upcoming',headers=h).json()
    assert page['total']==1 and page['items'][0]['followup']['date']=='2024-01-05'
    response=add(client,h,c['id'],date='2024-01-06',next_review_date=None)
    assert response.status_code==201,response.text
    assert client.get('/api/v1/health/reviews?state=all',headers=h).json()['total']==0


def test_result_requires_case_treatment_and_backdated_exit_conflicts(api):
    client,_=api;h=login(client);a,c=setup(client,h)
    assert add(client,h,c['id'],treatment_result='effective').status_code==422
    p=product(client,h).json()
    assert client.post('/api/v1/health/cases/'+c['id']+'/treatments',headers=h,json={
        'product_id':p['id'],'start_date':'2024-01-02','dose_value':'1','dose_unit_id':1,
        'route_id':1,'duration_days':1}).status_code==201
    assert add(client,h,c['id'],treatment_result='partially_effective',date='2024-01-04').status_code==201
    assert client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'exit_type':'death','date':'2024-01-03','reason':'Baja'}).status_code==422
    assert client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'exit_type':'death','date':'2024-01-04','reason':'Baja'}).status_code==201
    assert client.get('/api/v1/health/reviews?state=all',headers=h).json()['total']==0
    assert add(client,h,c['id'],date='2024-01-05').status_code==409


def test_validation_permissions_and_read_only_records(api):
    client,factory=api;h=login(client);_,c=setup(client,h);worker=login(client,'worker@example.com')
    for values in [{'date':'2023-12-31'},{'date':str(date.today()+timedelta(days=1))},
                   {'notes':'  '},{'next_review_date':'2024-01-02'}, {'evolution':'bad'},
                   {'treatment_result':'bad'},{'user_id':'forged'}]:
        assert add(client,h,c['id'],**values).status_code==422
    assert add(client,worker,c['id']).status_code==403
    assert client.get('/api/v1/health/reviews',headers=worker).status_code==403
    assert client.get('/api/v1/health/reviews').status_code==401
    assert client.get('/api/v1/health/reviews?limit=101',headers=h).status_code==422
    with factory() as db:assert db.scalar(select(func.count()).select_from(CaseFollowupModel))==0
    record=add(client,h,c['id']).json()
    for method in ['put','delete']:
        assert getattr(client,method)('/api/v1/health/cases/'+c['id']+'/followups',headers=h).status_code==405
    page=client.get('/api/v1/health/reviews?q=no-match',headers=h).json();assert page['total']==0
