import os
import sys
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

import required_runs

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


_DESELECTED = []


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "postgres: PostgreSQL-only test; excluded from the SQLite required run with -m 'not postgres'",
    )
    config.addinivalue_line(
        "markers",
        "compose: Docker Compose test; included in both required runs and never skipped at runtime",
    )
    _DESELECTED.clear()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_collection_modifyitems(config, items):
    collected = list(items)
    yield
    config.stash[required_runs.COLLECTED] = collected


def pytest_deselected(items):
    _DESELECTED.extend(item.nodeid for item in items)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.outcome == "skipped" or hasattr(report, "wasxfail"):
        required_runs.reject_runtime_skip(report)


def _call_nodeids(reports):
    return sorted(report.nodeid for report in reports if getattr(report, "when", None) == "call")


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    stats = reporter.stats if reporter else {}
    leftover = []
    for key in ("skipped", "xfailed", "xpassed"):
        leftover.extend(getattr(report, "nodeid", key) for report in stats.get(key, []))
    if leftover:
        message = "runtime skip is a failure; there is no allowed-skip list:\n  " + "\n  ".join(map(str, leftover))
        print(message, file=sys.stderr)
        if session.exitstatus == 0:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    run = os.environ.get("MOSS_REQUIRED_RUN")
    if not run or session.config.option.collectonly:
        return
    manifest = required_runs.load_manifest()
    if run not in manifest["runs"]:
        print(f"MOSS_REQUIRED_RUN={run!r} is not a required run", file=sys.stderr)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        return
    collected_items = session.config.stash.get(required_runs.COLLECTED, [])
    collected = sorted(item.nodeid for item in collected_items)
    deselected = sorted(set(_DESELECTED))
    failed = sorted(
        {report.nodeid for key in ("failed", "error") for report in stats.get(key, []) if hasattr(report, "nodeid")}
    )
    skipped = sorted(set(map(str, leftover)))
    passed = _call_nodeids(stats.get("passed", []))
    required_runs.write_result(
        run,
        {
            "run": run,
            "marker": manifest["runs"][run]["marker"],
            "collected": collected,
            "deselected": deselected,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
        },
    )
    expected = manifest["runs"][run]["deselected"]
    problems = []
    if deselected != expected:
        problems.append(
            f"{run} deselected ids do not match the committed list\n"
            f"  missing from run: {sorted(set(expected) - set(deselected))}\n"
            f"  extra in run: {sorted(set(deselected) - set(expected))}"
        )
    if not failed and not skipped and passed != sorted(set(collected) - set(expected)):
        problems.append(f"{run} passed ids do not match the committed selection")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        if session.exitstatus == 0:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
