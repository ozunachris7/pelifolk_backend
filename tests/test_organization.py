from datetime import date, timedelta
from sqlalchemy import select
from src.core.models import AuditModel
from tests.conftest import login
from tests.test_animals import animal


def group(client, headers, name='Crías'):
    response = client.post('/api/v1/groups', headers=headers, json={'name': name})
    assert response.status_code == 201, response.text
    return response.json()


def assign(client, headers, group_id, animal_ids, date='2024-01-01', move=False):
    return client.post('/api/v1/groups/'+group_id+'/assignments', headers=headers,
                       json={'animal_ids': animal_ids, 'effective_date': date, 'move_existing': move})


def test_location_catalog_lifecycle_and_audit(api):
    client, factory = api
    headers = login(client)
    kind = client.post('/api/v1/location-types', headers=headers, json={'name': 'Corral'}).json()
    assert client.post('/api/v1/location-types', headers=headers, json={'name': ' corral '}).status_code == 409
    data = {'name': ' Corral norte ', 'description': ' Cerca nueva ', 'location_type_id': kind['id']}
    response = client.post('/api/v1/locations', headers=headers, json=data)
    assert response.status_code == 201, response.text
    location = response.json()
    assert (location['name'], location['description'], location['location_type_name']) == ('Corral norte', 'Cerca nueva', 'Corral')
    assert client.get('/api/v1/locations?q=norte&active=true', headers=headers).json()[0]['id'] == location['id']
    assert client.post('/api/v1/locations', headers=headers, json={**data, 'name': 'corral norte'}).status_code == 409
    assert client.post('/api/v1/locations', headers=headers, json={**data, 'name': 'Other', 'location_type_id': 999}).status_code == 422
    response = client.put('/api/v1/locations/'+location['id'], headers=headers, json={**data, 'name': 'Corral principal', 'description': '', 'active': False})
    assert response.status_code == 200, response.text
    assert response.json()['description'] is None
    assert client.get('/api/v1/locations?active=true', headers=headers).json() == []
    with factory() as session:
        audit = session.scalar(select(AuditModel).where(AuditModel.table == 'locations', AuditModel.action == 'UPDATE'))
        assert audit.old_values['name'] == 'Corral norte'
        assert audit.new_values['active'] is False


def test_assignment_transfer_removal_and_history(api):
    client, factory = api
    owner = login(client)
    first, second = group(client, owner), group(client, owner, 'Reproductoras')
    saved = animal(client, owner, birth_date='2020-01-01')
    response = assign(client, owner, first['id'], [saved['id']])
    assert response.status_code == 201, response.text
    assert assign(client, owner, second['id'], [saved['id']], '2024-02-01').status_code == 409
    response = assign(client, owner, second['id'], [saved['id']], '2024-02-01', True)
    assert response.status_code == 201, response.text
    old = client.get('/api/v1/groups/'+first['id']+'/memberships?current=false', headers=owner).json()['items']
    assert old[0]['end_date'] == '2024-01-31'
    assert client.get('/api/v1/groups/'+first['id']+'/memberships', headers=owner).json()['total'] == 0
    options = client.get('/api/v1/groups/animal-options?q=Luna', headers=owner).json()
    assert options['items'][0]['group_id'] == second['id']
    assert client.put('/api/v1/groups/'+second['id'], headers=owner, json={'name': 'Reproductoras', 'active': False}).status_code == 409
    response = client.post(f"/api/v1/groups/{second['id']}/animals/{saved['id']}/remove", headers=owner,
                           json={'effective_date': '2024-03-01'})
    assert response.status_code == 200, response.text
    assert response.json()['end_date'] == '2024-02-29'
    assert client.get('/api/v1/groups/animal-options', headers=owner).json()['items'][0]['group_id'] is None
    assert client.put('/api/v1/groups/'+second['id'], headers=owner, json={'name': 'Reproductoras', 'active': False}).status_code == 200
    assert assign(client, owner, second['id'], [saved['id']], '2024-04-01').status_code == 409
    with factory() as session:
        audits = session.scalars(select(AuditModel).where(AuditModel.table == 'group_animals')).all()
        assert [a.action for a in audits] == ['INSERT', 'UPDATE', 'INSERT', 'UPDATE']


def test_dates_batches_and_overlap_are_validated_atomically(api):
    client, _ = api
    owner = login(client)
    first, second = group(client, owner), group(client, owner, 'Engorda')
    one, two = animal(client, owner), animal(client, owner, name='Nube', birth_date='2024-05-01')
    assert assign(client, owner, first['id'], [one['id']], '2024-06-01').status_code == 201
    assert assign(client, owner, second['id'], [two['id'], one['id']], '2024-06-02').status_code == 409
    assert client.get('/api/v1/groups/'+second['id']+'/memberships', headers=owner).json()['total'] == 0
    assert assign(client, owner, second['id'], [one['id']], '2024-06-01', True).status_code == 422
    assert assign(client, owner, second['id'], [two['id']], '2024-01-01').status_code == 422
    assert assign(client, owner, second['id'], [two['id']], str(date.today()+timedelta(days=1))).status_code == 422
    assert assign(client, owner, second['id'], [two['id'], two['id']]).status_code == 422
    assert assign(client, owner, first['id'], [one['id']]).status_code == 409
    removal = f"/api/v1/groups/{first['id']}/animals/{one['id']}/remove"
    assert client.post(removal, headers=owner, json={'effective_date':'2024-07-01'}).status_code == 200
    assert client.post(removal, headers=owner, json={'effective_date':'2024-07-02'}).status_code == 409
    assert assign(client, owner, second['id'], [one['id']], '2024-06-15').status_code == 409
    assert assign(client, owner, second['id'], [one['id'], two['id']], '2024-07-01').status_code == 201
    page = client.get('/api/v1/groups/'+second['id']+'/memberships?offset=1&limit=1', headers=owner).json()
    assert page['total'] == 2 and len(page['items']) == 1


def test_organization_permissions_and_missing_records(api):
    client, _ = api
    owner, worker = login(client), login(client, 'worker@example.com')
    for endpoint in ('locations', 'location-types', 'groups', 'groups/animal-options'):
        assert client.get('/api/v1/'+endpoint).status_code == 401
        assert client.get('/api/v1/'+endpoint, headers=worker).status_code == 403
    assert client.post('/api/v1/groups', headers=worker, json={'name':'Test'}).status_code == 403
    assert client.post('/api/v1/locations', headers=worker, json={'name':'Test','location_type_id':1}).status_code == 403
    missing = '11111111-1111-4111-8111-111111111111'
    assert client.get('/api/v1/groups/'+missing+'/memberships', headers=owner).status_code == 404
    assert client.put('/api/v1/groups/'+missing, headers=owner, json={'name':'Test'}).status_code == 404
    assert client.post('/api/v1/groups', headers=owner, json={'name':' '}).status_code == 422


def test_birth_edits_preserve_existing_group_history(api):
    client, _ = api
    owner = login(client)
    lot = group(client, owner)
    saved = animal(client, owner, birth_date='2020-01-01')
    assert assign(client, owner, lot['id'], [saved['id']], '2024-01-01').status_code == 201
    response = client.put('/api/v1/animals/'+saved['id'], headers=owner,
                          json={'name':'Luna','sex':'female','birth_date':'2024-02-01'})
    assert response.status_code == 422
    assert response.json()['detail'] == 'Birth date conflicts with group history'
    assert client.get('/api/v1/animals/'+saved['id'], headers=owner).json()['birth_date'] == '2020-01-01'
