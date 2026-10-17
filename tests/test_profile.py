from io import BytesIO
import re
import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.core.models import AuditModel, UserModel
from tests.conftest import login


@pytest.fixture
def photos(monkeypatch, tmp_path):
    monkeypatch.setenv('PROFILE_PHOTOS_DIR', str(tmp_path))
    return tmp_path


def photo(format='PNG', size=(80, 60), **options):
    file = BytesIO()
    Image.new('RGB', size, (80, 120, 40)).save(file, format=format, **options)
    return file.getvalue()


def upload(client, headers, data=None, name='camera.png'):
    return client.post('/api/v1/profile/photo', headers=headers,
                       files={'file': (name, photo() if data is None else data, 'image/png')})


def test_profile_photo_webp_url_session_static_and_replacement(photos, api):
    client, factory = api
    headers = login(client)
    assert client.get('/api/v1/profile', headers=headers).json()['profile_photo_url'] is None
    first = upload(client, headers, photo(size=(1600, 800)), name='../../untrusted.png')
    assert first.status_code == 200, first.text
    url = first.json()['profile_photo_url']
    assert re.fullmatch('/upload/photos_profile/ownerowner[0-9]{20}.webp', url)
    stored = photos / url.rsplit('/', 1)[1]
    with Image.open(stored) as image:
        assert image.format == 'WEBP'
        assert image.size == (1024, 512)
    fetched = client.get(url)
    assert fetched.status_code == 200 and fetched.headers['content-type'] == 'image/webp'
    assert client.get('/api/v1/auth/me', headers=headers).json()['profile_photo_url'] == url
    assert client.post('/api/v1/auth/login', json={'email': 'owner@example.com',
        'password': 'Test-password-12345'}).json()['user']['profile_photo_url'] == url
    second = upload(client, headers, photo('JPEG'))
    new_url = second.json()['profile_photo_url']
    assert second.status_code == 200 and new_url != url
    assert not stored.exists() and client.get(url).status_code == 404
    assert len(list(photos.glob('*.webp'))) == 1
    with factory() as session:
        row = session.scalar(select(UserModel).where(UserModel.email == 'owner@example.com'))
        assert row.profile_photo_url == new_url
        logs = session.scalars(select(AuditModel).where(AuditModel.table == 'users').order_by(AuditModel.date, AuditModel.id)).all()
        assert len(logs) == 2
        assert logs[-1].new_values['profile_photo_url'] == new_url


def test_worker_updates_only_their_own_photo_without_user_management_permission(photos, api):
    client, factory = api
    owner = login(client)
    worker = login(client, 'worker@example.com')
    assert client.get('/api/v1/profile').status_code == 401
    assert upload(client, {}).status_code == 401
    response = upload(client, worker)
    assert response.status_code == 200
    assert response.json()['role_name'] == 'worker'
    assert client.get('/api/v1/profile', headers=owner).json()['profile_photo_url'] is None
    assert client.get('/api/v1/users', headers=worker).status_code == 403
    assert client.patch('/api/v1/users/' + response.json()['id'], headers=owner,
        json={'profile_photo_url': '/upload/photos_profile/other.webp'}).status_code == 422


@pytest.mark.parametrize('data', [b'', b'not a picture', b'<svg xmlns="http://www.w3.org/2000/svg"/>',
                                 photo('GIF'), photo()[:30]])
def test_invalid_upload_preserves_current_photo(photos, api, data):
    client, _ = api
    headers = login(client)
    current = upload(client, headers).json()['profile_photo_url']
    response = upload(client, headers, data, 'fake.jpg')
    assert response.status_code == 422
    assert client.get('/api/v1/profile', headers=headers).json()['profile_photo_url'] == current
    assert len(list(photos.iterdir())) == 1


def test_oversized_upload_does_not_create_files(photos, api):
    client, _ = api
    assert upload(client, login(client), b'x' * (5 * 1024 * 1024 + 1)).status_code == 413
    assert not list(photos.iterdir())


def test_rotated_jpeg_orientation_is_applied_and_metadata_removed(photos, api):
    client, _ = api
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = 'Private camera metadata'
    response = upload(client, login(client), photo('JPEG', (30, 60), exif=exif))
    with Image.open(photos / response.json()['profile_photo_url'].rsplit('/', 1)[1]) as converted:
        assert converted.size == (60, 30)
        assert not converted.getexif()


def test_failed_database_commit_keeps_previous_photo_and_removes_new_file(photos, api, monkeypatch):
    client, _ = api
    headers = login(client)
    original = upload(client, headers).json()['profile_photo_url']
    def fail(*args, **kwargs):
        raise RuntimeError('simulated commit failure')
    with monkeypatch.context() as patch:
        patch.setattr(Session, 'commit', fail)
        with pytest.raises(RuntimeError, match='simulated commit failure'):
            upload(client, headers)
    assert client.get('/api/v1/profile', headers=headers).json()['profile_photo_url'] == original
    assert [p.name for p in photos.iterdir()] == [original.rsplit('/', 1)[1]]


def test_excessive_dimensions_are_rejected_before_creating_a_file(photos, api, monkeypatch):
    import src.features.users.infrastructure.profile as profile
    client, _ = api
    monkeypatch.setattr(profile, 'MAX_PIXELS', 100)
    response = upload(client, login(client), photo(size=(11, 10)))
    assert response.status_code == 422
    assert not list(photos.iterdir())


def test_mysql_concurrent_replacements_leave_only_the_latest_photo(photos, api, request):
    if not request.config.getoption('--mysql-api'):
        pytest.skip('Requires an isolated MySQL server for real row locks')
    from tests.test_mysql_validation import simultaneous_authenticated_requests
    client, factory = api
    headers = login(client)
    first = upload(client, headers).json()['profile_photo_url']
    results = simultaneous_authenticated_requests(client, factory, [
        lambda: upload(client, headers, photo('JPEG')), lambda: upload(client, headers, photo())])
    assert all(r.status_code == 200 for r in results), [(r.status_code, r.text) for r in results]
    final = client.get('/api/v1/profile', headers=headers).json()['profile_photo_url']
    assert final != first
    assert {p.name for p in photos.iterdir()} == {final.rsplit('/', 1)[1]}
    assert client.get(final).status_code == 200
