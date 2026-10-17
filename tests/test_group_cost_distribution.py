from decimal import Decimal
from sqlalchemy import select,func,delete
from src.core.models import AuditModel,ExpenseModel,ExpenseAllocationModel,GroupAnimalModel,RoleModel,RolePermissionModel,FeedPriceModel
from tests.conftest import login
from tests.test_animals import animal
from tests.test_finance import category
from tests.test_feeding import feed_setup
from src.features.finance.infrastructure.group_costs import split_cents


def assignment(client,h,g,ids,day):
    r=client.post(f"/api/v1/groups/{g['id']}/assignments",headers=h,json={'animal_ids':ids,'effective_date':day,'move_existing':True})
    assert r.status_code==201,r.text


def expense(client,h,g,cat,day,amount='100.01',shares=None):
    r=client.post('/api/v1/finance/expenses',headers=h,json={'category_id':cat['id'],'amount':amount,'date':day,'description':'Costo colectivo del lote'})
    assert r.status_code==201,r.text;e=r.json()
    r=client.put(f"/api/v1/finance/expenses/{e['id']}/allocations",headers=h,json={'allocations':shares or [{'kind':'group','target_id':g['id'],'percentage':'100'}]})
    assert r.status_code==200,r.text
    return e,r.json()['allocations']


def get(client,h,g,**params):
    r=client.get('/api/v1/finance/group-costs',headers=h,params={'kind':'group','target_id':g['id'],**params})
    assert r.status_code==200,r.text
    return r.json()


def test_historical_members_dates_remainders_pages_and_no_new_expenses(api):
    client,factory=api;h=login(client);cat=category(client,h,'expense','Manejo colectivo')
    a=animal(client,h,name='Luna',birth_date='2020-01-01');b=animal(client,h,name='Trueno',sex='male',birth_date='2020-01-01')
    g=client.post('/api/v1/groups',headers=h,json={'name':'Lote de manejo'}).json()
    assignment(client,h,g,[a['id']],'2024-06-01');assignment(client,h,g,[b['id']],'2024-06-02')
    e1,_=expense(client,h,g,cat,'2024-06-01');e2,alloc=expense(client,h,g,cat,'2024-06-02')
    with factory() as db:audits=db.scalar(select(func.count()).select_from(AuditModel))
    result=get(client,h,g,limit=1)
    assert result['total']==2 and len(result['items'])==1
    assert result['summary']['source_expenses']=='200.02' and result['summary']['attributed_expenses']=='200.02'
    detail=client.get(f"/api/v1/finance/group-costs/sources/expense/{alloc[0]['id']}",headers=h).json()
    values={r['animal']['id']:Decimal(r['amount']) for r in detail['items']}
    assert sum(values.values())==Decimal('100.01')
    assert values[min(values)]==Decimal('50.01')
    mine=client.get('/api/v1/finance/group-costs',headers=h,params={'kind':'animal','target_id':a['id']}).json()
    assert Decimal(mine['summary']['attributed_expenses'])==Decimal('100.01')+values[a['id']]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AuditModel))==audits
        assert db.scalar(select(func.count()).select_from(ExpenseAllocationModel))==2
    # A later move does not erase earlier membership.
    other=client.post('/api/v1/groups',headers=h,json={'name':'Otro lote'}).json();assignment(client,h,other,[a['id']],'2024-06-03')
    e3,_=expense(client,h,g,cat,'2024-06-03')
    day=get(client,h,g,date_from='2024-06-03',date_to='2024-06-03')
    assert [r['animal']['id'] for r in day['items']]==[b['id']] and day['items'][0]['expenses']=='100.01'
    assert client.get('/api/v1/finance/summary',headers=h).json()['expense_total']=='300.03'
    with factory() as db:
        count=db.scalar(select(func.count()).select_from(ExpenseModel));assert count==3
    assert get(client,h,g,date_from='2024-06-01',date_to='2024-06-01')['items'][0]['expenses']=='100.01'


