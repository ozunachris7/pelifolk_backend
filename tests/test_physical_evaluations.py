from datetime import date,timedelta
from sqlalchemy import select
from src.core.models import PhysicalEvaluationModel,AuditModel,RoleModel,RolePermissionModel
from tests.conftest import login
from tests.test_animals import animal
URL='/api/v1/physical-evaluations'

def record(client,h,a,**changes):
    return client.post(URL,headers=h,json={'animal_id':a['id'],'date':'2024-01-04','evaluated_by':'Evaluador del rancho','rubric_version':'descriptive_v1','findings':{'body_structure':'Proporciones descritas durante la revisión.'},**changes})


def test_descriptive_criteria_preserve_snapshot_evaluator_and_recorder(api):
    client,factory=api;h=login(client);a=animal(client,h,birth_date='2020-01-01')
    criteria=client.get(URL+'/criteria',headers=h).json();assert criteria['scoring']=='descriptive' and len(criteria['criteria'])==4
    result=record(client,h,a);assert result.status_code==201,result.text;r=result.json()
    assert r['evaluated_by']=='Evaluador del rancho' and r['recorded_by'].startswith('Owner')
    assert r['findings'][0]['observation']=='Proporciones descritas durante la revisión.'
    assert r['findings'][1]['observation'] is None and 'score' not in r
    assert r['findings'][0]['description']==criteria['criteria'][0]['description']
    with factory() as db:
        row=db.get(PhysicalEvaluationModel,r['id']);assert row.role_id and row.user_id
        audit=db.scalar(select(AuditModel).where(AuditModel.table=='physical_evaluations'))
        assert audit.new_values['findings']==r['findings'] and audit.new_values['evaluated_by']==r['evaluated_by']
    timeline=client.get('/api/v1/animals/'+a['id']+'/timeline?module=animals',headers=h).json()['items']
    item=next(i for i in timeline if i['kind']=='physical_evaluation')
    assert {'label':'Evaluada por','value':r['evaluated_by']} in item['details']
    assert {'label':'Patas y aplomos','value':'Sin evaluar'} in item['details']
    assert client.get('/api/v1/audit?module=animals&table=physical_evaluations',headers=h).json()['total']==1
    for method in ('put','delete'):assert getattr(client,method)(URL,headers=h).status_code==405


def test_validation_permissions_and_no_invented_scores(api):
    client,factory=api;h=login(client);a=animal(client,h,birth_date='2020-01-01');worker=login(client,'worker@example.com')
    assert client.get(URL).status_code==401 and client.get(URL,headers=worker).status_code==403
    for changes in ({'findings':{}},{'findings':{'body_structure':' '}},{'findings':{'score':5}},
                    {'score':10},{'user_id':a['id']},{'evaluated_by':' '},{'date':'2019-01-01'},
                    {'date':(date.today()+timedelta(days=1)).isoformat()}):
        assert record(client,h,a,**changes).status_code==422,changes
    assert record(client,h,a,rubric_version='invented_scale').status_code==409
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'));db.add(RolePermissionModel(role_id=role.id,permission='animals:read'))
    assert client.get(URL,headers=worker).status_code==200 and client.get(URL+'/criteria',headers=worker).status_code==200
    assert record(client,worker,a).status_code==403
    assert client.get(URL+'?limit=101',headers=h).status_code==422


def test_history_is_paginated_and_does_not_rewrite_prior_evaluations(api):
    client,_=api;h=login(client);a=animal(client,h,siniiga='PHY-001',birth_date='2020-01-01');other=animal(client,h,siniiga='PHY-OTHER',birth_date='2020-01-01')
    first=record(client,h,a).json();second=record(client,h,a,date='2024-01-05',findings={'movement':'Se describió el desplazamiento durante la revisión.'}).json()
    record(client,h,other)
    listing=client.get(URL,headers=h,params={'animal_id':a['id'],'limit':1,'offset':1}).json()
    assert listing['total']==2 and listing['items'][0]==first
    assert client.get(URL,headers=h,params={'q':'PHY-001'}).json()['total']==2
    assert client.get(URL,headers=h,params={'q':'%'}).json()['total']==0
    assert second['findings'][0]['observation'] is None


def test_physical_evaluation_dates_protect_birth_and_exit(api):
    client,_=api;h=login(client);a=animal(client,h,birth_date='2020-01-01');assert record(client,h,a).status_code==201
    assert client.put('/api/v1/animals/'+a['id'],headers=h,json={'name':'Luna','sex':'female','birth_date':'2024-01-05'}).status_code==422
    exit_data={'animal_id':a['id'],'date':'2024-01-03','exit_type':'sale','reason':'Venta'}
    assert client.post('/api/v1/exits',headers=h,json=exit_data).status_code==422
    assert client.post('/api/v1/exits',headers=h,json={**exit_data,'date':'2024-01-05'}).status_code==201
    assert record(client,h,a,date='2024-01-06').status_code==409
    assert all(x['id']!=a['id'] for x in client.get(URL+'/animal-options',headers=h).json())
