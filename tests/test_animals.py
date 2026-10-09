from datetime import date, timedelta
from sqlalchemy import select
from src.core.models import AuditModel
from tests.conftest import login


def breed(client, headers, name='Pelibuey'):
    response = client.post('/api/v1/breeds', headers=headers, json={'name': name})
    assert response.status_code == 201, response.text
    return response.json()['id']


def animal(client, headers, **values):
    data = {'name': 'Luna', 'sex': 'female', **values}
    response = client.post('/api/v1/animals', headers=headers, json=data)
    assert response.status_code == 201, response.text
    return response.json()


def test_animal_create_search_edit_detail_and_audit(api):
    client, factory = api
    headers = login(client)
    first, second = breed(client, headers), breed(client, headers, 'Dorper')
    mom = animal(client, headers, name='Madre', birth_date='2020-01-01')
    dad = animal(client, headers, name='Padre', sex='male', birth_date='2019-01-01')
    child = animal(client, headers, siniiga='MX123', birth_date='2024-02-01', mother_id=mom['id'], father_id=dad['id'],
                   breeds=[{'breed_id': first, 'percentage': 60}, {'breed_id': second, 'percentage': 40}])
    assert child['purity'] == 'crossbred' and child['mother']['name'] == 'Madre'
    page = client.get('/api/v1/animals?q=mx123&limit=1', headers=headers).json()
    assert page['total'] == 1 and page['items'][0]['id'] == child['id']
    assert client.get('/api/v1/animals?q=%', headers=headers).json()['total'] == 0
    assert client.get('/api/v1/animals?sex=male', headers=headers).json()['total'] == 1
    data = {k: child[k] for k in ('name', 'siniiga', 'sex', 'birth_date', 'origin', 'mother_id', 'father_id', 'is_breeder')}
    data.update(name='Luna nueva', breeds=[{'breed_id': first, 'percentage': 100}])
    updated = client.put(f"/api/v1/animals/{child['id']}", headers=headers, json=data)
    assert updated.status_code == 200, updated.text
    assert updated.json()['purity'] == 'pure' and len(updated.json()['breeds']) == 1
    assert client.get(f"/api/v1/animals/{child['id']}", headers=headers).json()['name'] == 'Luna nueva'
    data.update(breeds=[], mother_id=None, father_id=None, siniiga=None)
    assert client.put(f"/api/v1/animals/{child['id']}", headers=headers, json=data).json()['purity'] is None
    with factory() as session:
        audits = session.scalars(select(AuditModel).where(AuditModel.record_id == child['id'])).all()
        assert [a.action for a in audits] == ['INSERT', 'UPDATE', 'UPDATE']
        assert audits[1].old_values['name'] == 'Luna'


def test_animal_validation_and_duplicates_roll_back(api):
    client, _ = api
    headers = login(client)
    breed_id = breed(client, headers)
    assert client.post('/api/v1/breeds', headers=headers, json={'name': ' pelibuey '}).status_code == 409
    base = {'name': 'Luna', 'sex': 'female'}
    for changes in [ {'name': ' ', 'siniiga': None}, {'birth_date': str(date.today() + timedelta(days=1))},
                     {'breeds': [{'breed_id': breed_id, 'percentage': 99}]},
                     {'breeds': [{'breed_id': breed_id, 'percentage': 50}] * 2},
                     {'breeds': [{'breed_id': 999, 'percentage': 100}]},
                     {'breeds': [{'breed_id': breed_id, 'percentage': '99.999'}]}, {'sex': 'invalid'} ]:
        response = client.post('/api/v1/animals', headers=headers, json={**base, **changes})
        assert response.status_code == 422, response.text
    animal(client, headers, siniiga='MX1')
    assert client.post('/api/v1/animals', headers=headers, json={**base, 'siniiga': 'mx1'}).status_code == 409
    assert client.get('/api/v1/animals', headers=headers).json()['total'] == 1


