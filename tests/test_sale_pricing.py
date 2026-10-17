from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select
from src.core.models import AuditModel, IncomeModel, EventModel, EventWeightModel
from tests.conftest import login
from tests.test_animals import animal
from tests.test_finance import category


def setup_sale(client, h, weight='35.25', name='Estrella'):
    a = animal(client,h,name=name,birth_date='2020-01-01')
    r=client.post('/api/v1/weights',headers=h,json={'animal_id':a['id'],'date':'2024-06-01','weight_kg':weight})
    assert r.status_code==201,r.text
    w=r.json()
    r=client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'exit_type':'sale','date':'2024-06-01','reason':'Venta por kilogramo.'})
    assert r.status_code==201,r.text
    return a,w,r.json()


def test_calculated_income_snapshot_rounding_audit_and_summary(api):
    client,factory=api;h=login(client);c=category(client,h,'income','Venta por kg')
    a,w,sale=setup_sale(client,h)
    payload={'category_id':c['id'],'date':'2024-06-02','exit_event_id':sale['id'],'pricing_mode':'per_kg','weight_event_id':w['id'],'price_per_kg':'65.50'}
    options=client.get(f"/api/v1/finance/sales/{sale['id']}/weights",headers=h)
    assert options.status_code==200,options.text
    assert options.json()==[{'id':w['id'],'date':'2024-06-01','weight_kg':'35.25'}]
    r=client.post('/api/v1/finance/incomes',headers=h,json=payload)
    assert r.status_code==201,r.text
    saved=r.json();assert saved['amount']=='2308.88'
    assert saved['sale_pricing']=={'weight_event_id':w['id'],'weight_kg':'35.25','price_per_kg':'65.50'}
    from io import BytesIO
    from openpyxl import load_workbook
    export=client.get('/api/v1/reports/finance/export?kind=income',headers=h)
    assert export.status_code==200,export.text
    sheet=load_workbook(BytesIO(export.content))['Ingresos']
    assert sheet['G2'].value==35.25 and sheet['H2'].value==65.5 and sheet['I2'].value==w['id']
    assert client.post('/api/v1/finance/incomes',headers=h,json=payload).status_code==409
    assert client.get('/api/v1/finance/summary',headers=h).json()['income_total']=='2308.88'
    assert client.get('/api/v1/finance/incomes',headers=h).json()['items'][0]['sale_pricing']==saved['sale_pricing']
    with factory() as db:
        audit=db.scalar(select(AuditModel).where(AuditModel.record_id==saved['id']))
        assert audit.new_values['sale_weight_kg']=='35.25'
        assert audit.new_values['price_per_kg']=='65.50'
    # Repricing is explicit and audited; existing total-price editing continues working.
    r=client.put('/api/v1/finance/incomes/'+saved['id'],headers=h,json={**payload,'price_per_kg':'66.00'})
    assert r.status_code==200,r.text
    assert r.json()['amount']=='2326.50'
    with factory() as db:
        audit=db.scalar(select(AuditModel).where(AuditModel.record_id==saved['id'],AuditModel.action=='UPDATE'))
        assert audit.old_values['price_per_kg']=='65.50'
    r=client.put('/api/v1/finance/incomes/'+saved['id'],headers=h,json={'category_id':c['id'],'date':'2024-06-02','exit_event_id':sale['id'],'amount':'2400'})
    assert r.status_code==200,r.text
    assert r.json()['sale_pricing'] is None


def test_pricing_rejects_invalid_links_payloads_and_amounts_without_writes(api):
    client,factory=api;h=login(client);c=category(client,h,'income','Venta')
    a,w,sale=setup_sale(client,h)
    b,wrong_weight,other_sale=setup_sale(client,h,name='Lucero')
    old=client.post('/api/v1/weights',headers=h,json={'animal_id':a['id'],'date':'2024-05-31','weight_kg':'34'}).json()
    data={'category_id':c['id'],'date':'2024-06-01','exit_event_id':sale['id'],'pricing_mode':'per_kg','weight_event_id':w['id'],'price_per_kg':'65.50'}
    for invalid in [{'exit_event_id':None},{'weight_event_id':None},{'price_per_kg':None},{'price_per_kg':'0'},{'price_per_kg':'1.001'},{'price_per_kg':'NaN'},{'weight_event_id':wrong_weight['id']},{'weight_event_id':old['id']},{'weight_event_id':str(uuid4())},{'amount':'1'},{'date':'2024-05-31'},{'price_per_kg':'9999999999.99'},{'pricing_mode':'total','amount':'100'}]:
        r=client.post('/api/v1/finance/incomes',headers=h,json={**data,**invalid})
        assert r.status_code==422,(invalid,r.text)
    with factory() as db:
        assert not db.scalar(select(IncomeModel.id))
    worker=login(client,'worker@example.com')
    assert client.get(f"/api/v1/finance/sales/{sale['id']}/weights",headers=worker).status_code==403
    assert client.get(f"/api/v1/finance/sales/{sale['id']}/weights").status_code==401
    assert client.post('/api/v1/finance/incomes',headers=worker,json=data).status_code==403


def test_no_weight_no_fallback_and_replaced_weights_excluded(api):
    client,factory=api;h=login(client)
    a,w,sale=setup_sale(client,h)
    with factory() as db:
        original=db.get(EventModel,w['id'])
        replacement=EventModel(animal_id=a['id'],event_type_id=4,date=original.date,user_id=original.user_id,role_id=original.role_id,replaced_event_id=original.id)
        db.add(replacement);db.flush();db.add(EventWeightModel(event_id=replacement.id,weight_kg=Decimal('36')));db.commit();new_id=replacement.id
    response=client.get(f"/api/v1/finance/sales/{sale['id']}/weights",headers=h)
    assert response.status_code==200,response.text
    assert [r['id'] for r in response.json()]==[new_id]
    c=category(client,h,'income','Venta')
    r=client.post('/api/v1/finance/incomes',headers=h,json={'category_id':c['id'],'date':'2024-06-01','exit_event_id':sale['id'],'pricing_mode':'per_kg','weight_event_id':w['id'],'price_per_kg':'65'})
    assert r.status_code==422
    b=animal(client,h,name='Sin peso',birth_date='2020-01-01')
    death=client.post('/api/v1/exits',headers=h,json={'animal_id':b['id'],'exit_type':'death','date':'2024-06-01','reason':'Baja.'}).json()
    assert client.get(f"/api/v1/finance/sales/{death['id']}/weights",headers=h).status_code==404
