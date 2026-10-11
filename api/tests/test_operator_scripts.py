import argparse
import ast
import importlib.util
import io
import subprocess
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ["backup", "restore", "restore_media", "configure"])
def test_import_does_not_run_operator_commands(name, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Import must not parse CLI arguments or execute operator commands")

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", unexpected)
    monkeypatch.setattr(subprocess, "run", unexpected)
    monkeypatch.setattr(Path, "write_text", unexpected)
    monkeypatch.setattr(Path, "mkdir", unexpected)
    load_script(name)


def test_configure_preserves_existing_secrets_and_refuses_unsafe_production(tmp_path, monkeypatch):
    script = load_script("configure")
    monkeypatch.setattr(script, "__file__", str(tmp_path / "scripts/configure.py"))
    file = tmp_path / ".env"
    original = "POSTGRES_PASSWORD=change-me\nMOSS_SECRET_KEY=kept-secret\nMOSS_SETUP_TOKEN=kept-token\n"
    file.write_text(original)
    monkeypatch.setattr(sys, "argv", ["configure"])
    script.main()
    configured = file.read_text()
    assert all(line in configured for line in original.splitlines())
    assert file.stat().st_mode & 0o777 == 0o600

    for url in ["http://example.com", "https://example.com"]:
        monkeypatch.setattr(sys, "argv", ["configure", "--production", "--public-url", url])
        with pytest.raises(SystemExit):
            script.main()
        assert file.read_text() == configured


@pytest.mark.parametrize("confirmation,count", [("other", "0"), ("target", "1")])
def test_restore_rejects_mismatched_confirmation_or_nonempty_database(confirmation, count, monkeypatch):
    script = load_script("restore")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout=count)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["restore", "unused.dump", "--target", "target", "--confirm-target", confirmation])
    with pytest.raises(SystemExit):
        script.main()
    assert len(calls) == (confirmation == "target")
    assert not any("pg_restore" in argument for command in calls for argument in command)


def test_backup_removes_partial_file_when_docker_fails(tmp_path, monkeypatch):
    script = load_script("backup")

    def run(command, **kwargs):
        kwargs["stdout"].write(b"incomplete dump")
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["backup", "--directory", str(tmp_path)])
    with pytest.raises(subprocess.CalledProcessError):
        script.main()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("kind", ["file", "traversal", "symlink", "hardlink", "fifo", "nonempty"])
def test_media_restore_archive_guards(kind, tmp_path, monkeypatch):
    script = load_script("restore_media")
    backup = tmp_path / "media.tar.gz"
    with tarfile.open(backup, "w:gz") as archive:
        member = tarfile.TarInfo("../escape" if kind == "traversal" else "image.webp")
        if kind in {"symlink", "hardlink", "fifo"}:
            member.type = {"symlink": tarfile.SYMTYPE, "hardlink": tarfile.LNKTYPE, "fifo": tarfile.FIFOTYPE}[kind]
            member.linkname = "../escape"
            archive.addfile(member)
        else:
            member.size = 5
            archive.addfile(member, io.BytesIO(b"image"))
    commands = []
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: commands.append(command))
    monkeypatch.setattr(sys, "argv", ["restore_media", str(backup), "--confirm-empty-volume"])
    script.main()
    command = commands[0]
    assert command[:5] == ["docker", "compose", "run", "--rm", "--no-deps"]
    program = ast.parse(command[-1])
    root = tmp_path / "assets"
    root.mkdir()
    if kind == "nonempty":
        (root / "existing").write_bytes(b"kept")
    # Run the exact container program against an isolated temporary volume.
    program.body[1].value.args[0] = ast.Constant(str(root))
    ast.fix_missing_locations(program)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(backup.read_bytes())))
    if kind == "file":
        exec(compile(program, "media-restore", "exec"), {})
        assert (root / "image.webp").read_bytes() == b"image"
    else:
        with pytest.raises(SystemExit):
            exec(compile(program, "media-restore", "exec"), {})
        assert not (root / "image.webp").exists()
    assert not (tmp_path / "escape").exists()
    if kind == "nonempty":
        assert (root / "existing").read_bytes() == b"kept"
