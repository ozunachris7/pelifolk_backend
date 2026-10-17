from decimal import Decimal
from sqlalchemy import select,func
from src.core.models import AuditModel,ExpenseModel,RoleModel,RolePermissionModel,IncomeModel
from tests.conftest import login
from tests.test_animals import animal
from tests.test_finance import category
from tests.test_group_cost_distribution import assignment,expense
from tests.test_feeding import feed_setup
from tests.test_doses import setup,dose


def test_direct_and_sale_income_expense_cases_and_group_shares_reconcile(api):
    client,factory=api;h=login(client);cat=category(client,h,'expense','Sanidad');inc=category(client,h,'income','Ingresos')
    a=animal(client,h,name='Luna',birth_date='2020-01-01');b=animal(client,h,name='Trueno',birth_date='2020-01-01')
    g=client.post('/api/v1/groups',headers=h,json={'name':'Reproductoras'}).json();assignment(client,h,g,[a['id'],b['id']],'2024-06-01')
    expense(client,h,g,cat,'2024-06-01','100.01')
    expense(client,h,g,cat,'2024-06-01','20.00',shares=[{'kind':'animal','target_id':a['id'],'percentage':'100'}])
    case=client.post('/api/v1/health/cases',headers=h,json={'animal_id':a['id'],'reason':'Seguimiento','start_date':'2024-06-01'}).json()
    expense(client,h,g,cat,'2024-06-01','10.00',shares=[{'kind':'health_case','target_id':case['id'],'percentage':'100'}])
    r=client.post('/api/v1/finance/incomes',headers=h,json={'category_id':inc['id'],'animal_id':a['id'],'amount':'200','date':'2024-06-02','description':'Ingreso atribuible a Luna'})
    assert r.status_code==201,r.text
    assert r.json()['animal']['id']==a['id'] and r.json()['sale'] is None
    assert client.get('/api/v1/finance/incomes/'+r.json()['id'],headers=h).json()['animal']['id']==a['id']
    history=client.get(f"/api/v1/animals/{a['id']}/timeline?module=finance",headers=h).json()
    assert any(i['title']=='Ingreso vinculado al animal' for i in history['items'])
    sale=client.post('/api/v1/exits',headers=h,json={'animal_id':b['id'],'date':'2024-06-02','exit_type':'sale','reason':'Venta'}).json()
    assert client.post('/api/v1/finance/incomes',headers=h,json={'category_id':inc['id'],'exit_event_id':sale['id'],'amount':'300','date':'2024-06-03'}).status_code==201
    with factory() as db:before=db.scalar(select(func.count()).select_from(AuditModel))
    result=client.get('/api/v1/finance/profitability?limit=1',headers=h).json()
    assert result['total']==2 and len(result['items'])==1
    assert result['summary']=={'income':'500.00','expenses':'130.01','result':'369.99'}
    assert result['coverage']['pending_expenses']=='0.00'
    arow=client.get('/api/v1/finance/profitability?q=luna',headers=h).json()['items'][0]
    assert arow['direct_expenses']=='20.00' and arow['case_expenses']=='10.00'
    assert Decimal(arow['result'])==Decimal('200')-Decimal(arow['expenses'])
    entries=client.get(f"/api/v1/finance/profitability/{a['id']}/entries?section=expenses&limit=1",headers=h).json()
    assert entries['total']==3 and len(entries['items'])==1
    assert client.get('/api/v1/finance/profitability?status=exited',headers=h).json()['items'][0]['animal']['id']==b['id']
    assert client.get('/api/v1/finance/profitability?date_from=2024-06-02&date_to=2024-06-03',headers=h).json()['summary']['expenses']=='0.00'
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AuditModel))==before
        assert db.scalar(select(func.count()).select_from(ExpenseModel))==3


def test_general_expenses_and_unlinked_income_pending_until_explicitly_attributed(api):
    client,factory=api;h=login(client);a=animal(client,h,birth_date='2020-01-01');cat=category(client,h,'expense','Generales');inc=category(client,h,'income','Otros')
    e=client.post('/api/v1/finance/expenses',headers=h,json={'category_id':cat['id'],'amount':'120','date':'2024-06-01'}).json()
    income=client.post('/api/v1/finance/incomes',headers=h,json={'category_id':inc['id'],'amount':'200','date':'2024-06-01'}).json()
    data=client.get('/api/v1/finance/profitability',headers=h).json()
    assert data['coverage']['status']=='pending_attribution' and data['coverage']['pending_expenses']=='120.00' and data['coverage']['pending_income']=='200.00'
    assert data['summary']['result']=='0.00'
    pending=client.get('/api/v1/finance/profitability/pending?kind=expenses',headers=h).json()
    assert pending['items'][0]['record']['id']==e['id'] and pending['items'][0]['pending_amount']=='120.00'
    assert client.put(f"/api/v1/finance/expenses/{e['id']}/allocations",headers=h,json={'allocations':[{'kind':'animal','target_id':a['id'],'percentage':'100'}]}).status_code==200
    r=client.put('/api/v1/finance/incomes/'+income['id'],headers=h,json={'category_id':inc['id'],'animal_id':a['id'],'amount':'200','date':'2024-06-01'})
    assert r.status_code==200,r.text
    data=client.get('/api/v1/finance/profitability',headers=h).json()
    assert data['coverage']['status']=='attributed_records' and data['summary']['result']=='80.00'
    assert client.get('/api/v1/finance/incomes?q='+a['name'],headers=h).json()['total']==1


