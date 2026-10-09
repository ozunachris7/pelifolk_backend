from sqlalchemy import select
from src.core.models import AuditModel, UserModel
from tests.conftest import login, PASSWORD


def test_separate_first_and_middle_names_are_persisted_and_audited(api):
    client, factory = api
    headers = login(client)
    roles = client.get("/api/v1/roles", headers=headers).json()
    role_id = next(role["id"] for role in roles if role["name"] == "worker")
    data = {"name": " Juan ", "middle_name": " Carlos ", "paternal_lastname": "Lopez",
            "maternal_lastname": "Perez", "email": "juan@example.com", "password": PASSWORD,
            "role_id": role_id}
    response = client.post("/api/v1/users", headers=headers, json=data)
    assert response.status_code == 201, response.text
    user_id = response.json()["id"]
    assert response.json()["name"] == "Juan"
    assert response.json()["middle_name"] == "Carlos"
    user_headers = login(client, "juan@example.com")
    assert client.get("/api/v1/auth/me", headers=user_headers).json()["middle_name"] == "Carlos"
    assert client.get(f"/api/v1/users/{user_id}", headers=headers).json()["middle_name"] == "Carlos"
    with factory() as session:
        user = session.get(UserModel, user_id)
        assert (user.name, user.middle_name) == ("Juan", "Carlos")
        audit = session.scalar(select(AuditModel).where(AuditModel.record_id == user_id))
        assert audit.new_values["middle_name"] == "Carlos"
    assert client.patch(f"/api/v1/users/{user_id}", headers=headers,
                        json={"middle_name": " "}).status_code == 422
    assert client.patch(f"/api/v1/users/{user_id}", headers=headers,
                        json={"middle_name": " Miguel "}).json()["middle_name"] == "Miguel"
    assert client.patch(f"/api/v1/users/{user_id}", headers=headers,
                        json={"middle_name": None}).json()["middle_name"] is None
    data.pop("middle_name")
    data["email"] = "another@example.com"
    assert client.post("/api/v1/users", headers=headers, json=data).json()["middle_name"] is None


def test_custom_role_user_lifecycle_and_audit(api):
    client, factory = api
    headers = login(client)
    role = client.post("/api/v1/roles", headers=headers,
                       json={"name": "health_supervisor", "permissions": ["roles:read"]})
    assert role.status_code == 201, role.text
    role_id = role.json()["id"]
    data = {"name": "Ana", "paternal_lastname": "Lopez", "maternal_lastname": "Maternal", "email": " ANA@example.com ",
            "password": PASSWORD, "role_id": role_id}
    response = client.post("/api/v1/users", headers=headers, json=data)
    assert response.status_code == 201, response.text
    user_id = response.json()["id"]
    assert response.json()["email"] == "ana@example.com"
    assert response.json()["paternal_lastname"] == "Lopez"
    assert "password" not in response.text
    ana = login(client, "ana@example.com")
    assert client.get("/api/v1/roles", headers=ana).status_code == 200
    assert client.get("/api/v1/users", headers=ana).status_code == 403
    assert client.delete(f"/api/v1/roles/{role_id}", headers=headers).status_code == 409
    update = client.put(f"/api/v1/roles/{role_id}", headers=headers,
                         json={"name": "health_supervisor", "permissions": []})
    assert update.status_code == 200, update.text
    assert client.get("/api/v1/roles", headers=ana).status_code == 403
    assert client.delete(f"/api/v1/users/{user_id}", headers=headers).status_code == 204
    assert client.get("/api/v1/auth/me", headers=ana).status_code == 401
    with factory() as session:
        user = session.get(UserModel, user_id)
        assert user is not None and not user.active
        assert user.password_hash.startswith("$argon2")
        audits = session.scalars(select(AuditModel)).all()
        assert len(audits) == 4
        assert "password_hash" not in str([entry.new_values for entry in audits])


def test_duplicates_missing_relations_and_validation(api):
    client, _ = api
    headers = login(client)
    roles = client.get("/api/v1/roles", headers=headers).json()
    assert len(roles) == 6
    role_id = roles[0]["id"]
    data = {"name": "New", "paternal_lastname": "Person", "maternal_lastname": "Maternal", "email": "owner@example.com",
            "password": PASSWORD, "role_id": role_id}
    assert client.post("/api/v1/users", headers=headers, json=data).status_code == 409
    data["email"] = "new@example.com"
    data["role_id"] = "11111111-1111-4111-8111-111111111111"
    assert client.post("/api/v1/users", headers=headers, json=data).status_code == 404
    data["role_id"] = role_id
    data.pop("paternal_lastname")
    assert client.post("/api/v1/users", headers=headers, json=data).status_code == 422
    assert client.post("/api/v1/roles", headers=headers, json={"name": "owner"}).status_code == 409
    assert client.post("/api/v1/roles", headers=headers,
                       json={"name": "another", "permissions": ["unknown"]}).status_code == 422
    assert client.get("/api/v1/users?limit=999", headers=headers).status_code == 422


def test_protect_system_roles_and_own_account(api):
    client, _ = api
    headers = login(client)
    me = client.get("/api/v1/auth/me", headers=headers).json()
    user_id, role_id = me["id"], me["role_id"]
    assert client.delete(f"/api/v1/users/{user_id}", headers=headers).status_code == 409
    assert client.patch(f"/api/v1/users/{user_id}", headers=headers, json={"active": False}).status_code == 409
    assert client.patch(f"/api/v1/users/{user_id}", headers=headers, json={"role_id": role_id}).status_code == 409
    assert client.delete(f"/api/v1/roles/{role_id}", headers=headers).status_code == 409
    assert client.put(f"/api/v1/roles/{role_id}", headers=headers,
                      json={"name": "owner", "permissions": []}).status_code == 409
    assert client.patch(f"/api/v1/users/{user_id}", headers=headers, json={"paternal_lastname": None}).status_code == 422


