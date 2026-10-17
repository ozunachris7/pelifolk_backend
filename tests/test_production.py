import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError
from src.core.config.settings import Settings
from src.core.config import get_settings
from src.core.database import get_db
from main import create_app


def configuration(**overrides):
    return Settings(_env_file=None, database_url="mysql+pymysql://example@localhost/ranch",
                    jwt_secret="configuration-test-secret-longer-than-32-characters",
                    environment="production", **overrides)


@pytest.mark.parametrize("origin", ["*", "http://localhost:4200", "https://ranch.example/path",
                                      "https://user@ranch.example", "https://ranch.example?x=1"])
def test_production_rejects_unsafe_origins(origin):
    with pytest.raises(ValidationError):
        configuration(cors_origins=[origin])


def test_same_origin_production_allows_empty_cors():
    assert configuration(cors_origins=[]).cors_origins == []
    assert configuration(cors_origins=["https://ranch.example"]).environment == "production"


def test_production_docs_disabled(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://example@localhost/ranch")
    monkeypatch.setenv("CORS_ORIGINS", "[]")
    get_settings.cache_clear()
    try:
        with TestClient(create_app(migrate_on_startup=False)) as client:
            assert client.get("/health/live").json() == {"status": "ok"}
            for url in ("/docs", "/redoc", "/openapi.json"):
                assert client.get(url).status_code == 404
    finally:
        get_settings.cache_clear()


def test_readiness_checks_database_and_returns_sanitized_failure(api):
    client, _ = api
    assert client.get("/health/ready").json() == {"status": "ready"}
    def unavailable():
        raise OperationalError("secret SQL", {}, Exception("secret credentials"))
        yield
    client.app.dependency_overrides[get_db] = unavailable
    assert client.get("/health/live").status_code == 200
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
