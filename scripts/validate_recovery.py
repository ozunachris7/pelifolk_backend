"""Exercise backup and recovery with fictional ranch data and TWO isolated local servers."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import time
from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from scripts.backup import create_backup
from scripts.local_mysql import temporary_mysql
from scripts.verify_backup import inventory, verify_backup


def main():
    # Explicit test configuration, before importing the app; never read the ranch .env.
    os.environ.update(DATABASE_URL='sqlite://', JWT_SECRET='recovery-drill-only-secret-longer-than-32',
                      ENVIRONMENT='development', CORS_ORIGINS='[]')
    from fastapi.testclient import TestClient
    from src.core.config import get_settings
    from src.core.config.settings import Settings
    Settings.model_config = dict(Settings.model_config, env_file=None)
    get_settings.cache_clear()
    from main import create_app
    from src.core.database import get_db
    from src.core.migrations import run_migrations
    from src.core.models import RoleModel, UserModel
    from src.core.security import hash_password
    get_settings.cache_clear()

    def engine_for(socket, database):
        return create_engine(URL.create('mysql+pymysql', username='root', database=database,
                                        query={'unix_socket': socket}), hide_parameters=True)

    @contextmanager
    def client_for(engine):
        factory = sessionmaker(engine, expire_on_commit=False)
        app = create_app(migrate_on_startup=False)
        def database():
            with factory() as session:
                try:
                    yield session
                    session.commit()
                except Exception:
                    session.rollback()
                    raise
        app.dependency_overrides[get_db] = database
        with TestClient(app) as client:
            yield client

    def login(client):
        response = client.post('/api/v1/auth/login', json={
            'email': 'recovery@example.com', 'password': 'Fictional-recovery-password-123'})
        assert response.status_code == 200, response.text
        return {'Authorization': 'Bearer ' + response.json()['access_token']}

    started = time.monotonic()
    with temporary_mysql() as (root, socket):
        import pymysql
        admin = pymysql.connect(unix_socket=socket, user='root')
        try:
            with admin.cursor() as cursor:
                cursor.execute('CREATE DATABASE recovery_source CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci')
        finally:
            admin.close()
        engine = engine_for(socket, 'recovery_source')
        try:
            run_migrations(engine)
            with sessionmaker(engine).begin() as session:
                owner = session.scalar(select(RoleModel).where(RoleModel.name == 'owner'))
                session.add(UserModel(name='Recovery', paternal_lastname='Fictional',
                    maternal_lastname='Example', email='recovery@example.com', role_id=owner.id,
                    password_hash=hash_password('Fictional-recovery-password-123')))
            with client_for(engine) as client:
                headers = login(client)
                def post(path, body):
                    response = client.post('/api/v1' + path, headers=headers, json=body)
                    assert response.status_code == 201, response.text
                    return response.json()
                mother = post('/animals', {'name': 'SIMULACIÓN Madre', 'sex': 'female', 'birth_date': '2020-01-01'})
                child = post('/animals', {'name': 'SIMULACIÓN Cría', 'sex': 'female',
                    'birth_date': '2024-01-01', 'mother_id': mother['id']})
                post('/weights', {'animal_id': child['id'], 'date': '2024-03-01', 'weight_kg': '18.75'})
                post('/health/observations', {'animal_id': mother['id'], 'date': '2024-03-01',
                    'observation': 'SIMULACIÓN: nota para verificar restauración; sin hallazgo real.'})
                post('/health/cases', {'animal_id': mother['id'], 'start_date': '2024-03-01',
                    'reason': 'SIMULACIÓN de seguimiento'})
                paths = ['/animals', '/weights', '/health/observations', '/health/cases',
                         '/animals/' + child['id'] + '/timeline', '/auth/me']
                expected_responses = {}
                for path in paths:
                    response = client.get('/api/v1' + path, headers=headers)
                    assert response.status_code == 200, (path, response.text)
                    expected_responses[path] = response.json()
            expected = inventory(socket, 'recovery_source')
            config = root / 'source-client.cnf'
            config.write_text('[client]\nuser=root\nprotocol=SOCKET\nsocket=' + socket + '\n')
            config.chmod(0o600)
            backup = create_backup(config, 'recovery_source', root / 'backups')

            def validate(restored_socket, database, restored):
                assert restored == expected, 'Restored rows or programmable-object inventory differ'
                recovered_engine = engine_for(restored_socket, database)
                try:
                    run_migrations(recovered_engine)  # Checks all immutable migration checksums.
                    with client_for(recovered_engine) as recovered_client:
                        recovered_headers = login(recovered_client)
                        for path, payload in expected_responses.items():
                            response = recovered_client.get('/api/v1' + path, headers=recovered_headers)
                            assert response.status_code == 200, response.text
                            assert response.json() == payload, path
                finally:
                    recovered_engine.dispose()

            report, restored_root = verify_backup(backup, validate=validate)
            report.update(result='passed', source_and_restore_isolated=True,
                          all_table_hashes_match=True, migration_checksums_match=True,
                          api_routes_checked=paths, backup_folder=str(backup),
                          restore_report=str(restored_root / 'restoration.json'),
                          total_seconds=round(time.monotonic() - started, 2))
        finally:
            engine.dispose()
    report['source_server_stopped'] = True
    (root / 'recovery-drill.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Recovery drill passed. Evidence:', root / 'recovery-drill.json')


if __name__ == '__main__':
    main()
