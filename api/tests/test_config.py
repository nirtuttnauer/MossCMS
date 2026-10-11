from pathlib import Path

import pytest

from app.config import Settings, normalized_origins


@pytest.fixture
def settings():
    return Settings(
        database_url="postgresql+psycopg://fake-user:fake-password@db.invalid/fake-db",
        environment="development",
        skip_auth=False,
        secret="s" * 32,
        setup_token="t" * 24,
        origins=["https://cms.invalid/"],
        storage_dir=Path("/unused-test-storage"),
        public_url="https://cms.invalid",
        s3_bucket="",
        s3_endpoint=None,
        webhook_origins=[],
    )


@pytest.mark.parametrize(
    "environment,origins,expected",
    [
        ("development", [], []),
        ("development", ["", "/", "///", "https://cms.invalid///"], ["", "https://cms.invalid"]),
        (
            "development",
            ["http://localhost:8001/", "http://127.0.0.1:5173/", "https://cms.invalid/"],
            [
                "http://localhost:8001",
                "http://127.0.0.1:5173",
                "https://cms.invalid",
                "http://127.0.0.1:8001",
                "http://localhost:5173",
            ],
        ),
        (
            "development",
            ["http://localhost:8001", "http://127.0.0.1:8001/", "http://localhost:8001/"],
            ["http://localhost:8001", "http://127.0.0.1:8001"],
        ),
        (
            "development",
            ["https://localhost.example/path://127.0.0.1/"],
            ["https://localhost.example/path://127.0.0.1", "https://127.0.0.1.example/path://127.0.0.1"],
        ),
        ("production", ["", "http://localhost:8001/", "http://localhost:8001"], ["http://localhost:8001"] * 2),
        ("staging", ["http://127.0.0.1:5173/", "http://127.0.0.1:5173"], ["http://127.0.0.1:5173"] * 2),
        ("Development", ["http://localhost:8001/"], ["http://localhost:8001"]),
    ],
)
def test_normalized_origins_preserves_rules_and_input(environment, origins, expected):
    original = list(origins)
    result = normalized_origins(origins, environment)

    assert result == expected
    assert origins == original
    assert result is not origins


@pytest.mark.parametrize("environment", ["development", "staging", "production"])
def test_validate_assigns_normalized_origins_and_returns_self(settings, environment):
    settings.environment = environment
    original = ["", "http://localhost:8001/", "http://localhost:8001"]
    settings.origins = original

    assert settings.validate() is settings
    assert settings.origins == normalized_origins(original, environment)
    assert settings.origins is not original
    assert original == ["", "http://localhost:8001/", "http://localhost:8001"]


@pytest.mark.parametrize("field,value", [("secret", "s" * 31), ("setup_token", "t" * 23)])
def test_credential_failure_leaves_origins_untouched(settings, field, value):
    setattr(settings, field, value)
    original = ["*///", ""]
    settings.origins = original

    with pytest.raises(RuntimeError) as error:
        settings.validate()

    assert str(error.value) == (
        "Set MOSS_SECRET_KEY (32+ characters) and MOSS_SETUP_TOKEN (24+ characters). Run scripts/configure.py."
    )
    assert settings.origins is original
    assert original == ["*///", ""]


def test_skip_auth_failure_precedes_credentials_and_normalization(settings):
    settings.environment = "production"
    settings.skip_auth = True
    settings.secret = ""
    original = ["*///"]
    settings.origins = original

    with pytest.raises(RuntimeError, match=r"^MOSS_SKIP_AUTH is only available when MOSS_ENV=development\.$"):
        settings.validate()

    assert settings.origins is original


@pytest.mark.parametrize("origins,expected", [([], []), ([""], []), (["*///", ""], ["*"])])
def test_invalid_origins_fail_after_normalization_before_database_check(settings, origins, expected):
    settings.environment = "production"
    settings.database_url = "invalid database url"
    settings.origins = origins

    with pytest.raises(RuntimeError, match=r"^MOSS_ORIGINS must contain explicit trusted origins\.$"):
        settings.validate()

    assert settings.origins == expected
    assert settings.origins is not origins


def test_slash_only_origin_keeps_existing_validation_behavior(settings):
    settings.origins = ["///"]

    assert settings.validate() is settings
    assert settings.origins == [""]


@pytest.mark.parametrize(
    "database_url,message",
    [
        ("sqlite:///fake.db", "Production SQLite requires MOSS_USE_SQLITE=true."),
        (
            "postgresql://fake-user:change-me@db.invalid/fake-db",
            "Production requires PostgreSQL and a non-default database password.",
        ),
        (
            "postgresql://fake-user@db.invalid/fake-db",
            "Production requires PostgreSQL and a non-default database password.",
        ),
    ],
)
def test_production_database_guard_still_runs_after_normalization(settings, database_url, message):
    settings.environment = "production"
    settings.database_url = database_url

    with pytest.raises(RuntimeError) as error:
        settings.validate()

    assert str(error.value) == message
    assert settings.origins == ["https://cms.invalid"]


@pytest.mark.parametrize("flag", ["true", "TRUE", "1", "yes"])
def test_sqlite_flag_overrides_postgres_and_database_url(flag, tmp_path, monkeypatch):
    monkeypatch.setenv("MOSS_USE_SQLITE", flag)
    monkeypatch.setenv("MOSS_STORAGE_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused.invalid/db")
    monkeypatch.setenv("POSTGRES_HOST", "unused.invalid")
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)

    settings = Settings()

    assert settings.use_sqlite is True
    assert settings.database_url == f"sqlite:///{tmp_path / 'data' / 'mosscms.db'}"


@pytest.mark.parametrize("flag", [None, "false", "0", "no"])
def test_disabled_sqlite_flag_preserves_database_url(flag, monkeypatch):
    if flag is None:
        monkeypatch.delenv("MOSS_USE_SQLITE", raising=False)
    else:
        monkeypatch.setenv("MOSS_USE_SQLITE", flag)
    url = "postgresql+psycopg://user:password@db.invalid/db"
    monkeypatch.setenv("DATABASE_URL", url)

    settings = Settings()

    assert settings.use_sqlite is False
    assert settings.database_url == url


def test_explicit_sqlite_setting_runs_in_production_and_retains_data(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    settings = Settings(
        use_sqlite=True,
        environment="production",
        skip_auth=False,
        secret="s" * 32,
        setup_token="t" * 24,
        storage_dir=tmp_path / "persistent" / "data",
        public_url="https://cms.invalid",
        origins=["https://cms.invalid"],
    )
    with TestClient(create_app(settings), base_url="https://cms.invalid") as client:
        assert client.get("/ready").status_code == 200
        response = client.post(
            "/auth/setup",
            json={"token": "t" * 24, "email": "admin@example.com", "password": "secure-test-password", "name": "Admin"},
        )
        assert response.status_code == 200, response.text
        assert client.get("/auth/me").status_code == 200
    assert (settings.storage_dir / "mosscms.db").is_file()
    with TestClient(create_app(settings), base_url="https://cms.invalid") as client:
        response = client.post("/auth/login", json={"email": "admin@example.com", "password": "secure-test-password"})
        assert response.status_code == 200, response.text
        assert client.get("/auth/me").status_code == 200
