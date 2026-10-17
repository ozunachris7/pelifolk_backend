from sqlalchemy import select,func
from src.core.models import AuditModel,RoleModel,RolePermissionModel
from tests.conftest import login
from tests.test_animals import animal
from tests.test_health import create_case,transition
URL='/api/v1/breeding/performance'

def family(client,h):
    m=animal(client,h,name='Luna',sex='female',birth_date='2020-01-01');f=animal(client,h,name='Trueno',sex='male',birth_date='2020-01-01')
    a=animal(client,h,name='Estrella',birth_date='2024-01-01',mother_id=m['id'],father_id=f['id'])
    b=animal(client,h,name='Lucero',birth_date='2024-02-01',mother_id=m['id'],father_id=f['id'])
    return m,f,a,b

def endpoint(m,c):return URL+'/'+m['id']+'/offspring/'+c['id']+'/health-cases'


def test_health_case_counts_are_per_child_without_duplicate_affected_offspring(api):
    client,factory=api;h=login(client);m,f,a,b=family(client,h)
    one=create_case(client,h,a['id'],start_date='2024-03-01',reason='Hallazgo A').json()
    two=create_case(client,h,a['id'],start_date='2024-04-01',reason='Hallazgo B').json()
    assert transition(client,h,two['id'],'open','under_treatment').status_code==200
    three=create_case(client,h,b['id'],start_date='2024-05-01',reason='Hallazgo C').json()
    assert transition(client,h,three['id'],'open','closed',closed_date='2024-05-02').status_code==200
    with factory() as db:before=db.scalar(select(func.count()).select_from(AuditModel))
    expected=dict(total_cases=3,open_cases=1,under_treatment_cases=1,closed_cases=1,offspring_with_cases=2,offspring_without_cases=0)
    for sex,parent in [('female',m),('male',f)]:
        page=client.get(URL,headers=h,params={'sex':sex,'limit':1}).json();row=page['items'][0]
        assert row['health']==expected and page['health_summary']==expected
        children=client.get(URL+'/'+parent['id']+'/offspring',headers=h).json()['items']
        child=next(c for c in children if c['animal']['id']==a['id']);assert child['health']['total_cases']==2
        cases=client.get(endpoint(parent,a),headers=h,params={'limit':1}).json()
        assert cases['total']==2 and len(cases['items'])==1 and cases['items'][0]['id']==two['id']
    with factory() as db:assert db.scalar(select(func.count()).select_from(AuditModel))==before


def test_health_permissions_omit_every_health_field_and_protect_the_detail(api):
    client,factory=api;h=login(client);m,f,a,b=family(client,h);create_case(client,h,a['id'],start_date='2024-03-01',reason='Dato sanitario')
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'));db.add(RolePermissionModel(role_id=role.id,permission='breeding:read'))
    worker=login(client,'worker@example.com')
    page=client.get(URL,headers=worker).json();assert 'health_summary' not in page and 'health' not in page['items'][0]
    children=client.get(URL+'/'+m['id']+'/offspring',headers=worker).json();assert 'health' not in children['parent'] and all('health' not in c for c in children['items'])
    assert client.get(endpoint(m,a),headers=worker).status_code==403
    assert client.get(endpoint(m,a)).status_code==401
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'));db.add(RolePermissionModel(role_id=role.id,permission='health:read'))
    assert client.get(endpoint(m,a),headers=worker).status_code==200
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'));db.delete(db.get(RolePermissionModel,(role.id,'breeding:read')))
    assert client.get(endpoint(m,a),headers=worker).status_code==403


def test_birth_cohort_is_separate_from_case_dates_and_archived_children_remain_visible(api):
    client,_=api;h=login(client);m,f,a,b=family(client,h)
    case=create_case(client,h,a['id'],start_date='2024-06-01',reason='Caso posterior al periodo de nacimientos').json()
    assert client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'date':'2024-07-01','exit_type':'sale','reason':'Venta registrada'}).status_code==201
    create_case(client,h,b['id'],start_date='2024-06-01')
    period={'date_from':'2024-01-01','date_to':'2024-01-31'}
    page=client.get(URL,headers=h,params=period).json();assert page['items'][0]['health']['total_cases']==1
    detail=client.get(endpoint(m,a),headers=h,params=period);assert detail.status_code==200,detail.text
    assert detail.json()['items'][0]['id']==case['id']
    assert client.get(endpoint(m,b),headers=h,params=period).status_code==404
    no_cases=client.get(URL,headers=h,params={'date_from':'2024-03-01'}).json()['items'][0]['health'];assert no_cases['total_cases']==0 and no_cases['offspring_with_cases']==0


def test_detail_checks_parentage_pagination_and_unknown_is_not_healthy(api):
    client,_=api;h=login(client);m,f,a,b=family(client,h);other=animal(client,h,name='Otra madre',birth_date='2020-01-01')
    assert client.get(endpoint(other,a),headers=h).status_code==404
    assert client.get(endpoint(m,a)+'?limit=101',headers=h).status_code==422
    data=client.get(URL,headers=h).json()['items'][0]['health'];assert data['offspring_without_cases']==2 and data['total_cases']==0
    assert client.get(endpoint(m,a),headers=h).json()['total']==0


def test_health_summary_includes_all_filtered_parents_not_only_page(api):
    client,_=api;h=login(client);m,f,a,b=family(client,h)
    other=animal(client,h,name='Otra madre',birth_date='2020-01-01');child=animal(client,h,name='Otra cría',birth_date='2024-01-01',mother_id=other['id'])
    create_case(client,h,a['id'],start_date='2024-03-01');create_case(client,h,child['id'],start_date='2024-03-01')
    page=client.get(URL,headers=h,params={'limit':1}).json()
    assert page['total']==2 and len(page['items'])==1 and page['health_summary']['total_cases']==2
    assert page['health_summary']['offspring_with_cases']==2 and page['health_summary']['offspring_without_cases']==1
    filtered=client.get(URL,headers=h,params={'q':'Luna'}).json();assert filtered['health_summary']['total_cases']==1 and filtered['health_summary']['offspring_with_cases']==1
