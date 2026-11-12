from pathlib import Path
from urllib.parse import urlsplit

import pytest

from app.config import Settings


def _settings():
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


@pytest.fixture
def settings():
    return _settings()


SCHEME_MESSAGE = r"^MOSS_ORIGINS entries must be http\(s\) origins with a host\.$"

REJECTED = [
    "file:",
    "file://",
    "file:///",
    "file:///etc/passwd",
    "FILE:///",
    "data:",
    "data:text/html,hi",
    "DATA:text/plain,x",
    "javascript:",
    "javascript:alert(1)",
    "JAVASCRIPT:alert(1)",
    "cms.invalid",
    "localhost:8001",
    "//cms.invalid",
    "http://",
    "https://",
    "HTTP://",
    "https:///",
    "http:///tmp",
    "http://[",
    "ftp://files.example",
    "ws://cms.invalid",
    "file://localhost/tmp",
]


@pytest.mark.parametrize("origin", REJECTED)
def test_validate_rejects_non_http_scheme_or_missing_host(settings, origin):
    settings.origins = [origin]

    with pytest.raises(RuntimeError, match=SCHEME_MESSAGE):
        settings.validate()

    assert settings.origins == []
    assert origin not in settings.origins
    assert "file:///" not in settings.origins


def test_dangerous_origin_does_not_remain_beside_a_valid_origin(settings):
    original = [
        "https://cms.invalid/",
        "file:///",
        "data:text/html,hi",
        "javascript:alert(1)",
        "cms.invalid",
        "http://",
    ]
    settings.origins = original

    with pytest.raises(RuntimeError, match=SCHEME_MESSAGE):
        settings.validate()

    assert original == [
        "https://cms.invalid/",
        "file:///",
        "data:text/html,hi",
        "javascript:alert(1)",
        "cms.invalid",
        "http://",
    ]
    assert settings.origins == ["https://cms.invalid"]
    assert "file:///" not in settings.origins
    assert "file:" not in settings.origins
    for kept in settings.origins:
        parsed = urlsplit(kept)
        assert parsed.scheme in {"http", "https"}
        assert parsed.hostname


def test_development_mirroring_does_not_keep_a_file_origin(settings):
    settings.environment = "development"
    settings.origins = ["file://localhost/tmp"]

    with pytest.raises(RuntimeError, match=SCHEME_MESSAGE):
        settings.validate()

    assert settings.origins == []
    assert "file://localhost/tmp" not in settings.origins
    assert "file://127.0.0.1/tmp" not in settings.origins


@pytest.mark.parametrize(
    "environment,origins,expected",
    [
        (
            "development",
            ["http://localhost:8001/", "https://cms.invalid/"],
            ["http://localhost:8001", "https://cms.invalid", "http://127.0.0.1:8001"],
        ),
        (
            "development",
            ["http://127.0.0.1:5173/"],
            ["http://127.0.0.1:5173", "http://localhost:5173"],
        ),
        (
            "staging",
            ["https://cms.invalid/", "http://localhost:8001/"],
            ["https://cms.invalid", "http://localhost:8001"],
        ),
        ("production", ["https://cms.invalid/"], ["https://cms.invalid"]),
        ("production", ["http://localhost:8001/"], ["http://localhost:8001"]),
        ("staging", ["http://[::1]:5173/"], ["http://[::1]:5173"]),
    ],
)
def test_http_and_https_origins_with_a_host_validate(settings, environment, origins, expected):
    settings.environment = environment
    settings.origins = list(origins)

    assert settings.validate() is settings
    assert settings.origins == expected
    assert settings.origins is not origins


def test_star_and_production_database_guards_stay_in_place(settings):
    settings.origins = ["*///", ""]
    with pytest.raises(RuntimeError, match=r"^MOSS_ORIGINS must contain explicit trusted origins\.$"):
        settings.validate()
    assert settings.origins == ["*"]

    settings.environment = "production"
    settings.database_url = "postgresql://fake-user:change-me@db.invalid/fake-db"
    settings.origins = ["https://cms.invalid"]
    with pytest.raises(RuntimeError, match=r"^Production requires PostgreSQL and a non-default database password\.$"):
        settings.validate()
    assert settings.origins == ["https://cms.invalid"]

    settings.database_url = "sqlite:///fake.db"
    settings.origins = ["https://cms.invalid"]
    with pytest.raises(RuntimeError, match=r"^Production SQLite requires MOSS_USE_SQLITE=true\.$"):
        settings.validate()
    assert settings.origins == ["https://cms.invalid"]


def test_credential_failure_still_leaves_a_file_origin_untouched(settings):
    settings.secret = "s" * 31
    original = ["file:///"]
    settings.origins = original

    with pytest.raises(RuntimeError) as error:
        settings.validate()

    assert str(error.value) == (
        "Set MOSS_SECRET_KEY (32+ characters) and MOSS_SETUP_TOKEN (24+ characters). Run scripts/configure.py."
    )
    assert settings.origins is original
    assert original == ["file:///"]
