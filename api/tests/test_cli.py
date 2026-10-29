import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, call

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import accounts, cli, security
from app.models import Audit, Token


@pytest.fixture
def operator(monkeypatch):
    engine = MagicMock()
    factory = MagicMock()
    transaction = factory.begin.return_value
    transaction.__exit__.return_value = False
    session = transaction.__enter__.return_value
    settings = SimpleNamespace(database_url="mock-database", public_url="https://example.test")
    settings_class = MagicMock()
    settings_class.return_value.validate.return_value = settings
    monkeypatch.setattr(cli, "Settings", settings_class)
    monkeypatch.setattr(cli, "load_dotenv", MagicMock())
    monkeypatch.setattr(cli, "database", MagicMock(return_value=(engine, factory)))
    monkeypatch.setattr(cli, "migrate", MagicMock())
    monkeypatch.setattr(cli, "save_type", MagicMock())
    monkeypatch.setattr(cli, "save_entry", MagicMock())
    monkeypatch.setattr(cli, "issue_token", MagicMock())
    monkeypatch.setattr(cli, "audit", MagicMock())
    server = MagicMock()
    monkeypatch.setitem(sys.modules, "uvicorn", server)
    return SimpleNamespace(engine=engine, factory=factory, transaction=transaction, session=session, server=server)


def test_reindex_is_explicit_and_workspace_scoped(operator, monkeypatch, capsys):
    from app import indexing

    monkeypatch.setattr(indexing, "rebuild", MagicMock(return_value=42))
    monkeypatch.setattr(sys, "argv", ["moss", "reindex", "--project", "workspace"])
    cli.main()
    assert indexing.rebuild.call_args.args[-1] == "workspace"
    assert '"entries": 42' in capsys.readouterr().out
    operator.engine.dispose.assert_called_once_with()


def test_reindex_requires_workspace(operator, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["moss", "reindex"])
    with pytest.raises(SystemExit):
        cli.main()
    assert "--project is required" in capsys.readouterr().err
    operator.factory.begin.assert_not_called()


def test_migrate_disposes_after_success(operator, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["moss", "migrate"])
    calls = MagicMock()
    calls.attach_mock(cli.migrate, "migrate")
    calls.attach_mock(operator.engine.dispose, "dispose")

    cli.main()

    assert calls.mock_calls == [call.migrate(operator.engine), call.dispose()]
    cli.database.assert_called_once_with("mock-database")
    operator.factory.begin.assert_not_called()


@pytest.mark.parametrize("command", ["migrate", "serve"])
def test_migration_failure_disposes_and_preserves_failure(operator, monkeypatch, command):
    monkeypatch.setattr(sys, "argv", ["moss", command])
    failure = RuntimeError("migration failed")
    cli.migrate.side_effect = failure

    with pytest.raises(RuntimeError) as raised:
        cli.main()

    assert raised.value is failure
    cli.migrate.assert_called_once_with(operator.engine)
    operator.server.run.assert_not_called()
    operator.engine.dispose.assert_called_once_with()


def test_serve_failure_disposes_and_preserves_failure(operator, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["moss", "serve"])
    monkeypatch.setenv("PORT", "8123")
    failure = RuntimeError("server failed")
    operator.server.run.side_effect = failure
    calls = MagicMock()
    calls.attach_mock(cli.migrate, "migrate")
    calls.attach_mock(operator.server.run, "serve")
    calls.attach_mock(operator.engine.dispose, "dispose")

    with pytest.raises(RuntimeError) as raised:
        cli.main()

    assert raised.value is failure
    assert calls.mock_calls == [
        call.migrate(operator.engine),
        call.serve("app.main:app", host="0.0.0.0", port=8123, log_level="info", timeout_graceful_shutdown=20),
        call.dispose(),
    ]


@pytest.mark.parametrize(
    "arguments,message,starts_transaction",
    [
        (["reset-password"], "--email is required", False),
        (["seed"], "--project is required; seeding is always explicit", False),
        (["reset-password", "--email", "missing@example.test"], "Account not found", True),
        (["seed", "--project", "missing-project"], "Project administrator not found", True),
    ],
)
def test_command_validation_disposes(operator, monkeypatch, capsys, arguments, message, starts_transaction):
    monkeypatch.setattr(sys, "argv", ["moss", *arguments])
    operator.session.scalar.return_value = None

    with pytest.raises(SystemExit) as raised:
        cli.main()

    assert raised.value.code == 2
    output = capsys.readouterr()
    assert message in output.err
    assert output.out == ""
    cli.database.assert_called_once_with("mock-database")
    operator.engine.dispose.assert_called_once_with()
    assert operator.factory.begin.call_count == int(starts_transaction)
    if starts_transaction:
        operator.transaction.__exit__.assert_called_once_with(SystemExit, raised.value, ANY)
        assert operator.transaction.__exit__.call_args.args[2] is not None
    cli.issue_token.assert_not_called()
    cli.audit.assert_not_called()
    cli.save_type.assert_not_called()
    cli.save_entry.assert_not_called()


@pytest.mark.parametrize("failing_operation", ["save_type", "save_entry"])
def test_seed_failure_exits_transaction_and_disposes(operator, monkeypatch, capsys, failing_operation):
    monkeypatch.setattr(sys, "argv", ["moss", "seed", "--project", "workspace"])
    operator.session.scalar.side_effect = [SimpleNamespace(user_id="admin"), None, None]
    failure = RuntimeError("seed failed")
    getattr(cli, failing_operation).side_effect = failure
    calls = MagicMock()
    calls.attach_mock(operator.transaction.__exit__, "exit_transaction")
    calls.attach_mock(operator.engine.dispose, "dispose")

    with pytest.raises(RuntimeError) as raised:
        cli.main()

    assert raised.value is failure
    assert calls.mock_calls == [call.exit_transaction(RuntimeError, failure, ANY), call.dispose()]
    assert operator.transaction.__exit__.call_args.args[2] is not None
    operator.factory.begin.assert_called_once_with()
    assert capsys.readouterr().out == ""
    if failing_operation == "save_type":
        cli.save_entry.assert_not_called()


