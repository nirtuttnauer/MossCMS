import argparse
import builtins
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
import sqlalchemy
from PIL import Image  # noqa: F401
from sqlalchemy.exc import ArgumentError

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
NAMES = ["release_fixture", "release_http_acceptance"]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unexpected(*args, **kwargs):
    pytest.fail("Release script must not perform this side effect")


@pytest.mark.parametrize("name", NAMES)
def test_import_has_no_command_side_effects(name, monkeypatch):
    # Preload dependencies above so the assertions apply to script initialization.
    monkeypatch.delenv("MOSS_RELEASE_DATABASE_URL", raising=False)
    monkeypatch.delenv("MOSS_RELEASE_NODE", raising=False)
    monkeypatch.setattr(sys, "argv", [name, "invalid-action"])
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", unexpected)
    monkeypatch.setattr(type(os.environ), "__getitem__", unexpected)
    monkeypatch.setattr(sqlalchemy, "create_engine", unexpected)
    monkeypatch.setattr(subprocess, "Popen", unexpected)
    monkeypatch.setattr(subprocess, "run", unexpected)
    monkeypatch.setattr(httpx, "Client", unexpected)
    monkeypatch.setattr(builtins, "open", unexpected)
    monkeypatch.setattr(Path, "write_text", unexpected)
    monkeypatch.setattr(Path, "mkdir", unexpected)
    monkeypatch.setitem(sys.modules, "app.migrate", SimpleNamespace(migrate=unexpected))
    original_import = builtins.__import__

    def import_dependency(name, *args, **kwargs):
        if name == "app.migrate":
            unexpected()
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_dependency)
    original_path = sys.path.copy()
    module = load_script(name)
    assert callable(module.main)
    assert sys.path == original_path


def forbid_commands(module, monkeypatch):
    monkeypatch.setattr(sys, "argv", [module.__name__, "seed"])
    monkeypatch.setattr(sys, "path", sys.path.copy())
    monkeypatch.setitem(sys.modules, "app.migrate", SimpleNamespace(migrate=unexpected))
    monkeypatch.setattr(sqlalchemy, "create_engine", unexpected)
    if module.__name__ == "release_fixture":
        monkeypatch.setattr(module, "create_engine", unexpected)
    monkeypatch.setattr(subprocess, "Popen", unexpected)
    monkeypatch.setattr(subprocess, "run", unexpected)
    monkeypatch.setattr(httpx, "Client", unexpected)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize(
    "database_url,error,message",
    [
        ("malformed", ArgumentError, "Could not parse SQLAlchemy URL"),
        ("postgresql://example.com/moss_release_fixture", SystemExit, "loopback moss_release_"),
        ("postgresql://[::1]/moss_release_fixture", SystemExit, "loopback moss_release_"),
        ("postgresql://localhost/production", SystemExit, "loopback moss_release_"),
        ("postgresql://127.0.0.1", SystemExit, "loopback moss_release_"),
    ],
)
def test_database_guard_refuses_before_database_or_subprocess(name, database_url, error, message, monkeypatch):
    module = load_script(name)
    forbid_commands(module, monkeypatch)
    monkeypatch.setenv("MOSS_RELEASE_DATABASE_URL", database_url)
    with pytest.raises(error, match=message):
        module.main()


def test_fixture_parses_action_before_requiring_environment(monkeypatch):
    module = load_script("release_fixture")
    forbid_commands(module, monkeypatch)
    monkeypatch.setattr(sys, "argv", [module.__name__, "invalid-action"])
    monkeypatch.delenv("MOSS_RELEASE_DATABASE_URL", raising=False)
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2


def test_fixture_seed_refuses_nonempty_database_before_migration(monkeypatch):
    module = load_script("release_fixture")
    forbid_commands(module, monkeypatch)
    monkeypatch.setenv("MOSS_RELEASE_DATABASE_URL", "postgresql://localhost/moss_release_fixture")
    engine = object()
    monkeypatch.setattr(module, "create_engine", lambda url: engine)
    inspected = []

    def inspect(target):
        inspected.append(target)
        return SimpleNamespace(get_table_names=lambda: ["existing_table"])

    monkeypatch.setattr(module, "inspect", inspect)
    with pytest.raises(SystemExit, match="Seed requires an empty disposable database\\."):
        module.main()
    assert inspected == [engine]


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
@pytest.mark.parametrize("users,entries", [(1, 1004), (0, 1003), (0, 1005)])
def test_acceptance_refuses_dirty_fixture_before_starting_processes(host, users, entries, monkeypatch):
    module = load_script("release_http_acceptance")
    forbid_commands(module, monkeypatch)
    monkeypatch.setenv("MOSS_RELEASE_DATABASE_URL", f"postgresql://{host}/moss_release_fixture")
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.side_effect = [
        SimpleNamespace(scalar_one=lambda: users),
        SimpleNamespace(scalar_one=lambda: entries),
    ]
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda url: engine)
    with pytest.raises(
        SystemExit, match="Restore the clean 1004-entry fixture with no accounts before this walkthrough\\."
    ):
        module.main()
    queries = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert queries == ["select count(*) from users"] + (
        ["select count(*) from entries where id like 'legacy-%'"] if users == 0 else []
    )
    engine.connect.return_value.__exit__.assert_called_once()


def test_acceptance_disposes_clean_fixture_and_stops_api_on_client_failure(monkeypatch):
    module = load_script("release_http_acceptance")
    forbid_commands(module, monkeypatch)
    database_url = "postgresql://localhost/moss_release_fixture"
    monkeypatch.setenv("MOSS_RELEASE_DATABASE_URL", database_url)
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    connection.execute.side_effect = [SimpleNamespace(scalar_one=lambda: 0), SimpleNamespace(scalar_one=lambda: 1004)]
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda url: engine)
    api = MagicMock()
    processes = []

    def start(command, **kwargs):
        processes.append((command, kwargs))
        return api

    def client(**kwargs):
        raise RuntimeError("client initialization failed")

    monkeypatch.setattr(subprocess, "Popen", start)
    monkeypatch.setattr(httpx, "Client", client)
    with pytest.raises(RuntimeError, match="client initialization failed"):
        module.main()
    engine.dispose.assert_called_once_with()
    assert len(processes) == 1
    command, options = processes[0]
    assert command == [
        str(module.ROOT / "api/.venv/bin/python"),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "18033",
        "--no-access-log",
    ]
    assert options["cwd"] == module.ROOT / "api"
    assert options["env"]["DATABASE_URL"] == database_url
    assert options["env"]["MOSS_SKIP_AUTH"] == "false"
    assert options["stdout"] == options["stderr"] == subprocess.DEVNULL
    api.terminate.assert_called_once_with()
    api.wait.assert_called_once_with(timeout=10)
