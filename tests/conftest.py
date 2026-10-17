import os
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-only-secret-with-more-than-thirty-two-characters"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, delete
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.core.config import get_settings
from src.core.database import get_db
from src.core.models import BirthTypeModel, ProductTypeModel, UnitModel, AdministrationRouteModel, EventTypeModel, ExpenseCategoryModel, IncomeCategoryModel, LocationTypeModel, Base, RoleModel, RolePermissionModel, UserModel
from src.core.security import hash_password
from src.features.roles.domain.entities.Role import INITIAL_ROLES, PERMISSIONS
from main import create_app
from contextlib import nullcontext
from tests.mysql_support import isolated_mysql_database, test_mysql_url
from src.core.migrations import run_migrations

PASSWORD = "Test-password-12345"


def pytest_addoption(parser):
    parser.addoption('--mysql-api', action='store_true', default=False,
                     help='Run API fixtures against independently migrated disposable MySQL databases')


@pytest.fixture
def mysql_engine():
    with isolated_mysql_database(test_mysql_url()) as engine:
        yield engine


@pytest.fixture
def api(request):
    get_settings.cache_clear()
    mysql = request.config.getoption('--mysql-api')
    context = isolated_mysql_database(test_mysql_url()) if mysql else nullcontext(
        create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool))
    with context as engine:
        if mysql:
            # Exercise the actual SQL schema, functions, triggers and every immutable migration.
            run_migrations(engine)
        else:
            @event.listens_for(engine, 'connect')
            def foreign_keys(connection, record):
                connection.execute('PRAGMA foreign_keys=ON')
            Base.metadata.create_all(engine)
        factory = sessionmaker(engine, expire_on_commit=False)
        with factory.begin() as session:
            if mysql:
                # Test catalog IDs are controlled like the SQLite fixture. Real migration seeds
                # are verified independently in test_migrations; no existing schema is used here.
                for model in (BirthTypeModel, ProductTypeModel, UnitModel, AdministrationRouteModel, EventTypeModel, ExpenseCategoryModel, IncomeCategoryModel, LocationTypeModel):
                    session.execute(delete(model))
            session.add(BirthTypeModel(id=1,name='natural'))
            session.add_all([EventTypeModel(id=i,code=code,name=code) for i,code in [(5,'mating'),(6,'pregnancy_diagnosis'),(7,'birth'),(8,'exit'),(9,'location_movement')]])
            session.add_all([ProductTypeModel(id=1,name='medicine'), UnitModel(id=1,code='ml'), AdministrationRouteModel(id=1,name='oral')])
            session.add(EventTypeModel(id=3,code='treatment',name='Treatment'))
            session.add(EventTypeModel(id=2, code='diagnosis', name='Diagnosis'))
            session.add(EventTypeModel(id=1, code='observation', name='Observation'))
            session.add(EventTypeModel(id=4, code='weight', name='Weight'))
            for name in INITIAL_ROLES:
                privileges = PERMISSIONS if name in {'owner', 'administrator'} else set()
                role = session.scalar(select(RoleModel).where(RoleModel.name==name)) if mysql else None
                if role is None:
                    role = RoleModel(name=name, is_system=True)
                    session.add(role)
                role.permissions[:] = [p for p in role.permissions if p.permission in privileges]
                existing = {p.permission for p in role.permissions}
                role.permissions.extend(RolePermissionModel(permission=p) for p in privileges-existing)
                session.flush()
                session.add(UserModel(name=name.title(), paternal_lastname='Example', maternal_lastname='Maternal', email=f'{name}@example.com',
                                      role_id=role.id, password_hash=hash_password(PASSWORD), active=True))
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
        try:
            with TestClient(app) as client:
                yield client, factory
        finally:
            engine.dispose()


def login(client, email="owner@example.com", password=PASSWORD):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}
