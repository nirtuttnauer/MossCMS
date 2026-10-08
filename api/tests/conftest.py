import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

os.environ.setdefault("MOSS_SKIP_AUTH", "false")
os.environ.setdefault("MOSS_SECRET_KEY", "test-secret-" * 4)
os.environ.setdefault("MOSS_SETUP_TOKEN", "test-setup-" * 4)
os.environ.setdefault("MOSS_STORAGE_DIR", "/tmp/mosscms-test-default")

from app.config import Settings
from app.main import create_app

# Point the suite at a real database (e.g. PostgreSQL) to catch engine-specific
# behavior that SQLite silently no-ops (JSON path casts, SKIP LOCKED, advisory locks).
TEST_DATABASE_URL = os.environ.get("MOSS_TEST_DATABASE_URL", "")


def admin_engine():
    template = make_url(TEST_DATABASE_URL)
    return create_engine(
        template.set(database=template.database).render_as_string(hide_password=False),
        execution_options={"isolation_level": "AUTOCOMMIT"},
    )


def database_url(tmp_path):
    if not TEST_DATABASE_URL:
        return f"sqlite:///{tmp_path}/cms.db"
    template = make_url(TEST_DATABASE_URL)
    if template.drivername.startswith("sqlite"):
        return f"sqlite:///{tmp_path}/cms.db"
    if not template.drivername.startswith("postgresql"):
        raise RuntimeError("MOSS_TEST_DATABASE_URL must be sqlite or postgresql for per-test isolation.")
    # A fresh, isolated database per test: drop-if-exists then create. Tests never share state.
    database = f"moss_test_{uuid.uuid4().hex[:8]}"
    engine = admin_engine()
    with engine.begin() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{database}"'))
        connection.execute(text(f'CREATE DATABASE "{database}"'))
    engine.dispose()
    return template.set(database=database).render_as_string(hide_password=False)


def drop_test_database(url):
    if not TEST_DATABASE_URL:
        return
    if not make_url(TEST_DATABASE_URL).drivername.startswith("postgresql"):
        return
    database = make_url(url).database
    engine = admin_engine()
    with engine.begin() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{database}"'))
    engine.dispose()


@pytest.fixture
def app(tmp_path):
    url = database_url(tmp_path)
    application = create_app(
        Settings(
            database_url=url,
            skip_auth=False,
            secret="s" * 40,
            setup_token="t" * 30,
            storage_dir=tmp_path / "media",
        )
    )
    yield application
    drop_test_database(url)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def admin(client):
    response = client.post(
        "/auth/setup",
        json={"token": "t" * 30, "email": "admin@example.com", "password": "secure-test-password", "name": "Admin"},
    )
    assert response.status_code == 200, response.text
    account = client.get("/auth/me").json()
    headers = {"x-moss-project": account["projects"][0]["id"], "x-moss-csrf": account["csrf"]}
    return headers


def gql(client, headers, query, variables=None, delivery=False):
    response = client.post(
        "/delivery/graphql" if delivery else "/graphql", json={"query": query, "variables": variables}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def define(client, headers, key="article", fields=None):
    fields = fields or [
        {"name": "title", "type": "text", "required": True},
        {"name": "body", "type": "richText"},
        {"name": "secret", "type": "text", "private": True},
    ]
    result = gql(
        client,
        headers,
        "mutation($key:String!,$fields:JSON!){saveContentType(key:$key,name:$key,fields:$fields){id key version}}",
        {"key": key, "fields": fields},
    )
    assert "errors" not in result, result
    return result["data"]["saveContentType"]


def entry(client, headers, slug="hello", data=None, status="draft", key="article", **extra):
    result = gql(
        client,
        headers,
        "mutation($key:String!,$slug:String!,$data:JSON!,$status:String!,$id:ID,$version:Int,$scheduledAt:String){saveEntry(typeKey:$key,slug:$slug,data:$data,status:$status,id:$id,version:$version,scheduledAt:$scheduledAt){id slug data status version}}",
        {
            "key": key,
            "slug": slug,
            "data": data or {"title": slug, "body": "text", "secret": "hidden"},
            "status": status,
            **extra,
        },
    )
    return result