def test_only_group_share_is_split_unoccupied_cost_and_same_day_exit(api):
    client,factory=api;h=login(client);cat=category(client,h,'expense','Servicios')
    a=animal(client,h,birth_date='2020-01-01');b=animal(client,h,name='Sol',birth_date='2020-01-01')
    g=client.post('/api/v1/groups',headers=h,json={'name':'Lote'}).json();assignment(client,h,g,[a['id'],b['id']],'2024-06-01')
    e,rows=expense(client,h,g,cat,'2024-06-01',amount='10.01',shares=[{'kind':'animal','target_id':a['id'],'percentage':'50'},{'kind':'group','target_id':g['id'],'percentage':'50'}])
    group_amount=next(r['amount'] for r in rows if r['kind']=='group')
    result=get(client,h,g)
    assert result['summary']['source_expenses']==group_amount
    assert sum(Decimal(r['expenses']) for r in result['items'])==Decimal(group_amount)
    r=client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'date':'2024-06-02','exit_type':'sale','reason':'Salida registrada.'});assert r.status_code==201,r.text
    expense(client,h,g,cat,'2024-06-02',amount='2.00')
    assert get(client,h,g,date_from='2024-06-02',date_to='2024-06-02')['total']==2
    expense(client,h,g,cat,'2024-06-03',amount='2.00')
    assert get(client,h,g,date_from='2024-06-03',date_to='2024-06-03')['total']==1
    expense(client,h,g,cat,'2024-05-31',amount='4.00')
    result=get(client,h,g,date_from='2024-05-31',date_to='2024-05-31',view='sources')
    assert result['summary']['unallocated_expenses']=='4.00' and result['items'][0]['member_count']==0


def test_feeding_costs_remain_separate_and_permission_gated(api):
    client,factory=api;h=login(client);a=animal(client,h,birth_date='2020-01-01');g=client.post('/api/v1/groups',headers=h,json={'name':'Alimentación'}).json();assignment(client,h,g,[a['id']],'2024-06-01')
    feed=feed_setup(client,factory,h)
    assert client.post(f"/api/v1/feeding/feeds/{feed['id']}/prices",headers=h,json={'effective_from':'2024-01-01','unit_cost':'1.005'}).status_code==201
    r=client.post('/api/v1/feeding/consumptions',headers=h,json={'feed_id':feed['id'],'group_id':g['id'],'quantity':'1','date':'2024-06-01'});assert r.status_code==201,r.text
    result=get(client,h,g);assert result['items'][0]['feeding']=='1.01' and result['summary']['attributed_feeding']=='1.01'
    w=login(client,'worker@example.com')
    assert client.get('/api/v1/finance/group-costs',headers=w,params={'kind':'group','target_id':g['id']}).status_code==403
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'));db.add(RolePermissionModel(role_id=role.id,permission='finance:read'))
    limited=get(client,w,g);assert 'source_feeding' not in limited['summary'] and limited['items']==[]
    assert client.get(f"/api/v1/finance/group-costs/sources/feeding/{r.json()['id']}",headers=w).status_code==403
    with factory.begin() as db:db.execute(delete(FeedPriceModel).where(FeedPriceModel.feed_id==feed['id']))
    missing=get(client,h,g);assert missing['summary']['unpriced_feeding']==1 and missing['items'][0]['unpriced_feeding']==1
    assert missing['items'][0]['feeding']=='0.00'
    with factory() as db:assert db.scalar(select(func.count()).select_from(ExpenseModel))==0


def test_cents_and_validation(api):
    assert split_cents(Decimal('0.01'),['b','a','c'])=={'a':Decimal('0.01'),'b':Decimal('0'),'c':Decimal('0')}
    assert split_cents(Decimal('10.00'),[])=={}
    client,_=api;h=login(client)
    assert client.get('/api/v1/finance/group-costs').status_code==401
    assert client.get('/api/v1/finance/group-costs',headers=h,params={'kind':'other','target_id':'no'}).status_code==422
