from datetime import date, timedelta
from sqlalchemy import select
from src.core.models import AuditModel, EventModel, GroupAnimalModel, UserModel
from tests.conftest import login
from tests.test_animals import animal


def test_exit_status_history_membership_and_permissions(api):
    client, factory = api
    headers = login(client)
    a = animal(client, headers, name='Luna', birth_date='2020-01-01')
    group = client.post('/api/v1/groups', headers=headers, json={'name':'Reproductoras'}).json()
    assigned = client.post(f"/api/v1/groups/{group['id']}/assignments",headers=headers,json={'animal_ids':[a['id']],'effective_date':'2024-01-01','move_existing':False})
    assert assigned.status_code == 201, assigned.text
    payload = {'animal_id':a['id'],'exit_type':'sale','date':'2024-06-01','reason':'Venta a otro rancho.'}
    response = client.post('/api/v1/exits',headers=headers,json=payload)
    assert response.status_code == 201, response.text
    departure = response.json()
    detail = client.get('/api/v1/animals/'+a['id'],headers=headers).json()
    assert (detail['status'],detail['exit_date']) == ('sale','2024-06-01')
    assert client.get('/api/v1/animals?active=true',headers=headers).json()['total'] == 0
    assert client.get('/api/v1/animals?active=false',headers=headers).json()['total'] == 1
    assert client.get('/api/v1/exits?q=luna&exit_type=sale',headers=headers).json()['items'][0]['id'] == departure['id']
    assert client.get(f"/api/v1/exits/animals/{a['id']}/history",headers=headers).json()['items'][0]['reason'] == payload['reason']
    assert client.get('/api/v1/exits/animal-options',headers=headers).json() == []
    invalid_edit = client.put('/api/v1/animals/'+a['id'],headers=headers,json={'name':'Luna','sex':'female','birth_date':'2025-01-01'})
    assert invalid_edit.status_code == 422
    assert client.post('/api/v1/exits',headers=headers,json=payload).status_code == 409
    worker = login(client,'worker@example.com')
    assert client.get('/api/v1/exits',headers=worker).status_code == 403
    assert client.post('/api/v1/exits',headers=worker,json=payload).status_code == 403
    assert client.get('/api/v1/exits').status_code == 401
    with factory() as db:
        period = db.scalar(select(GroupAnimalModel).where(GroupAnimalModel.animal_id == a['id']))
        assert period.end_date == date(2024,6,1)
        audit = db.scalar(select(AuditModel).where(AuditModel.record_id == departure['id']))
        assert audit.new_values['exit_type'] == 'sale'
        assert db.get(EventModel,departure['id']).role_id == db.get(UserModel,audit.user_id).role_id


def test_exit_validates_chronology_and_prevents_later_activity(api):
    client, factory = api
    headers = login(client)
    a = animal(client,headers,birth_date='2020-01-01')
    payload = {'animal_id':a['id'],'exit_type':'death','date':'2019-01-01','reason':'Fallecimiento.'}
    assert client.post('/api/v1/exits',headers=headers,json=payload).status_code == 422
    payload['date'] = (date.today()+timedelta(days=1)).isoformat()
    assert client.post('/api/v1/exits',headers=headers,json=payload).status_code == 422
    payload['date'] = '2024-06-01'
    weight = {'animal_id':a['id'],'date':'2024-06-02','weight_kg':30}
    assert client.post('/api/v1/weights',headers=headers,json=weight).status_code == 201
    assert client.post('/api/v1/exits',headers=headers,json=payload).status_code == 422
    payload['date'] = '2024-06-03'
    assert client.post('/api/v1/exits',headers=headers,json=payload).status_code == 201
    weight['date'] = '2024-06-04'
    assert client.post('/api/v1/weights',headers=headers,json=weight).status_code == 409
    assert client.post('/api/v1/health/observations',headers=headers,json={'animal_id':a['id'],'date':'2024-06-04','observation':'Control'}).status_code == 409
    assert client.post('/api/v1/health/cases',headers=headers,json={'animal_id':a['id'],'start_date':'2024-06-04','reason':'Control'}).status_code == 409
    group = client.post('/api/v1/groups',headers=headers,json={'name':'Lote'}).json()
    assert client.post(f"/api/v1/groups/{group['id']}/assignments",headers=headers,json={'animal_ids':[a['id']],'effective_date':'2024-06-04'}).status_code == 409
    # Historical measurements before the exit remain registrable.
    weight['date'] = '2024-05-01'
    assert client.post('/api/v1/weights',headers=headers,json=weight).status_code == 201


def test_exit_treatment_dates_and_active_group_counts(api):
    from tests.test_health import create_case
    from tests.test_treatments import product
    client, factory = api
    headers = login(client)
    a = animal(client,headers,birth_date='2020-01-01')
    case = create_case(client,headers,a['id']).json()
    p = product(client,headers).json()
    treatment = {'product_id':p['id'],'start_date':'2024-06-01','dose_value':2,'dose_unit_id':1,'route_id':1,'duration_days':10}
    path = f"/api/v1/health/cases/{case['id']}/treatments"
    assert client.post(path,headers=headers,json=treatment).status_code == 201
    payload = {'animal_id':a['id'],'exit_type':'sale','date':'2024-06-05','reason':'Venta.'}
    assert client.post('/api/v1/exits',headers=headers,json=payload).status_code == 422
    payload['date'] = '2024-06-10'
    assert client.post('/api/v1/exits',headers=headers,json=payload).status_code == 201
    assert client.post(path,headers=headers,json={**treatment,'start_date':'2024-06-09','duration_days':3}).status_code == 409
    assert client.post(f"/api/v1/health/cases/{case['id']}/diagnoses",headers=headers,json={'date':'2024-06-11','diagnosis':'Control','severity':'mild'}).status_code == 409
    # Exiting today closes membership today but excludes the animal from current members.
    b = animal(client,headers,name='Trueno',sex='male',birth_date='2020-01-01')
    group = client.post('/api/v1/groups',headers=headers,json={'name':'Lote actual'}).json()
    assert client.post(f"/api/v1/groups/{group['id']}/assignments",headers=headers,json={'animal_ids':[b['id']],'effective_date':date.today().isoformat()}).status_code == 201
    assert client.post('/api/v1/exits',headers=headers,json={**payload,'animal_id':b['id'],'date':date.today().isoformat()}).status_code == 201
    assert client.get(f"/api/v1/groups/{group['id']}/memberships?current=true",headers=headers).json()['total'] == 0
    assert client.get(f"/api/v1/groups/{group['id']}/memberships?current=false",headers=headers).json()['total'] == 1
    assert next(g for g in client.get('/api/v1/groups',headers=headers).json() if g['id']==group['id'])['member_count']==0
