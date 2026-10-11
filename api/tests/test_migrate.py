from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, call

import pytest
from sqlalchemy.sql.elements import TextClause

from app import migrate


@pytest.fixture
def migration(monkeypatch):
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    context = engine.connect.return_value
    context.__exit__.return_value = False
    connection = context.__enter__.return_value
    upgrade = MagicMock()
    monkeypatch.setattr(migrate.command, "upgrade", upgrade)
    calls = MagicMock()
    calls.attach_mock(engine.connect, "connect")
    calls.attach_mock(context.__enter__, "enter")
    calls.attach_mock(connection.execute, "execute")
    calls.attach_mock(upgrade, "upgrade")
    calls.attach_mock(context.__exit__, "exit")
    return SimpleNamespace(engine=engine, connection=connection, upgrade=upgrade, calls=calls)


@pytest.mark.parametrize("revision", [None, "0008"])
def test_postgres_locks_same_connection_around_upgrade(migration, revision):
    if revision is None:
        migrate.migrate(migration.engine)
    else:
        migrate.migrate(migration.engine, revision)

    assert migration.calls.mock_calls == [
        call.connect(),
        call.enter(),
        call.execute(ANY),
        call.upgrade(ANY, "head" if revision is None else revision),
        call.execute(ANY),
        call.exit(None, None, None),
    ]
    statements = [args.args[0] for args in migration.connection.execute.call_args_list]
    assert all(isinstance(statement, TextClause) for statement in statements)
    assert [str(statement) for statement in statements] == [
        "SELECT pg_advisory_lock(741582901)",
        "SELECT pg_advisory_unlock(741582901)",
    ]
    config = migration.upgrade.call_args.args[0]
    root = Path(migrate.__file__).resolve().parents[1]
    assert config.config_file_name == str(root / "alembic.ini")
    assert config.get_main_option("script_location") == str(root / "migrations")
    assert config.attributes["engine"] is migration.engine


def test_upgrade_failure_unlocks_before_connection_exit(migration):
    failure = RuntimeError("upgrade failed")
    migration.upgrade.side_effect = failure

    with pytest.raises(RuntimeError) as raised:
        migrate.migrate(migration.engine)

    assert raised.value is failure
    assert migration.calls.mock_calls == [
        call.connect(),
        call.enter(),
        call.execute(ANY),
        call.upgrade(ANY, "head"),
        call.execute(ANY),
        call.exit(RuntimeError, failure, ANY),
    ]
    assert str(migration.connection.execute.call_args.args[0]) == "SELECT pg_advisory_unlock(741582901)"


def test_lock_failure_exits_without_upgrade_or_unlock(migration):
    failure = RuntimeError("lock failed")
    migration.connection.execute.side_effect = failure

    with pytest.raises(RuntimeError) as raised:
        migrate.migrate(migration.engine)

    assert raised.value is failure
    assert migration.calls.mock_calls == [
        call.connect(),
        call.enter(),
        call.execute(ANY),
        call.exit(RuntimeError, failure, ANY),
    ]
    assert str(migration.connection.execute.call_args.args[0]) == "SELECT pg_advisory_lock(741582901)"
    migration.upgrade.assert_not_called()


def test_unlock_failure_propagates_after_connection_exit(migration):
    failure = RuntimeError("unlock failed")
    migration.connection.execute.side_effect = [None, failure]

    with pytest.raises(RuntimeError) as raised:
        migrate.migrate(migration.engine)

    assert raised.value is failure
    assert migration.calls.mock_calls == [
        call.connect(),
        call.enter(),
        call.execute(ANY),
        call.upgrade(ANY, "head"),
        call.execute(ANY),
        call.exit(RuntimeError, failure, ANY),
    ]
    assert str(migration.connection.execute.call_args.args[0]) == "SELECT pg_advisory_unlock(741582901)"


def test_non_postgres_upgrades_without_lock_connection(migration):
    migration.engine.dialect.name = "sqlite"

    migrate.migrate(migration.engine, "0008")

    assert migration.calls.mock_calls == [call.upgrade(ANY, "0008")]
    migration.engine.connect.assert_not_called()
