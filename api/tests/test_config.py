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
    "database_url",
    [
        "sqlite:///fake.db",
        "postgresql://fake-user:change-me@db.invalid/fake-db",
        "postgresql://fake-user@db.invalid/fake-db",
    ],
)
def test_production_database_guard_still_runs_after_normalization(settings, database_url):
    settings.environment = "production"
    settings.database_url = database_url

    with pytest.raises(RuntimeError) as error:
        settings.validate()

    assert str(error.value) == "Production requires PostgreSQL and a non-default database password."
    assert settings.origins == ["https://cms.invalid"]