def test_consumption_is_reference_and_never_added_to_financial_expenses(api):
    client,factory=api;h=login(client);a,c,p,t=setup(client,h)
    feed=feed_setup(client,factory,h)
    assert client.post('/api/v1/feeding/feeds/'+feed['id']+'/prices',headers=h,json={'effective_from':'2024-01-01','unit_cost':'10'}).status_code==201
    assert client.post('/api/v1/feeding/consumptions',headers=h,json={'feed_id':feed['id'],'animal_id':a['id'],'quantity':'2','date':'2024-01-03'}).status_code==201
    assert client.post(f"/api/v1/health/products/{p['id']}/prices",headers=h,json={'effective_from':'2024-01-01','cost':'0.50'}).status_code==201
    assert dose(client,h,t,p).status_code==201
    cat=category(client,h,'expense','Compra registrada')
    e=client.post('/api/v1/finance/expenses',headers=h,json={'category_id':cat['id'],'amount':'100','date':'2024-01-03'}).json()
    assert client.put(f"/api/v1/finance/expenses/{e['id']}/allocations",headers=h,json={'allocations':[{'kind':'animal','target_id':a['id'],'percentage':'100'}]}).status_code==200
    row=client.get('/api/v1/finance/profitability',headers=h).json()['items'][0]
    assert row['expenses']=='100.00' and row['result']=='-100.00'
    assert row['feeding']['known_cost']=='20.00' and row['medicines']['known_cost']=='1.00'
    w=login(client,'worker@example.com')
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'));db.add(RolePermissionModel(role_id=role.id,permission='finance:read'))
    limited=client.get('/api/v1/finance/profitability',headers=w).json()['items'][0]
    assert 'feeding' not in limited and 'medicines' not in limited and limited['result']=='-100.00'
    assert client.get(f"/api/v1/finance/profitability/{a['id']}/entries?section=medicines",headers=w).status_code==403
    assert client.get('/api/v1/finance/profitability').status_code==401


def test_direct_income_validation_and_conflicting_attribution(api):
    client,_=api;h=login(client);inc=category(client,h,'income','Ingreso');a=animal(client,h,birth_date='2020-01-01')
    data={'category_id':inc['id'],'animal_id':a['id'],'amount':'1','date':'2019-01-01'}
    assert client.post('/api/v1/finance/incomes',headers=h,json=data).status_code==422
    sale=client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'date':'2024-06-01','exit_type':'sale','reason':'Venta'}).json()
    assert client.post('/api/v1/finance/incomes',headers=h,json={**data,'date':'2024-06-01','exit_event_id':sale['id']}).status_code==422
    assert client.get('/api/v1/finance/profitability?date_from=2025-01-01&date_to=2024-01-01',headers=h).status_code==422
    assert client.get('/api/v1/finance/profitability?date_to=2019-12-31',headers=h).json()['items'][0]['status']=='not_born'
    assert client.get('/api/v1/finance/profitability?date_to=2019-12-31&status=exited',headers=h).json()['total']==0


def test_exact_animal_filter_and_activity_counts(api):
    client, _ = api
    h = login(client)
    a = animal(client,h,name='Luna',birth_date='2020-01-01')
    b = animal(client,h,name='Luna',birth_date='2020-01-01')
    inc = category(client,h,'income','Otros')
    empty = client.get('/api/v1/finance/profitability',headers=h,params={'animal_id':a['id']}).json()
    assert empty['total'] == 1 and empty['items'][0]['animal']['id'] == a['id']
    assert empty['activity'] == {'income_count':0,'expense_count':0}
    r = client.post('/api/v1/finance/incomes',headers=h,json={'category_id':inc['id'],'animal_id':b['id'],'amount':'0','date':'2024-06-01'})
    assert r.status_code == 201, r.text
    selected = client.get('/api/v1/finance/profitability',headers=h,params={'animal_id':b['id']}).json()
    assert selected['total'] == 1 and selected['activity']['income_count'] == 1
    assert selected['summary']['income'] == '0.00'
    assert client.get('/api/v1/finance/profitability',headers=h,params={'animal_id':'invalid'}).status_code == 422