def test_password_change_revokes_tokens_and_never_audits_password(api):
    client, factory = api
    headers = login(client)
    me = client.get("/api/v1/auth/me", headers=headers).json()
    response = client.patch(f"/api/v1/users/{me['id']}", headers=headers,
                            json={"password": "Updated-password-12345"})
    assert response.status_code == 200, response.text
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": PASSWORD}).status_code == 401
    login(client, password="Updated-password-12345")
    with factory() as session:
        audit = session.scalar(select(AuditModel))
        assert audit.new_values["password_changed"] is True
        assert "Updated-password" not in str(audit.new_values)


def test_custom_role_can_be_deleted_if_unassigned(api):
    client, _ = api
    headers = login(client)
    role = client.post("/api/v1/roles", headers=headers, json={"name": "temporary_role"}).json()
    assert client.delete(f"/api/v1/roles/{role['id']}", headers=headers).status_code == 204
    assert client.delete(f"/api/v1/roles/{role['id']}", headers=headers).status_code == 404


def test_system_role_permissions_can_be_changed_without_renaming_or_deleting(api):
    client, factory = api
    owner = login(client)
    worker = login(client, "worker@example.com")
    role = next(role for role in client.get("/api/v1/roles", headers=owner).json() if role["name"] == "worker")
    response = client.put(f"/api/v1/roles/{role['id']}", headers=owner,
                          json={"name": "worker", "permissions": ["users:read"]})
    assert response.status_code == 200, response.text
    assert response.json()["permissions"] == ["users:read"]
    assert client.get("/api/v1/users", headers=worker).status_code == 200
    assert client.put(f"/api/v1/roles/{role['id']}", headers=owner,
                      json={"name": "renamed_worker", "permissions": ["users:read"]}).status_code == 409
    assert client.delete(f"/api/v1/roles/{role['id']}", headers=owner).status_code == 409
    assert client.put(f"/api/v1/roles/{role['id']}", headers=owner,
                      json={"name": "worker", "permissions": []}).status_code == 200
    assert client.get("/api/v1/users", headers=worker).status_code == 403
    with factory() as session:
        audits = session.scalars(select(AuditModel).where(AuditModel.table == "roles")).all()
        assert len(audits) == 2
        assert audits[0].new_values["permissions"] == ["users:read"]


def test_delegated_manager_cannot_escalate_or_reset_owner_password(api):
    client, _ = api
    owner = login(client)
    permissions = ["users:read", "users:write", "roles:read", "roles:write"]
    roles = client.get("/api/v1/roles", headers=owner).json()
    owner_role = next(role for role in roles if role["name"] == "owner")
    custom = client.post("/api/v1/roles", headers=owner,
                         json={"name": "limited_manager", "permissions": ["users:write", "roles:write"]}).json()
    user = {"name": "Limited", "paternal_lastname": "Manager", "maternal_lastname": "Maternal", "email": "limited@example.com",
            "password": PASSWORD, "role_id": custom["id"]}
    assert client.post("/api/v1/users", headers=owner, json=user).status_code == 201
    limited = login(client, "limited@example.com")
    assert client.post("/api/v1/roles", headers=limited,
                       json={"name": "escalated_role", "permissions": permissions}).status_code == 403
    user.update(email="escalated@example.com", role_id=owner_role["id"])
    assert client.post("/api/v1/users", headers=limited, json=user).status_code == 403
    me = client.get("/api/v1/auth/me", headers=owner).json()
    assert client.patch(f"/api/v1/users/{me['id']}", headers=limited,
                        json={"password": "Takeover-password-12345"}).status_code == 403
    assert client.delete(f"/api/v1/users/{me['id']}", headers=limited).status_code == 403


def test_validation_errors_do_not_echo_passwords(api):
    client, _ = api
    headers = login(client)
    response = client.post("/api/v1/users", headers=headers,
                           json={"name": "New", "paternal_lastname": "Person", "maternal_lastname": "Maternal", "email": "new@example.com",
                                 "password": "shortsecret", "role_id": "invalid"})
    assert response.status_code == 422
    assert "shortsecret" not in response.text
    assert "input" not in response.text


def test_role_reassignment_revokes_existing_session(api):
    client, _ = api
    owner = login(client)
    worker = login(client, "worker@example.com")
    worker_id = client.get("/api/v1/auth/me", headers=worker).json()["id"]
    roles = client.get("/api/v1/roles", headers=owner).json()
    veterinarian = next(role for role in roles if role["name"] == "veterinarian")
    assert client.patch(f"/api/v1/users/{worker_id}", headers=owner,
                        json={"role_id": veterinarian["id"]}).status_code == 200
    assert client.get("/api/v1/auth/me", headers=worker).status_code == 401
    fresh = login(client, "worker@example.com")
    assert client.get("/api/v1/auth/me", headers=fresh).json()["role_name"] == "veterinarian"


def test_users_list_excludes_actor_before_pagination(api):
    client, _ = api
    headers = login(client)
    me = client.get('/api/v1/auth/me', headers=headers).json()
    users = client.get('/api/v1/users', headers=headers).json()
    assert users and all(user['id'] != me['id'] for user in users)
    pages = [client.get(f'/api/v1/users?offset={offset}&limit=1', headers=headers).json()
             for offset in range(len(users) + 1)]
    assert [page[0]['id'] for page in pages[:-1]] == [user['id'] for user in users]
    assert pages[-1] == []
