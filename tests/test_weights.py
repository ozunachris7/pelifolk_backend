from datetime import date, timedelta
from uuid import uuid4
from sqlalchemy import select, func
from src.core.models import EventModel, EventWeightModel, AuditModel
from tests.conftest import login
from tests.test_animals import animal


def post(client, headers, animal_id, day='2024-01-01', weight='30.50', **values):
    return client.post('/api/v1/weights', headers=headers, json=dict(animal_id=animal_id, date=day, weight_kg=weight, **values))


def test_create_history_sorted_gain_inputs_and_audit(api):
    client, factory = api
    owner = login(client)
    saved = animal(client, owner, birth_date='2023-01-01', siniiga='MX123')
    assert post(client, owner, saved['id'], '2024-02-01', '40.25', notes='  Buen estado  ').status_code == 201
    response = post(client, owner, saved['id'])
    assert response.status_code == 201, response.text
    data = response.json()
    assert data['weight_kg'] == '30.50' and data['recorded_by'].startswith('Owner')
    history = client.get(f"/api/v1/weights/animals/{saved['id']}/history", headers=owner).json()
    assert [w['date'] for w in history['items']] == ['2024-01-01', '2024-02-01']
    assert history['items'][1]['notes'] == 'Buen estado'
    page = client.get('/api/v1/weights?q=mx123&limit=1', headers=owner).json()
    assert page['total'] == 2 and page['items'][0]['date'] == '2024-02-01'
    assert client.get('/api/v1/weights?q=other', headers=owner).json()['total'] == 0
    assert client.get('/api/v1/weights/animal-options?q=mx123', headers=owner).json()[0]['id'] == saved['id']
    with factory() as db:
        event = db.get(EventModel, data['id'])
        assert event.user_id and event.role_id and event.event_type_id == 4
        audit = db.scalar(select(AuditModel).where(AuditModel.record_id == data['id']))
        assert audit.new_values['weight_kg'] == '30.50'


def test_invalid_duplicate_and_birth_edit_leave_no_partial_events(api):
    client, factory = api
    owner = login(client)
    saved = animal(client, owner, birth_date='2023-01-01')
    assert post(client, owner, saved['id'], '2022-01-01').status_code == 422
    for value in ['0', '-1', '1.234', '100000', 'NaN']:
        assert post(client, owner, saved['id'], weight=value).status_code == 422
    assert post(client, owner, saved['id'], str(date.today() + timedelta(days=1))).status_code == 422
    assert post(client, owner, str(uuid4())).status_code == 404
    assert post(client, owner, saved['id']).status_code == 201
    assert post(client, owner, saved['id'], weight='35').status_code == 409
    assert client.put('/api/v1/animals/'+saved['id'], headers=owner, json={'name':'Luna', 'sex':'female', 'birth_date':'2024-01-02'}).status_code == 422
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(EventModel)) == 1
        assert db.scalar(select(func.count()).select_from(EventWeightModel)) == 1


def test_permissions_and_empty_history(api):
    client, factory = api
    owner, worker = login(client), login(client, 'worker@example.com')
    saved = animal(client, owner)
    assert client.get('/api/v1/weights').status_code == 401
    for path in ['/weights', '/weights/animal-options', '/weights/animals/'+saved['id']+'/history']:
        assert client.get('/api/v1'+path, headers=worker).status_code == 403
    assert post(client, worker, saved['id']).status_code == 403
    assert client.get('/api/v1/weights/animals/'+saved['id']+'/history', headers=owner).json()['items'] == []
