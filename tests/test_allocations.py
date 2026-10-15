from decimal import Decimal
from sqlalchemy import select
from src.core.models import AuditModel, ExpenseAllocationModel, RoleModel, RolePermissionModel
from tests.conftest import login
from tests.test_animals import animal
from tests.test_finance import category
from tests.test_feeding import feed_setup


def expense(client,h,amount='100.01'):
    cat=category(client,h,'expense','Sanidad')
    r=client.post('/api/v1/finance/expenses',headers=h,json={'category_id':cat['id'],'amount':amount,'date':'2024-06-01','description':'Atención del hato'})
    assert r.status_code==201,r.text
    return r.json(),cat


def test_allocations_atomic_rounding_editing_costs_and_clear(api):
    client,factory=api;h=login(client);e,cat=expense(client,h)
    a=animal(client,h,name='Luna');b=animal(client,h,name='Sol');g=client.post('/api/v1/groups',headers=h,json={'name':'Reproductoras'}).json()
    path='/api/v1/finance/expenses/'+e['id']+'/allocations'
    before=client.get(path,headers=h).json();assert before['allocations']==[] and before['unassigned_amount']=='100.01'
    shares=[{'kind':'animal','target_id':a['id'],'percentage':'33.33'},{'kind':'animal','target_id':b['id'],'percentage':'33.33'},{'kind':'group','target_id':g['id'],'percentage':'33.34'}]
    r=client.put(path,headers=h,json={'allocations':shares});assert r.status_code==200,r.text
    saved=r.json();assert saved['assigned_amount']=='100.01' and saved['unassigned_amount']=='0.00'
    assert sum(Decimal(s['amount']) for s in saved['allocations'])==Decimal('100.01')
    assert next(s['amount'] for s in saved['allocations'] if s['kind']=='group')=='33.35'
    assert client.get('/api/v1/finance/expenses',headers=h).json()['items'][0]['allocation_count']==3
    assert client.get('/api/v1/finance/summary',headers=h).json()['expense_total']=='100.01'
    cost=client.get('/api/v1/finance/costs',headers=h,params={'kind':'animal','target_id':a['id']}).json()
    assert cost['assigned_expenses']=='33.33' and cost['total']==1 and cost['feeding']['total_cost']=='0.00'
    for invalid in ([{**shares[0],'percentage':'99'}],[shares[0],{**shares[0],'percentage':'66.67'}],[{**shares[0],'percentage':'NaN'}],[{**shares[0],'percentage':'100','target_id':'00000000-0000-4000-8000-000000000099'}]):
        assert client.put(path,headers=h,json={'allocations':invalid}).status_code==422
        assert client.get(path,headers=h).json()==saved
    assert client.put('/api/v1/finance/expenses/'+e['id'],headers=h,json={'category_id':cat['id'],'amount':'200.02','date':'2024-06-01'}).status_code==200
    edited=client.get(path,headers=h).json();assert edited['assigned_amount']=='200.02' and len(edited['allocations'])==3
    assert client.put(path,headers=h,json={'allocations':[]}).status_code==200
    assert client.get(path,headers=h).json()['unassigned_amount']=='200.02'
    assert client.get('/api/v1/finance/costs',headers=h,params={'kind':'group','target_id':g['id']}).json()['assigned_expenses']=='0.00'
    with factory() as db:
        audit=db.scalars(select(AuditModel).where(AuditModel.table=='expense_allocations')).all()
        assert len(audit)==2 and audit[-1].old_values['allocations'] and audit[-1].new_values['allocations']==[]
        assert db.scalars(select(ExpenseAllocationModel)).all()==[]


def test_case_allocations_feeding_separate_period_and_permission(api):
    client,factory=api;h=login(client);e,_=expense(client,h,'120.00');a=animal(client,h,birth_date='2020-01-01')
    r=client.post('/api/v1/health/cases',headers=h,json={'animal_id':a['id'],'reason':'Seguimiento','start_date':'2024-06-01'});assert r.status_code==201,r.text;case=r.json()
    path='/api/v1/finance/expenses/'+e['id']+'/allocations'
    r=client.put(path,headers=h,json={'allocations':[{'kind':'animal','target_id':a['id'],'percentage':'50'},{'kind':'health_case','target_id':case['id'],'percentage':'50'}]});assert r.status_code==200,r.text
    feed=feed_setup(client,factory,h);client.post('/api/v1/feeding/feeds/'+feed['id']+'/prices',headers=h,json={'effective_from':'2024-01-01','unit_cost':'10'})
    assert client.post('/api/v1/feeding/consumptions',headers=h,json={'animal_id':a['id'],'feed_id':feed['id'],'quantity':'2','date':'2024-06-01'}).status_code==201
    f={'kind':'animal','target_id':a['id'],'date_from':'2024-06-01','date_to':'2024-06-01','limit':1}
    data=client.get('/api/v1/finance/costs',headers=h,params=f).json()
    assert data['assigned_expenses']=='120.00' and data['total']==2 and len(data['items'])==1
    assert data['feeding']=={'total':1,'unpriced_count':0,'total_cost':'20.00'}
    assert client.get('/api/v1/finance/summary',headers=h).json()['expense_total']=='120.00'
    assert client.get('/api/v1/finance/costs',headers=h,params={**f,'date_from':'2024-06-02','date_to':'2024-06-02'}).json()['assigned_expenses']=='0.00'
    worker=login(client,'worker@example.com')
    for url in (path,'/api/v1/finance/allocation-options','/api/v1/finance/costs?kind=animal&target_id='+a['id']):
        assert client.get(url).status_code==401 and client.get(url,headers=worker).status_code==403
    assert client.put(path,headers=worker,json={'allocations':[]}).status_code==403
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'));db.add(RolePermissionModel(role_id=role.id,permission='finance:read'))
    limited=client.get('/api/v1/finance/costs',headers=worker,params=f);assert limited.status_code==200,limited.text;assert limited.json()['feeding'] is None
    assert client.get(path,headers=worker).status_code==200
    assert client.put(path,headers=worker,json={'allocations':[]}).status_code==403
