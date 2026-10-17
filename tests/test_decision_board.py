from datetime import datetime,timezone
from sqlalchemy import select,func
from src.core.models import AnimalDecisionModel,AuditModel,RoleModel,RolePermissionModel
from tests.conftest import login
from tests.test_animals import animal
from tests.test_decisions import add
from tests.test_health import create_case
URL='/api/v1/management-decisions'


def test_latest_management_decision_is_selected_before_filters_and_context_does_not_replace(api):
    client,factory=api;h=login(client);a=animal(client,h,birth_date='2020-01-01')
    old=add(client,h,a,kind='sale_planned',date='2024-01-03').json()
    current=add(client,h,a,kind='retain_breeding',date='2024-01-04').json()
    add(client,h,a,kind='purchase_reason',date='2024-01-05');add(client,h,a,kind='other',date='2024-01-06')
    # A later-captured decision with an older clinical date cannot replace the newer plan.
    add(client,h,a,kind='separate',date='2024-01-02')
    r=client.get(URL,headers=h);assert r.status_code==200,r.text;p=r.json()
    assert p['total']==1 and p['items'][0]['decision']['id']==current['id']
    assert client.get(URL+'?kind=sale_planned',headers=h).json()['total']==0
    assert p['summary']['retain_breeding']==1 and p['summary']['sale_planned']==0
    assert client.get('/api/v1/animals/'+a['id']+'/decisions',headers=h).json()['total']==5
    assert client.get('/api/v1/animals/'+a['id'],headers=h).json()['is_breeder'] is False
    with factory() as db:assert db.get(AnimalDecisionModel,old['id']) is not None


def test_same_date_uses_capture_order_then_stable_id_and_preserves_history(api):
    client,factory=api;h=login(client);a=animal(client,h)
    first=add(client,h,a,kind='sale_planned').json();last=add(client,h,a,kind='separate').json()
    with factory.begin() as db:
        db.get(AnimalDecisionModel,first['id']).created_at=datetime(2024,1,3,10)
        db.get(AnimalDecisionModel,last['id']).created_at=datetime(2024,1,3,11)
    assert client.get(URL,headers=h).json()['items'][0]['decision']['id']==last['id']
    with factory.begin() as db:db.get(AnimalDecisionModel,last['id']).created_at=datetime(2024,1,3,10)
    expected=max(first['id'],last['id'])
    assert client.get(URL,headers=h).json()['items'][0]['decision']['id']==expected


def test_status_summary_pagination_search_and_no_implicit_sale(api):
    client,factory=api;h=login(client);a=animal(client,h,name='Luna',siniiga='BOARD-1',birth_date='2020-01-01');b=animal(client,h,name='Otra',siniiga='BOARD-2',sex='male',birth_date='2020-01-01')
    add(client,h,a,kind='sale_planned');add(client,h,b,kind='retain_breeding')
    with factory() as db:before=db.scalar(select(func.count()).select_from(AuditModel))
    p=client.get(URL+'?limit=1',headers=h).json();assert p['total']==2 and len(p['items'])==1 and sum(p['summary'].values())==2
    assert client.get(URL+'?q=%25',headers=h).json()['total']==0
    assert client.get(URL+'?sex=female',headers=h).json()['total']==1
    with factory() as db:assert db.scalar(select(func.count()).select_from(AuditModel))==before
    assert client.get('/api/v1/animals/'+a['id'],headers=h).json()['status']=='active'
    assert client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'exit_type':'sale','date':'2024-02-01','reason':'Venta registrada'}).status_code==201
    assert client.get(URL,headers=h).json()['total']==1
    exited=client.get(URL+'?status=exited',headers=h).json()['items'][0]
    assert exited['animal']['id']==a['id'] and exited['decision']['kind']=='sale_planned' and exited['status']=='sale'


def test_module_context_is_permission_gated_and_no_decision_means_no_candidate(api):
    client,factory=api;h=login(client);a=animal(client,h,birth_date='2020-01-01');add(client,h,a,kind='sale_planned')
    b=animal(client,h,birth_date='2020-01-01');add(client,h,b,kind='purchase_reason')
    create_case(client,h,a['id'],start_date='2024-01-10')
    owner=client.get(URL,headers=h).json()['items'][0];assert owner['health']['open_cases']==1 and owner['withdrawal']['status']=='no_records' and owner['breeding']['pregnancy'] is None
    assert client.get(URL).status_code==401
    worker=login(client,'worker@example.com');assert client.get(URL,headers=worker).status_code==403
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'));db.add(RolePermissionModel(role_id=role.id,permission='animals:read'))
    r=client.get(URL,headers=worker).json();assert r['total']==1;row=r['items'][0]
    assert 'health' not in row and 'withdrawal' not in row and 'breeding' not in row
    for params in ({'kind':'other'},{'limit':101},{'status':'bad'},{'sex':'bad'}):assert client.get(URL,headers=h,params=params).status_code==422


def test_birth_after_pregnancy_keeps_old_diagnosis_out_of_current_context(api):
    client,_=api;h=login(client);m=animal(client,h,birth_date='2020-01-01');f=animal(client,h,sex='male',birth_date='2019-01-01')
    add(client,h,m,kind='retain_breeding')
    mate=client.post('/api/v1/breeding/matings',headers=h,json={'animal_id':m['id'],'male_id':f['id'],'date':'2024-01-01'}).json()
    assert client.post('/api/v1/breeding/pregnancy-diagnoses',headers=h,json={'animal_id':m['id'],'date':'2024-02-01','result':'pregnant','mating_event_id':mate['id']}).status_code==201
    assert client.get(URL,headers=h).json()['items'][0]['breeding']['pregnancy']['result']=='pregnant'
    assert client.post('/api/v1/breeding/births',headers=h,json={'animal_id':m['id'],'date':'2024-06-01','birth_type_id':1,'offspring':[{'name':'Cría','sex':'female'}]}).status_code==201
    context=client.get(URL,headers=h).json()['items'][0]['breeding'];assert context['pregnancy'] is None and context['last_birth_date']=='2024-06-01'
