from datetime import date, timedelta
from sqlalchemy import select
from src.core.models import AuditModel, IncomeModel
from tests.conftest import login
from tests.test_animals import animal


def category(client,h,kind,name):
    response=client.post('/api/v1/finance/categories/'+kind,headers=h,json={'name':name})
    assert response.status_code==201,response.text
    return response.json()


def test_expenses_income_sale_editing_totals_and_audit(api):
    client,factory=api;h=login(client)
    expense=category(client,h,'expense','Alimentación');income=category(client,h,'income','Venta de animales')
    supplier=client.post('/api/v1/finance/suppliers',headers=h,json={'name':'Agropecuaria del Valle','phone':'9612345678','email':'ventas@example.com','address':'Tuxtla Gutiérrez'}).json()
    data={'category_id':expense['id'],'supplier_id':supplier['id'],'amount':'100.10','date':'2024-06-01','description':'Alimento para el hato'}
    r=client.post('/api/v1/finance/expenses',headers=h,json=data);assert r.status_code==201,r.text;saved=r.json();assert saved['supplier']['name']==supplier['name']
    inactive=client.put('/api/v1/finance/suppliers/'+supplier['id'],headers=h,json={key:value for key,value in {**supplier,'active':False}.items() if key!='id'})
    assert inactive.status_code==200,inactive.text
    a=animal(client,h,name='Aurora',birth_date='2020-01-01')
    sale=client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'exit_type':'sale','date':'2024-06-01','reason':'Venta.'}).json()
    assert client.get('/api/v1/finance/sale-options',headers=h).json()[0]['id']==sale['id']
    money={'category_id':income['id'],'exit_event_id':sale['id'],'amount':'300.30','date':'2024-06-02','description':'Venta de Aurora'}
    r=client.post('/api/v1/finance/incomes',headers=h,json=money);assert r.status_code==201,r.text;received=r.json()
    assert received['sale']['animal_name']=='Aurora'
    assert client.get('/api/v1/finance/sale-options',headers=h).json()==[]
    assert client.get('/api/v1/finance/sale-options?income_id='+received['id'],headers=h).json()[0]['id']==sale['id']
    assert client.post('/api/v1/finance/incomes',headers=h,json=money).status_code==409
    r=client.put('/api/v1/finance/expenses/'+saved['id'],headers=h,json={**data,'amount':'150.15'});assert r.status_code==200,r.text
    r=client.put('/api/v1/finance/incomes/'+received['id'],headers=h,json={**money,'amount':'350.35'});assert r.status_code==200,r.text
    totals=client.get('/api/v1/finance/summary?date_from=2024-06-01&date_to=2024-06-02',headers=h).json()
    assert totals=={'income_total':'350.35','expense_total':'150.15','balance':'200.20','income_count':1,'expense_count':1}
    assert client.get('/api/v1/finance/expenses?date_from=2024-06-02',headers=h).json()['total']==0
    assert client.get('/api/v1/finance/incomes?q=aurora&category_id='+str(income['id']),headers=h).json()['total']==1
    assert client.delete('/api/v1/finance/categories/expense/'+str(expense['id']),headers=h).status_code==409
    with factory() as db:
        audit=db.scalar(select(AuditModel).where(AuditModel.record_id==saved['id'],AuditModel.action=='UPDATE'))
        assert audit.old_values['amount']=='100.10' and audit.new_values['amount']=='150.15'
        assert db.get(IncomeModel,received['id']).exit_event_id==sale['id']


def test_finance_validation_protection_and_catalog_lifecycle(api):
    client,factory=api;h=login(client);worker=login(client,'worker@example.com')
    cat=category(client,h,'expense','Alimento')
    assert client.post('/api/v1/finance/categories/expense',headers=h,json={'name':' alimento '}).status_code==409
    assert client.put('/api/v1/finance/categories/expense/'+str(cat['id']),headers=h,json={'name':'Alimentación'}).status_code==200
    spare=category(client,h,'income','Otro ingreso')
    assert client.delete('/api/v1/finance/categories/income/'+str(spare['id']),headers=h).status_code==204
    supplier={'name':'Agropecuaria','active':True}
    s=client.post('/api/v1/finance/suppliers',headers=h,json=supplier).json()
    assert client.post('/api/v1/finance/suppliers',headers=h,json=supplier).status_code==409
    assert client.put('/api/v1/finance/suppliers/'+s['id'],headers=h,json={**supplier,'active':False}).status_code==200
    data={'category_id':cat['id'],'amount':'1.25','date':'2024-01-01','supplier_id':s['id']}
    assert client.post('/api/v1/finance/expenses',headers=h,json=data).status_code==409
    data['supplier_id']=None
    for invalid in [{'amount':0},{'amount':-1},{'amount':'1.001'},{'amount':'NaN'},{'amount':'10000000000'},{'date':str(date.today()+timedelta(days=1))},{'category_id':999}]:
        assert client.post('/api/v1/finance/expenses',headers=h,json={**data,**invalid}).status_code==422
    assert client.get('/api/v1/finance/summary?date_from=2024-02-01&date_to=2024-01-01',headers=h).status_code==422
    for path in ['/summary','/expenses','/incomes','/suppliers','/categories/expense','/sale-options']:
        assert client.get('/api/v1/finance'+path,headers=worker).status_code==403
        assert client.get('/api/v1/finance'+path).status_code==401
    assert client.post('/api/v1/finance/expenses',headers=worker,json=data).status_code==403
    assert client.get('/api/v1/finance/summary',headers=h).json()['expense_count']==0


def test_income_must_reference_sale_and_not_precede_it(api):
    client,_=api;h=login(client);cat=category(client,h,'income','Venta')
    a=animal(client,h,birth_date='2020-01-01')
    death=client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'exit_type':'death','date':'2024-06-01','reason':'Fallecimiento.'}).json()
    data={'category_id':cat['id'],'amount':'300','date':'2024-06-01','exit_event_id':death['id']}
    assert client.post('/api/v1/finance/incomes',headers=h,json=data).status_code==422
    b=animal(client,h,name='Sol',birth_date='2020-01-01')
    sale=client.post('/api/v1/exits',headers=h,json={'animal_id':b['id'],'exit_type':'sale','date':'2024-06-01','reason':'Venta.'}).json()
    data.update(exit_event_id=sale['id'],date='2024-05-31')
    assert client.post('/api/v1/finance/incomes',headers=h,json=data).status_code==422
    assert client.get('/api/v1/finance/summary',headers=h).json()['income_count']==0
    data.update(exit_event_id=None,date='2024-06-01',amount='0')
    assert client.post('/api/v1/finance/incomes',headers=h,json=data).status_code==201
