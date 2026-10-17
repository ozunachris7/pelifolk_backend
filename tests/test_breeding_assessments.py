from datetime import date,timedelta
from sqlalchemy import select,func
from src.core.models import AuditModel,BreedingAssessmentModel,EventModel,RoleModel,RolePermissionModel
from tests.conftest import login
from tests.test_animals import animal
URL='/api/v1/breeding/assessments'

def setup(client,h):
    m=animal(client,h,name='Luna',birth_date='2020-01-01');f=animal(client,h,name='Trueno',sex='male',birth_date='2019-01-01')
    r=client.post('/api/v1/breeding/births',headers=h,json={'animal_id':m['id'],'father_id':f['id'],'date':'2024-06-01','birth_type_id':1,'offspring':[{'name':'Estrella','sex':'female'}]})
    assert r.status_code==201,r.text
    b=r.json();return m,f,b,b['offspring'][0]['animal']

def record(client,h,b,**changes):
    return client.post(URL,headers=h,json={'birth_event_id':b['id'],'kind':'maternal','date':'2024-06-02','evaluated_by':'Persona evaluadora','rubric_version':'breeding_descriptive_v1','findings':{'acceptance':'Se registró el contacto observado con la cría.'},**changes})


def test_maternal_and_offspring_preserve_birth_criteria_and_distinct_authorship(api):
    client,factory=api;h=login(client);m,f,b,c=setup(client,h)
    r=record(client,h,b);assert r.status_code==201,r.text;maternal=r.json()
    r=record(client,h,b,kind='offspring',offspring_id=c['id'],findings={'body_features':'Rasgos visibles descritos.'});assert r.status_code==201,r.text;child=r.json()
    assert maternal['animal']['id']==m['id'] and maternal['father'] is None
    assert child['animal']['id']==c['id'] and child['father']['id']==f['id'] and child['mother']['id']==m['id']
    assert child['findings'][1]['observation'] is None and 'score' not in child
    assert maternal['evaluated_by']=='Persona evaluadora' and maternal['recorded_by'].startswith('Owner')
    for a,total in [(m,2),(f,1),(c,1)]:
        assert client.get(URL,headers=h,params={'animal_id':a['id']}).json()['total']==total
        timeline=client.get('/api/v1/animals/'+a['id']+'/timeline?module=breeding',headers=h).json()['items']
        assert sum(i['kind']=='breeding_assessment' for i in timeline)==total
    with factory() as db:
        row=db.get(BreedingAssessmentModel,child['id']);assert row.role_id and row.user_id
        audit=db.scalar(select(AuditModel).where(AuditModel.table=='breeding_assessments',AuditModel.record_id==row.id))
        assert audit.new_values['findings']==child['findings'] and audit.new_values['father_id']==f['id']
    assert client.get('/api/v1/audit?module=breeding&table=breeding_assessments',headers=h).json()['total']==2
    for method in ('put','delete'):assert getattr(client,method)(URL,headers=h).status_code==405


def test_invalid_criteria_membership_dates_and_future_are_rejected(api):
    client,_=api;h=login(client);m,f,b,c=setup(client,h);other=animal(client,h,birth_date='2020-01-01')
    for values in ({'findings':{}},{'findings':{'acceptance':' '}},{'findings':{'score':'5'}},{'score':5},
          {'findings':{'movement':'Wrong kind'}},{'findings':{'acceptance':'a'*2001}},{'user_id':m['id']},
          {'evaluated_by':' '},{'date':'2024-05-31'},{'date':(date.today()+timedelta(days=1)).isoformat()},
          {'offspring_id':c['id']},{'kind':'offspring','findings':{'body_features':'Observed'}},
          {'kind':'offspring','offspring_id':other['id'],'findings':{'body_features':'Observed'}}):
        assert record(client,h,b,**values).status_code==422,values
    assert record(client,h,b,rubric_version='invented').status_code==409
    assert record(client,h,other).status_code==422


def test_effective_birth_options_and_replaced_birth_history(api):
    client,factory=api;h=login(client);m,f,b,c=setup(client,h);r=record(client,h,b).json()
    page=client.get(URL+'/birth-options',headers=h,params={'q':'Luna','limit':1}).json()
    assert page['total']==1 and page['items'][0]['offspring'][0]['animal']['id']==c['id']
    assert client.get(URL+'/birth-options',headers=h,params={'q':'%'}).json()['total']==0
    with factory.begin() as db:
        old=db.get(EventModel,b['id']);db.add(EventModel(animal_id=m['id'],event_type_id=7,date=old.date,user_id=old.user_id,role_id=old.role_id,replaced_event_id=old.id))
    assert client.get(URL+'/birth-options',headers=h).json()['total']==0
    assert record(client,h,b).status_code==409
    retained=client.get(URL,headers=h).json()['items'][0];assert retained['id']==r['id'] and retained['birth_replaced']


def test_permissions_prevent_clinical_scope_leakage_and_allow_read_only(api):
    client,factory=api;h=login(client);m,f,b,c=setup(client,h);record(client,h,b);worker=login(client,'worker@example.com')
    assert client.get(URL).status_code==401 and client.get(URL,headers=worker).status_code==403
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'));db.add(RolePermissionModel(role_id=role.id,permission='animals:read'))
    timeline=client.get('/api/v1/animals/'+m['id']+'/timeline',headers=worker).json()['items'];assert not any(i['kind']=='breeding_assessment' for i in timeline)
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'));db.add(RolePermissionModel(role_id=role.id,permission='breeding:read'))
    assert client.get(URL,headers=worker).status_code==200 and record(client,worker,b).status_code==403
    assert client.get(URL+'?limit=101',headers=h).status_code==422


def test_revisions_preserve_prior_observations_and_subject_exit_dates(api):
    client,_=api;h=login(client);m,f,b,c=setup(client,h);first=record(client,h,b).json()
    second=record(client,h,b,date='2024-06-03',findings={'care':'Nueva observación del cuidado.'}).json()
    page=client.get(URL,headers=h,params={'birth_event_id':b['id'],'offset':1,'limit':1}).json();assert page['total']==2 and page['items'][0]==first
    exit_data={'animal_id':m['id'],'date':'2024-06-02','exit_type':'sale','reason':'Venta'}
    assert client.post('/api/v1/exits',headers=h,json=exit_data).status_code==422
    assert client.post('/api/v1/exits',headers=h,json={**exit_data,'date':'2024-06-03'}).status_code==201
    assert record(client,h,b,date='2024-06-04').status_code==409
    # A child can be evaluated after its mother leaves; the subject is the child.
    r=record(client,h,b,kind='offspring',offspring_id=c['id'],date='2024-06-04',findings={'development':'Conducta observada de la cría.'});assert r.status_code==201,r.text
