import pytest
from sqlalchemy import select
from src.core.models import AuditModel, UserModel
from tests.conftest import login, PASSWORD


def test_worker_updates_own_identity_and_can_login_with_the_new_email(api):
    client, factory = api
    headers = login(client, 'worker@example.com')
    original = client.get('/api/v1/profile', headers=headers).json()
    response = client.patch('/api/v1/profile', headers=headers, json={
        'name': ' Mateo ', 'middle_name': ' Andres ', 'paternal_lastname': ' Lopez ',
        'maternal_lastname': ' Perez ', 'email': ' MATEO@example.com ', 'phone': ' 9612345678 '})
    assert response.status_code == 200, response.text
    saved = response.json()
    assert [saved[k] for k in ('name', 'middle_name', 'paternal_lastname', 'maternal_lastname', 'email', 'phone')] == [
        'Mateo', 'Andres', 'Lopez', 'Perez', 'mateo@example.com', '9612345678']
    assert saved['id'] == original['id'] and saved['role_id'] == original['role_id']
    assert saved['permissions'] == original['permissions'] and saved['active'] is True
    assert client.get('/api/v1/auth/me', headers=headers).json() == saved
    assert client.post('/api/v1/auth/login', json={'email': 'worker@example.com', 'password': PASSWORD}).status_code == 401
    assert client.post('/api/v1/auth/login', json={'email': saved['email'], 'password': PASSWORD}).status_code == 200
    with factory() as session:
        audit = session.scalar(select(AuditModel).where(AuditModel.record_id == original['id']))
        assert audit.user_id == original['id'] and audit.old_values['email'] == 'worker@example.com'
        assert audit.new_values['email'] == saved['email']
        assert 'password_hash' not in audit.new_values


@pytest.mark.parametrize('body', [{}, {'name': ' '}, {'name': None}, {'email': None},
    {'email': 'invalid'}, {'paternal_lastname': None}, {'maternal_lastname': ''},
    {'phone': 'x' * 31}, {'role_id': 'owner'}, {'permissions': ['users:write']},
    {'active': False}, {'password': 'new-password'}, {'id': 'another-user'},
    {'profile_photo_url': '/upload/photos_profile/other.webp'}])
def test_invalid_profile_edits_and_privilege_fields_are_rejected(api, body):
    client, _ = api
    headers = login(client, 'worker@example.com')
    before = client.get('/api/v1/profile', headers=headers).json()
    assert client.patch('/api/v1/profile', headers=headers, json=body).status_code == 422
    assert client.get('/api/v1/profile', headers=headers).json() == before


def test_duplicate_email_rolls_back_all_changes(api):
    client, factory = api
    headers = login(client)
    before = client.get('/api/v1/profile', headers=headers).json()
    response = client.patch('/api/v1/profile', headers=headers,
                            json={'email': 'WORKER@example.com', 'name': 'Should not persist'})
    assert response.status_code == 409
    assert client.get('/api/v1/profile', headers=headers).json() == before
    with factory() as session:
        assert session.scalar(select(AuditModel).where(AuditModel.record_id == before['id'])) is None


def test_partial_update_preserves_photo_other_fields_and_other_users(api):
    client, factory = api
    headers = login(client)
    own = client.get('/api/v1/profile', headers=headers).json()
    with factory.begin() as session:
        session.get(UserModel, own['id']).profile_photo_url = '/upload/photos_profile/ownerowner20261017000000000000.webp'
    response = client.patch('/api/v1/profile', headers=headers, json={'middle_name': ' ', 'phone': ''})
    assert response.status_code == 200
    assert response.json()['phone'] is None and response.json()['middle_name'] is None
    assert response.json()['name'] == own['name']
    assert response.json()['profile_photo_url'].endswith('.webp')
    with factory() as session:
        assert session.scalar(select(UserModel).where(UserModel.email == 'worker@example.com')).name == 'Worker'
    assert client.patch('/api/v1/profile', json={'name': 'Unauthenticated'}).status_code == 401
