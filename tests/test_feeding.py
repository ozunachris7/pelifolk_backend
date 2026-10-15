from datetime import date,timedelta
from sqlalchemy import select
from src.core.models import UnitModel,AuditModel
from tests.conftest import login
from tests.test_animals import animal


def feed_setup(client,factory,h):
    with factory.begin() as db:
        db.add(UnitModel(id=2,code='kg'))
    r=client.post('/api/v1/feeding/feeds',headers=h,json={'name':'Alimento para ovinos','unit_id':2})
    assert r.status_code==201,r.text
    return r.json()


def test_feeding_effective_prices_costs_and_history(api):
    client,factory=api;h=login(client);feed=feed_setup(client,factory,h)
    for start,cost in [('2024-01-01','10.1250'),('2024-02-01','12.5000')]:
        assert client.post(f"/api/v1/feeding/feeds/{feed['id']}/prices",headers=h,json={'effective_from':start,'unit_cost':cost}).status_code==201
    a=animal(client,h,birth_date='2020-01-01')
    data={'animal_id':a['id'],'feed_id':feed['id'],'date':'2024-01-31','quantity':'1.25'}
    r=client.post('/api/v1/feeding/consumptions',headers=h,json=data);assert r.status_code==201,r.text
    first=r.json();assert first['cost']=='12.66' and first['price_from']=='2024-01-01'
    r=client.post('/api/v1/feeding/consumptions',headers=h,json={**data,'date':'2024-02-01','quantity':'2'});assert r.status_code==201,r.text
    assert r.json()['cost']=='25.00'
    history=client.get('/api/v1/feeding/consumptions?animal_id='+a['id'],headers=h).json()
    assert history['total_cost']=='37.66' and history['total']==2 and history['unpriced_count']==0
    assert client.get('/api/v1/feeding/consumptions?date_from=2024-02-01&date_to=2024-02-01',headers=h).json()['total_cost']=='25.00'
    prices=client.get(f"/api/v1/feeding/feeds/{feed['id']}/prices",headers=h).json();assert prices[0]['effective_from']=='2024-02-01'
    assert client.post(f"/api/v1/feeding/feeds/{feed['id']}/prices",headers=h,json={'effective_from':'2024-01-01','unit_cost':15}).status_code==409
    assert client.put(f"/api/v1/feeding/feeds/{feed['id']}",headers=h,json={'name':'Alimento editado','unit_id':1}).status_code==409
    assert client.put(f"/api/v1/feeding/feeds/{feed['id']}",headers=h,json={'name':'Alimento editado','unit_id':2}).status_code==200
    assert client.put('/api/v1/animals/'+a['id'],headers=h,json={'name':'Luna','sex':'female','birth_date':'2024-02-02'}).status_code==422
    assert client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'exit_type':'sale','date':'2024-01-30','reason':'Venta'}).status_code==422
    assert client.post('/api/v1/exits',headers=h,json={'animal_id':a['id'],'exit_type':'sale','date':'2024-02-02','reason':'Venta'}).status_code==201
    assert client.post('/api/v1/feeding/consumptions',headers=h,json={**data,'date':'2024-02-03'}).status_code==409
    with factory() as db:
        assert db.scalar(select(AuditModel).where(AuditModel.record_id==first['id'])).new_values['quantity']=='1.25'


def test_group_feeding_validation_and_permissions(api):
    client,factory=api;h=login(client);feed=feed_setup(client,factory,h)
    a=animal(client,h,birth_date='2020-01-01')
    group=client.post('/api/v1/groups',headers=h,json={'name':'Reproductoras'}).json()
    data={'group_id':group['id'],'feed_id':feed['id'],'date':'2024-06-01','quantity':'5.50'}
    assert client.post('/api/v1/feeding/consumptions',headers=h,json=data).status_code==422
    client.post(f"/api/v1/groups/{group['id']}/assignments",headers=h,json={'animal_ids':[a['id']],'effective_date':'2024-01-01'})
    assert client.post('/api/v1/feeding/consumptions',headers=h,json=data).status_code==422
    client.post(f"/api/v1/feeding/feeds/{feed['id']}/prices",headers=h,json={'effective_from':'2024-01-01','unit_cost':'10'})
    r=client.post('/api/v1/feeding/consumptions',headers=h,json=data);assert r.status_code==201,r.text;assert r.json()['cost']=='55.00' and r.json()['animal'] is None
    for change in [{'animal_id':a['id']},{'group_id':None},{'quantity':0},{'quantity':'1.001'},{'quantity':'NaN'},{'date':str(date.today()+timedelta(days=1))}]:
        assert client.post('/api/v1/feeding/consumptions',headers=h,json={**data,**change}).status_code==422
    worker=login(client,'worker@example.com')
    for path in ['/units','/feeds','/consumptions','/target-options?kind=animal',f"/feeds/{feed['id']}/prices"]:
        assert client.get('/api/v1/feeding'+path,headers=worker).status_code==403
    assert client.post('/api/v1/feeding/consumptions',headers=worker,json=data).status_code==403
    assert client.get('/api/v1/feeding/consumptions').status_code==401
    assert client.get('/api/v1/feeding/consumptions?date_from=2024-06-02&date_to=2024-06-01',headers=h).status_code==422


def test_create_feed_with_initial_price(api):
    client,factory=api;h=login(client)
    body={'name':'Concentrado','unit_id':1,'initial_price':{'effective_from':'2024-01-01','unit_cost':'8.5000'}}
    bad=client.post('/api/v1/feeding/feeds',headers=h,json={**body,'initial_price':{'effective_from':'2024-01-01','unit_cost':'-1'}})
    assert bad.status_code==422
    assert client.get('/api/v1/feeding/feeds',headers=h).json()['total']==0
    response=client.post('/api/v1/feeding/feeds',headers=h,json=body)
    assert response.status_code==201,response.text
    feed=response.json()
    assert client.get(f"/api/v1/feeding/feeds/{feed['id']}/prices",headers=h).json()==[{'effective_from':'2024-01-01','unit_cost':'8.5000'}]
    assert client.post('/api/v1/feeding/feeds',headers=h,json=body).status_code==409
    assert len(client.get(f"/api/v1/feeding/feeds/{feed['id']}/prices",headers=h).json())==1


def test_feed_list_shows_current_price_not_future_price(api):
    client,factory=api;h=login(client);feed=feed_setup(client,factory,h)
    path=f"/api/v1/feeding/feeds/{feed['id']}/prices"
    assert client.post(path,headers=h,json={'effective_from':'2024-01-01','unit_cost':'8.5'}).status_code==201
    assert client.post(path,headers=h,json={'effective_from':(date.today()+timedelta(days=1)).isoformat(),'unit_cost':'20'}).status_code==201
    row=client.get('/api/v1/feeding/feeds',headers=h).json()['items'][0]
    assert row['current_unit_cost']=='8.5000'
    assert row['current_price_from']=='2024-01-01'
