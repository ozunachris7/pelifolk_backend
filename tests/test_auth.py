from datetime import datetime, timedelta, timezone
import jwt
from sqlalchemy import select
from src.core.config import get_settings
from src.core.models import UserModel
from tests.conftest import login, PASSWORD


def test_login_me_and_logout_revokes_all_tokens(api):
    client, factory = api
    first = login(client)
    second = login(client)
    response = client.get("/api/v1/auth/me", headers=first)
    assert response.status_code == 200
    assert response.json()["lastname"] == "Example"
    assert response.json()["role_name"] == "owner"
    assert "password_hash" not in response.text
    assert client.post("/api/v1/auth/logout", headers=first).status_code == 204
    assert client.get("/api/v1/auth/me", headers=first).status_code == 401
    assert client.get("/api/v1/auth/me", headers=second).status_code == 401
    assert client.get("/api/v1/auth/me", headers=login(client)).status_code == 200


def test_invalid_unknown_and_inactive_credentials_have_same_error(api):
    client, factory = api
    for email, password in [("owner@example.com", "wrong"), ("unknown@example.com", PASSWORD)]:
        response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid email or password"
    with factory.begin() as session:
        session.scalar(select(UserModel).where(UserModel.email == "worker@example.com")).active = False
    response = client.post("/api/v1/auth/login", json={"email": "worker@example.com", "password": PASSWORD})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_missing_tampered_and_expired_tokens(api):
    client, factory = api
    assert client.get("/api/v1/auth/me").status_code == 401
    headers = login(client)
    token = headers["Authorization"].split()[1]
    settings = get_settings()
    claims = jwt.decode(token, settings.jwt_secret.get_secret_value(), algorithms=["HS256"], audience="pelifolk")
    claims["iat"] = datetime.now(timezone.utc) - timedelta(hours=2)
    claims["exp"] = datetime.now(timezone.utc) - timedelta(hours=1)
    expired = jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + expired}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token + "broken"}).status_code == 401


def test_worker_cannot_manage_users_or_roles(api):
    client, _ = api
    headers = login(client, "worker@example.com")
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.get("/api/v1/users", headers=headers).status_code == 403
    assert client.get("/api/v1/roles", headers=headers).status_code == 403
    assert client.post("/api/v1/roles", headers=headers, json={"name": "new_role"}).status_code == 403


def test_unknown_stored_hash_rejects_login(api):
    client, factory = api
    with factory.begin() as session:
        session.scalar(select(UserModel).where(UserModel.email == "worker@example.com")).password_hash = "invalid-hash"
    assert client.post("/api/v1/auth/login", json={"email": "worker@example.com", "password": PASSWORD}).status_code == 401