def test_seed_keeps_existing_content_and_disposes(operator, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["moss", "seed", "--project", "workspace"])
    operator.session.scalar.side_effect = [SimpleNamespace(user_id="admin"), object(), "existing-entry"]

    cli.main()

    cli.save_type.assert_not_called()
    cli.save_entry.assert_not_called()
    operator.transaction.__exit__.assert_called_once_with(None, None, None)
    operator.engine.dispose.assert_called_once_with()
    assert capsys.readouterr().out == '{"seeded": "workspace"}\n'


def test_claim_workspace_is_scoped_and_refuses_existing_members(client, admin, app, monkeypatch):
    from sqlalchemy import select
    from app.models import Membership, Project, User

    with app.state.db.begin() as session:
        unowned = Project(name="Old example")
        other = Project(name="Other unowned")
        session.add_all([unowned, other])
        session.flush()
        target, other_id = unowned.id, other.id
        user_id = session.scalar(select(User.id).where(User.email == "admin@example.com"))
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "Settings", lambda: SimpleNamespace(validate=lambda: SimpleNamespace(database_url="test")))
    monkeypatch.setattr(cli, "database", lambda url: (MagicMock(), app.state.db))
    monkeypatch.setattr(sys, "argv", ["moss", "claim-workspace", "--project", target, "--email", "admin@example.com"])
    cli.main()
    with app.state.db() as session:
        assert session.get(Membership, (target, user_id)).role == "admin"
        assert session.scalar(select(Membership.user_id).where(Membership.project_id == other_id)) is None
    with pytest.raises(SystemExit):
        cli.main()


def _bind_operator_cli(app, monkeypatch, public_url):
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        cli,
        "Settings",
        lambda: SimpleNamespace(validate=lambda: SimpleNamespace(database_url="test", public_url=public_url)),
    )
    monkeypatch.setattr(cli, "database", lambda url: (MagicMock(), app.state.db))


def _issue_reset(app, monkeypatch, capsys, email, public_url="https://cms.example.test/"):
    _bind_operator_cli(app, monkeypatch, public_url)
    monkeypatch.setattr(sys, "argv", ["moss", "reset-password", "--email", email])
    cli.main()
    output = capsys.readouterr()
    assert output.err == ""
    link = output.out.strip()
    prefix = public_url.rstrip("/") + "/#reset/"
    assert link.startswith(prefix)
    token = link.removeprefix(prefix)
    assert token and "/" not in token
    return token


def _accept(http, token, password):
    return http.post(
        "/auth/accept",
        json={"token": token, "email": "admin@example.com", "password": password, "name": "Admin"},
    )


def test_reset_password_cli_link_replaces_the_password_once(client, admin, app, monkeypatch, capsys):
    replaced = _issue_reset(app, monkeypatch, capsys, " Admin@Example.com ")
    current = _issue_reset(app, monkeypatch, capsys, "admin@example.com")
    assert replaced != current
    with app.state.db() as session:
        assert session.get(Token, security.digest(replaced)) is None
        assert session.get(Token, security.digest(current)).kind == "reset"
        issued = session.scalars(select(Audit).where(Audit.action == "account.recovery.issue")).all()
        assert len(issued) == 2
        assert {row.actor for row in issued} == {"operator"}
        assert all(row.details["userId"] for row in issued)
    assert _accept(client, replaced, "unused-password-value").status_code == 400
    owner = TestClient(app)
    assert _accept(owner, current, "replacement-password").status_code == 200
    assert client.get("/auth/me").status_code == 401
    assert _accept(owner, current, "replacement-password").status_code == 400
    assert (
        owner.post("/auth/login", json={"email": "admin@example.com", "password": "secure-test-password"}).status_code
        == 401
    )
    assert (
        owner.post("/auth/login", json={"email": "admin@example.com", "password": "replacement-password"}).status_code
        == 200
    )


def test_reset_password_cli_link_expires_on_an_injected_clock(client, admin, app, monkeypatch, capsys):
    start = datetime(2026, 10, 29, 12, 0, 0)
    clock = {"at": start}

    def frozen_now():
        return clock["at"]

    monkeypatch.setattr(security, "now", frozen_now)
    monkeypatch.setattr(accounts, "now", frozen_now)
    early = _issue_reset(app, monkeypatch, capsys, "admin@example.com")
    clock["at"] = start + timedelta(days=1) - timedelta(seconds=1)
    owner = TestClient(app)
    assert _accept(owner, early, "replacement-password").status_code == 200
    late = _issue_reset(app, monkeypatch, capsys, "admin@example.com")
    clock["at"] = clock["at"] + timedelta(days=1)
    expired = _accept(TestClient(app), late, "another-password-value")
    assert expired.status_code == 400
    assert expired.json()["detail"] == "This invitation or recovery link is invalid or expired."
    with app.state.db() as session:
        assert session.get(Token, security.digest(late)) is not None
        assert session.scalar(select(func.count()).select_from(Token).where(Token.kind == "reset")) == 1
    assert (
        owner.post("/auth/login", json={"email": "admin@example.com", "password": "secure-test-password"}).status_code
        == 401
    )
    assert (
        owner.post("/auth/login", json={"email": "admin@example.com", "password": "replacement-password"}).status_code
        == 200
    )
    assert (
        owner.post("/auth/login", json={"email": "admin@example.com", "password": "another-password-value"}).status_code
        == 401
    )
