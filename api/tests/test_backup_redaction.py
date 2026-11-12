import ast
import gzip
import importlib.util
import io
import subprocess
import sys
import tarfile
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
PLANTED = "change-me"


def load_script(name):
    spec = importlib.util.spec_from_file_location(f"redaction_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def env_part(part):
    return part == ".env" or part.startswith(".env.")


def write_password(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"POSTGRES_PASSWORD={PLANTED}\n")


def fixture_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    data = workspace / "data"
    (data / "uploads").mkdir(parents=True)
    (data / "uploads" / "cover.webp").write_bytes(b"image-bytes")
    (data / "mosscms.db").write_bytes(b"sqlite-ok")
    (data / ".environment").write_text("keep-environment\n")
    (workspace / "ROOT_ONLY.txt").write_text("workspace-root-marker\n")
    for relative in (
        ".env",
        ".env.local",
        ".env.production",
        ".env.example",
        "example-site/.env",
        "data/.env",
        "data/.env.local",
        "data/nested/.env.production",
        "data/nested/.env/secret",
    ):
        write_password(workspace / relative)
    return workspace, data


def run_backup(monkeypatch, workspace, data, destination, database_only=False):
    script = load_script("backup")
    scripts = workspace / "scripts"
    scripts.mkdir(exist_ok=True)
    monkeypatch.setattr(script, "__file__", str(scripts / "backup.py"))
    real_run = subprocess.run
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        stdout = kwargs["stdout"]
        if "pg_dump" in command[-1]:
            assert command[:5] == ["docker", "compose", "exec", "-T", "db"]
            stdout.write(b"PGDMP")
            return subprocess.CompletedProcess(command, 0)
        entry_at = command.index("--entrypoint")
        assert command[entry_at + 1] == "tar"
        assert command[entry_at + 2] == "app"
        rewritten = ["tar"]
        for arg in command[entry_at + 3 :]:
            rewritten.append(str(data) if arg == "/data" else arg)
        real_run(rewritten, stdout=stdout, check=True)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    argv = ["backup", "--directory", str(destination)]
    if database_only:
        argv.insert(1, "--database-only")
    monkeypatch.setattr(sys, "argv", argv)
    script.main()
    return commands


def test_backup_omits_env_files_and_planted_database_password(tmp_path, monkeypatch):
    workspace, data = fixture_workspace(tmp_path)
    destination = tmp_path / "backups"
    commands = run_backup(monkeypatch, workspace, data, destination)

    archives = list(destination.iterdir())
    media = next(path for path in archives if path.name.endswith(".media.tar.gz"))
    dump = next(path for path in archives if path.suffix == ".dump")
    assert media.stat().st_mode & 0o777 == 0o600
    assert dump.stat().st_mode & 0o777 == 0o600
    assert not list(destination.glob("*.partial"))
    payload = gzip.decompress(media.read_bytes())
    assert PLANTED.encode() not in payload
    assert b"workspace-root-marker" not in payload
    assert PLANTED.encode() not in dump.read_bytes()
    assert all(PLANTED.encode() not in " ".join(command).encode() for command in commands)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        names = archive.getnames()
        files = {member.name: archive.extractfile(member).read() for member in archive.getmembers() if member.isfile()}
    assert not any(env_part(part) for name in names for part in PurePosixPath(name).parts)
    assert b"image-bytes" in files.values()
    assert b"sqlite-ok" in files.values()
    assert b"keep-environment\n" in files.values()


def test_database_only_backup_omits_planted_database_password(tmp_path, monkeypatch):
    workspace, data = fixture_workspace(tmp_path)
    destination = tmp_path / "backups"
    commands = run_backup(monkeypatch, workspace, data, destination, database_only=True)

    archives = list(destination.iterdir())
    assert len(archives) == 1
    dump = archives[0]
    assert dump.suffix == ".dump"
    assert dump.read_bytes() == b"PGDMP"
    assert PLANTED.encode() not in dump.read_bytes()
    assert all("tar" not in argument for command in commands for argument in command)
    assert all(PLANTED.encode() not in " ".join(command).encode() for command in commands)


def test_media_restore_skips_env_members_and_keeps_confirmation(tmp_path, monkeypatch):
    script = load_script("restore_media")
    backup = tmp_path / "media.tar.gz"
    secret = f"POSTGRES_PASSWORD={PLANTED}\n".encode()
    with tarfile.open(backup, "w:gz") as archive:
        for name, payload in (
            ("image.webp", b"image"),
            (".env", secret),
            (".env.local", secret),
            ("nested/.env.production", secret),
            (".env/secret", secret),
            ("note.txt", b"note"),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))

    calls = []
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: calls.append(command))
    monkeypatch.setattr(sys, "argv", ["restore_media", str(backup)])
    with pytest.raises(SystemExit):
        script.main()
    assert calls == []

    monkeypatch.setattr(sys, "argv", ["restore_media", str(backup), "--confirm-empty-volume"])
    script.main()
    command = calls[0]
    assert command[:5] == ["docker", "compose", "run", "--rm", "--no-deps"]
    program = ast.parse(command[-1])
    root = tmp_path / "assets"
    root.mkdir()
    program.body[1].value.args[0] = ast.Constant(str(root))
    ast.fix_missing_locations(program)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(backup.read_bytes())))
    exec(compile(program, "media-restore", "exec"), {})

    assert (root / "image.webp").read_bytes() == b"image"
    assert (root / "note.txt").read_bytes() == b"note"
    restored = [path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()]
    assert not any(env_part(part) for name in restored for part in PurePosixPath(name).parts)
    assert all(PLANTED.encode() not in path.read_bytes() for path in root.rglob("*") if path.is_file())
