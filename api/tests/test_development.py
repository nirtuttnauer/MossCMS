"""The development identity is not a delivery credential, including after startup."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import Settings
from app.development import DEVELOPMENT_USER_EMAIL, DEVELOPMENT_USER_ID, initialize_development
from app.main import create_app
from app.security import identify


def _settings(tmp_path, *, environment, skip_auth):
    values = {
        "environment": environment,
        "skip_auth": skip_auth,
        "secret": "s" * 40,
        "setup_token": "t" * 30,
        "origins": ["https://cms.invalid"],
        "public_url": "https://cms.invalid",
        "storage_dir": tmp_path / "data",
        "otel_enabled": False,
        "use_sqlite": environment == "production",
    }
    if environment != "production":
        values["database_url"] = f"sqlite:///{tmp_path / 'dev.db'}"
    return Settings(**values)


def test_production_validation_still_rejects_skip_auth():
    settings = Settings(
        environment="production",
        skip_auth=True,
        secret="s" * 40,
        setup_token="t" * 30,
        database_url="postgresql+psycopg://user:password@db.invalid/db",
        origins=["https://cms.invalid"],
        otel_enabled=False,
    )

    with pytest.raises(RuntimeError, match=r"^MOSS_SKIP_AUTH is only available when MOSS_ENV=development\.$"):
        settings.validate()

    assert settings.validated_environment is None


def test_production_skip_auth_flip_after_validation_stays_off(tmp_path):
    settings = _settings(tmp_path, environment="production", skip_auth=False)
    assert settings.validate() is settings
    assert settings.validated_environment == "production"

    with pytest.raises(
        RuntimeError,
        match=r"^MOSS_SKIP_AUTH cannot be enabled after validation when MOSS_ENV is not development\.$",
    ):
        settings.skip_auth = True
    assert settings.skip_auth is False

    with pytest.raises(RuntimeError, match=r"^MOSS_ENV cannot change after the configuration is validated\.$"):
        settings.environment = "development"
    assert settings.environment == "production"
    assert settings.skip_auth is False

    settings.skip_auth = False
    settings.environment = "production"
    assert settings.skip_auth is False


def test_development_skip_auth_flip_after_validation_stays_available(tmp_path):
    settings = _settings(tmp_path, environment="development", skip_auth=False)
    settings.validate()
    settings.skip_auth = True

    assert settings.skip_auth is True

    with pytest.raises(RuntimeError, match=r"^MOSS_ENV cannot change after the configuration is validated\.$"):
        settings.environment = "production"
    assert settings.environment == "development"


def test_development_identity_is_not_a_delivery_credential(tmp_path):
    app = create_app(_settings(tmp_path, environment="development", skip_auth=True))
    with TestClient(app) as client:
        me = client.get("/auth/me")
        assert me.status_code == 200
        account = me.json()
        assert account["user"]["id"] == DEVELOPMENT_USER_ID
        assert account["user"]["email"] == DEVELOPMENT_USER_EMAIL
        assert account["authSkipped"] is True
        headers = {"x-moss-project": account["projects"][0]["id"], "x-moss-csrf": account["csrf"]}
        created = client.post("/api/tokens", headers=headers, json={"name": "site"})
        assert created.status_code == 200
        accepted = client.get("/delivery/types", headers={"Authorization": "Bearer " + created.json()["token"]})
        assert accepted.status_code == 200
        assert accepted.json() == []
        for presented in (DEVELOPMENT_USER_ID, DEVELOPMENT_USER_EMAIL, account["user"]["name"]):
            denied = client.get("/delivery/types", headers={"Authorization": "Bearer " + presented})
            assert denied.status_code == 401
            assert denied.json()["detail"] == "A valid delivery token is required."
        client.cookies.set("moss_session", DEVELOPMENT_USER_ID)
        cookie = client.get("/delivery/types")
        client.cookies.clear()
        assert cookie.status_code == 401
        assert cookie.json()["detail"] == "A valid delivery token is required."
        request = SimpleNamespace(app=app, headers={}, cookies={})
        with app.state.db() as session:
            editor = identify(request, session, delivery=False)
            assert editor["delivery"] is False
            assert editor["actor"] == DEVELOPMENT_USER_EMAIL
            assert editor["user"].id == DEVELOPMENT_USER_ID
            with pytest.raises(HTTPException) as raised:
                identify(request, session, delivery=True)
            assert raised.value.status_code == 401
            assert raised.value.detail == "A valid delivery token is required."


def test_development_skip_auth_flip_after_start_opens_the_editor(tmp_path):
    app = create_app(_settings(tmp_path, environment="development", skip_auth=False))
    with TestClient(app) as client:
        assert client.get("/auth/me").status_code == 401
        initialize_development(app.state.db)
        app.state.settings.skip_auth = True
        me = client.get("/auth/me")
        assert me.status_code == 200
        assert me.json()["user"]["id"] == DEVELOPMENT_USER_ID
        assert me.json()["authSkipped"] is True
        denied = client.get("/delivery/types")
        assert denied.status_code == 401
        assert denied.json()["detail"] == "A valid delivery token is required."


def test_production_request_stays_signed_out_after_skip_auth_flip(tmp_path):
    app = create_app(_settings(tmp_path, environment="production", skip_auth=False))
    with TestClient(app, base_url="https://cms.invalid") as client:
        assert client.get("/auth/me").status_code == 401
        with pytest.raises(RuntimeError, match=r"^MOSS_SKIP_AUTH cannot be enabled after validation"):
            app.state.settings.skip_auth = True
        assert app.state.settings.skip_auth is False
        me = client.get("/auth/me")
        assert me.status_code == 401
        assert me.json()["detail"] == "Sign in required."
        status = client.get("/auth/status").json()
        assert status == {"initialized": False, "providers": [], "authSkipped": False}
        denied = client.get("/delivery/types")
        assert denied.status_code == 401
        assert denied.json()["detail"] == "A valid delivery token is required."
        request = SimpleNamespace(app=app, headers={}, cookies={})
        with app.state.db() as session:
            with pytest.raises(HTTPException) as raised:
                identify(request, session, delivery=False)
            assert raised.value.status_code == 401
            assert raised.value.detail == "Sign in required."
