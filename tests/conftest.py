import os
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-only-secret-with-more-than-thirty-two-characters"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.core.config import get_settings
from src.core.database import get_db
from src.core.models import Base, RoleModel, RolePermissionModel, UserModel
from src.core.security import hash_password
from src.features.roles.domain.entities.Role import INITIAL_ROLES, PERMISSIONS
from main import create_app

PASSWORD = "Test-password-12345"


@pytest.fixture
def api():
    get_settings.cache_clear()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as session:
        for name in INITIAL_ROLES:
            privileges = PERMISSIONS if name in {"owner", "administrator"} else set()
            role = RoleModel(name=name, is_system=True,
                             permissions=[RolePermissionModel(permission=p) for p in privileges])
            session.add(role)
            session.flush()
            session.add(UserModel(name=name.title(), paternal_lastname="Example", maternal_lastname="Maternal", email=f"{name}@example.com",
                                  role_id=role.id, password_hash=hash_password(PASSWORD), active=True))
    app = create_app()
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
        yield client, factory
    engine.dispose()


def login(client, email="owner@example.com", password=PASSWORD):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}
