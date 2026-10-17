from sqlalchemy import select
from src.core.models import AuditModel, UnitModel, ProductModel, RoleModel, RolePermissionModel, ExpenseModel
from tests.conftest import login
from tests.test_treatments import product
from tests.test_doses import setup,dose


def price(client,h,p,day,cost):
    return client.post(f"/api/v1/health/products/{p['id']}/prices",headers=h,json={'effective_from':day,'cost':cost})


def test_price_history_current_future_initial_atomicity_and_audit(api):
    client,factory=api;h=login(client)
    with factory.begin() as db:db.add(UnitModel(id=2,code='g'))
    p=product(client,h,initial_price={'effective_from':'2024-01-01','cost':'0.50'}).json()
    assert p.get('id'),p
    assert client.post(f"/api/v1/health/products/{p['id']}/prices",headers=h,json={'effective_from':'2024-02-01','cost':'1','expected_unit_id':2}).status_code==409
    assert price(client,h,p,'2024-01-01','1.00').status_code==409
    assert price(client,h,p,'2099-01-01','2.00').status_code==201
    r=client.get(f"/api/v1/health/products/{p['id']}/prices?limit=1",headers=h)
    assert r.status_code==200,r.text
    data=r.json();assert data['total']==2 and data['items'][0]['effective_from']=='2099-01-01'
    assert data['current_price']['cost']=='0.50'
    assert client.get('/api/v1/health/products',headers=h).json()['items'][0]['current_price']['cost']=='0.50'
    r=client.put('/api/v1/health/products/'+p['id'],headers=h,json={'name':p['name'],'product_type_id':1,'unit_id':2,'withdrawal_days':7})
    assert r.status_code==409,r.text
    for invalid in ['-1','NaN','1.001','10000000000']:
        assert price(client,h,p,'2024-02-01',invalid).status_code==422
    with factory() as db:
        assert db.scalar(select(AuditModel).where(AuditModel.table=='product_prices')).new_values['unit_id']==1
        assert not db.scalar(select(ExpenseModel.id))


def test_actual_cost_by_clinical_date_partial_unknown_zero_and_pagination(api):
    client,factory=api;h=login(client);a,c,p,t=setup(client,h)
    with factory.begin() as db:db.add(UnitModel(id=2,code='g'))
    url=f"/api/v1/health/treatments/{t['id']}/products/{p['id']}/cost"
    assert client.get(url,headers=h).json()['status']=='no_applications'
    assert dose(client,h,t,p).status_code==201
    assert dose(client,h,t,p,applied_at='2024-01-04T10:00:00-06:00',dose_value='1.125',notes='Cantidad real registrada.').status_code==201
    assert price(client,h,p,'2024-01-04','0.50').status_code==201
    r=client.get(url+'?limit=1&offset=1',headers=h).json()
    assert (r['known_cost'],r['total'],r['priced_applications'],r['unknown_applications'])==('0.56',2,1,1)
    assert r['items'][0]['cost']=='0.56'
    # 23:30 -06 belongs to Jan 3 although its UTC instant belongs to Jan 4.
    assert price(client,h,p,'2024-01-03','0.25').status_code==201
    r=client.get(url,headers=h).json();assert r['known_cost']=='1.06' and r['status']=='complete'
    assert price(client,h,p,'2024-01-05','0').status_code==201
    assert dose(client,h,t,p,applied_at='2024-01-05T10:00:00-06:00',notes='Fecha real.').status_code==201
    r=client.get(url,headers=h).json();assert r['items'][-1]['cost']=='0.00' and r['priced_applications']==3
    assert dose(client,h,t,p,applied_at='2024-01-06T10:00:00-06:00',dose_unit_id=2,notes='Unidad real distinta.').status_code==201
    r=client.get(url,headers=h).json();assert r['unknown_applications']==1 and r['items'][-1]['unknown_reason']=='unit_mismatch'
    assert r['known_cost']=='1.06'


def test_prices_and_costs_require_finance_permission_and_hide_prices(api):
    client,factory=api;h=login(client);a,c,p,t=setup(client,h);w=login(client,'worker@example.com')
    with factory.begin() as db:
        role=db.scalar(select(RoleModel).where(RoleModel.name=='worker'))
        db.add_all([RolePermissionModel(role_id=role.id,permission='health:read'),RolePermissionModel(role_id=role.id,permission='health:products:write')])
    paths=[f"/api/v1/health/products/{p['id']}/prices",f"/api/v1/health/treatments/{t['id']}/products/{p['id']}/cost"]
    for path in paths:
        assert client.get(path,headers=w).status_code==403
        assert client.get(path).status_code==401
    assert price(client,w,p,'2024-01-01','0.50').status_code==403
    r=product(client,w,name='No autorizado',initial_price={'effective_from':'2024-01-01','cost':'1'})
    assert r.status_code==403
    assert 'current_price' not in client.get('/api/v1/health/products',headers=w).json()['items'][0]
    with factory() as db:assert not db.scalar(select(ProductModel.id).where(ProductModel.name=='No autorizado'))