def test_genealogy_sex_dates_and_cycles(api):
    client, _ = api
    headers = login(client)
    mom = animal(client, headers, name='Mom', birth_date='2020-01-01')
    child = animal(client, headers, name='Child', birth_date='2021-01-01', mother_id=mom['id'])
    assert client.post('/api/v1/animals', headers=headers, json={'name': 'Other', 'sex': 'female', 'father_id': mom['id']}).status_code == 422
    for changes in [{'mother_id': child['id']}, {'mother_id': mom['id']}, {'sex': 'male'}, {'birth_date': '2022-01-01'}]:
        response = client.put(f"/api/v1/animals/{mom['id']}", headers=headers,
                              json={'name': 'Mom', 'sex': 'female', **changes})
        assert response.status_code == 422, response.text
    assert client.get('/api/v1/animals?sex=female&exclude_id='+mom['id'], headers=headers).json()['total'] == 1
    assert client.get('/api/v1/animals?offset=1&limit=1', headers=headers).json()['items'][0]['id'] == mom['id']


def test_animal_permissions_are_enforced_and_can_be_delegated(api):
    client, _ = api
    owner, worker = login(client), login(client, 'worker@example.com')
    assert client.get('/api/v1/animals').status_code == 401
    assert client.get('/api/v1/animals', headers=worker).status_code == 403
    role = next(r for r in client.get('/api/v1/roles', headers=owner).json() if r['name'] == 'worker')
    assert client.put('/api/v1/roles/'+role['id'], headers=owner, json={'name': 'worker', 'permissions': ['animals:read']}).status_code == 200
    assert client.get('/api/v1/animals', headers=worker).status_code == 200
    assert client.post('/api/v1/animals', headers=worker, json={'name': 'Luna', 'sex': 'female'}).status_code == 403
    assert client.post('/api/v1/breeds', headers=worker, json={'name': 'Dorper'}).status_code == 403


def test_rename_breed_preserves_assignments_and_audits(api):
    client, factory = api
    headers = login(client)
    breed_id = breed(client, headers, 'Pelibuei')
    other_id = breed(client, headers, 'Dorper')
    saved = animal(client, headers, breeds=[{'breed_id': breed_id, 'percentage': 100}])
    response = client.put(f'/api/v1/breeds/{breed_id}', headers=headers, json={'name': ' Pelibuey '})
    assert response.status_code == 200, response.text
    assert response.json() == {'id': breed_id, 'name': 'Pelibuey'}
    detail = client.get('/api/v1/animals/'+saved['id'], headers=headers).json()
    assert detail['breeds'] == [{'breed_id': breed_id, 'name': 'Pelibuey', 'percentage': '100.00'}]
    assert client.put(f'/api/v1/breeds/{breed_id}', headers=headers, json={'name': 'dorper'}).status_code == 409
    assert client.put('/api/v1/breeds/9999', headers=headers, json={'name': 'New'}).status_code == 404
    assert client.put(f'/api/v1/breeds/{other_id}', headers=headers, json={'name': ' '}).status_code == 422
    worker = login(client, 'worker@example.com')
    assert client.put(f'/api/v1/breeds/{breed_id}', headers=worker, json={'name': 'New'}).status_code == 403
    with factory() as session:
        audit = session.scalar(select(AuditModel).where(AuditModel.table == 'breeds',
                                                       AuditModel.record_id == str(breed_id), AuditModel.action == 'UPDATE'))
        assert audit.old_values['name'] == 'Pelibuei'
        assert audit.new_values['name'] == 'Pelibuey'


def test_delete_breed_requires_permission_and_preserves_animal_assignments(api):
    client, factory = api
    owner = login(client)
    used = breed(client, owner)
    animal(client, owner, breeds=[{'breed_id': used, 'percentage': 100}])
    unused = breed(client, owner, 'Dorper')
    assert client.delete(f'/api/v1/breeds/{unused}').status_code == 401
    worker = login(client, 'worker@example.com')
    assert client.delete(f'/api/v1/breeds/{unused}', headers=worker).status_code == 403
    assert client.delete(f'/api/v1/breeds/{used}', headers=owner).status_code == 409
    assert client.delete(f'/api/v1/breeds/{unused}', headers=owner).status_code == 204
    assert client.delete(f'/api/v1/breeds/{unused}', headers=owner).status_code == 404
    assert client.get('/api/v1/breeds', headers=owner).json() == [{'id': used, 'name': 'Pelibuey'}]
    with factory() as session:
        audit = session.scalar(select(AuditModel).where(AuditModel.table == 'breeds',
                                                       AuditModel.record_id == str(unused), AuditModel.action == 'DELETE'))
        assert audit.old_values == {'id': unused, 'name': 'Dorper'}
