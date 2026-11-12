"""Lock the image runtime user and the default Compose Postgres port.

``docker compose up`` and ``scripts/start.py`` read ``compose.yaml``. With
``MOSS_USE_SQLITE`` unset, that file extends ``compose.database.false.yaml``
(PostgreSQL). ``compose.benchmark.yaml`` and ``compose.observability.yaml``
are separate files and are not that start path.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_FROM = (
    "FROM python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d AS runtime"
)
_PORT_NUMBER = re.compile(r"\d+")


def dockerfile_instructions(text):
    instructions = []
    pending = ""
    for raw in text.splitlines():
        line = raw.strip()
        if pending:
            line = f"{pending} {line}".strip()
            pending = ""
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            pending = line[:-1].strip()
            continue
        code = line.split("#", 1)[0].strip()
        if not code:
            continue
        name, _, argument = code.partition(" ")
        instructions.append((name.upper(), argument.strip()))
    return instructions


def final_stage_instructions(text):
    current = None
    for name, argument in dockerfile_instructions(text):
        if name == "FROM":
            current = []
        elif current is not None:
            current.append((name, argument))
    return current


def final_stage_user(text):
    stage = final_stage_instructions(text)
    if stage is None:
        return None
    user = None
    for name, argument in stage:
        if name == "USER":
            user = argument
    return user


def user_account(user):
    token = user.strip().strip("\"'")
    if not token:
        return ""
    token = token.split()[0].strip("\"'")
    return token.split(":", 1)[0].strip("\"'")


def is_root_account(account):
    if account.lower() == "root":
        return True
    try:
        return int(account) == 0
    except ValueError:
        return False


def uid_assigned_in_stage(stage, account):
    for name, argument in stage:
        if name != "RUN":
            continue
        for segment in argument.split("&&"):
            parts = segment.split()
            if not parts or parts[0] not in {"useradd", "adduser"} or account not in parts:
                continue
            for part in parts:
                if part.startswith("--uid="):
                    return part.split("=", 1)[1]
            for flag in ("--uid", "-u"):
                if flag in parts:
                    index = parts.index(flag)
                    if index + 1 < len(parts):
                        return parts[index + 1]
    return None


def require_non_root_runtime_user(text):
    stage = final_stage_instructions(text)
    user = final_stage_user(text)
    assert user, "runtime stage has no USER instruction"
    account = user_account(user)
    assert account, "runtime stage has no USER instruction"
    assert not is_root_account(account), user
    if stage is not None and not account.isdigit():
        uid = uid_assigned_in_stage(stage, account)
        if uid is not None:
            assert not is_root_account(uid), user
    return account


def iter_published_ports(services):
    for name, service in services.items():
        for port in service.get("ports") or []:
            if isinstance(port, dict):
                published = port.get("published", "")
                target = port.get("target", "")
            else:
                published, target = _split_port_spec(str(port))
            yield name, str(published), str(target)


def _split_port_spec(spec):
    parts = spec.split("/", 1)[0].rsplit(":", 2)
    if len(parts) == 1:
        return parts[0], parts[0]
    return parts[-2], parts[-1]


def port_numbers(value):
    return set(_PORT_NUMBER.findall(value))


def require_postgres_unpublished(services):
    image = services["db"]["image"]
    assert str(image).startswith("postgres:"), image
    hits = [
        f"{name} {published}:{target}"
        for name, published, target in iter_published_ports(services)
        if "5432" in port_numbers(published) or "5432" in port_numbers(target)
    ]
    assert not hits, hits


def _checked_in_dockerfile():
    return (ROOT / "Dockerfile").read_text()


def test_checked_in_dockerfile_runtime_user_is_not_root():
    account = require_non_root_runtime_user(_checked_in_dockerfile())
    assert not is_root_account(account)


@pytest.mark.parametrize("user", ["root", "0", "0:0", "root:root"])
def test_root_runtime_user_is_rejected(user):
    text = _checked_in_dockerfile()
    assert "USER appuser\n" in text
    rooted = text.replace("USER appuser\n", f"USER {user}\n", 1)
    with pytest.raises(AssertionError):
        require_non_root_runtime_user(rooted)


def test_missing_runtime_user_is_rejected():
    text = _checked_in_dockerfile()
    assert "USER appuser\n" in text
    missing = text.replace("USER appuser\n", "", 1)
    assert "\nUSER " not in f"\n{missing}"
    with pytest.raises(AssertionError):
        require_non_root_runtime_user(missing)


def test_user_set_before_the_runtime_stage_is_rejected():
    text = _checked_in_dockerfile()
    assert text.count(RUNTIME_FROM) == 1
    assert "USER appuser\n" in text
    shifted = text.replace("USER appuser\n", "", 1).replace(RUNTIME_FROM, f"USER appuser\n{RUNTIME_FROM}", 1)
    with pytest.raises(AssertionError):
        require_non_root_runtime_user(shifted)


def test_root_uid_for_the_runtime_account_is_rejected():
    text = _checked_in_dockerfile()
    assert "--uid 10001" in text
    rooted = text.replace("--uid 10001", "--uid 0", 1)
    with pytest.raises(AssertionError):
        require_non_root_runtime_user(rooted)


@pytest.fixture
def compose_project(tmp_path):
    if not shutil.which("docker"):
        pytest.fail("Docker is required to validate deployment configuration.")
    version = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True)
    if version.returncode:
        pytest.fail(f"Docker Compose is unavailable.\n{version.stderr}")
    project = tmp_path / "project"
    project.mkdir()
    for name in ("compose.yaml", "compose.database.false.yaml", "compose.database.true.yaml"):
        shutil.copyfile(ROOT / name, project / name)
    return project


def render_compose(project):
    # Unset MOSS_USE_SQLITE selects the PostgreSQL file. Parent env must not override that.
    values = {
        "MOSS_SECRET_KEY": "s" * 40,
        "MOSS_SETUP_TOKEN": "t" * 30,
        "POSTGRES_DB": "fixture",
        "POSTGRES_USER": "fixture",
        "POSTGRES_PASSWORD": "fixture-password",
    }
    env_file = project / "fixture.env"
    env_file.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith(("MOSS_", "POSTGRES_", "COMPOSE_"))
    }
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(project / "compose.yaml"),
            "config",
            "--no-env-resolution",
            "--format",
            "json",
        ],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["services"]


@pytest.mark.compose
def test_default_compose_does_not_publish_postgres(compose_project):
    require_postgres_unpublished(render_compose(compose_project))


@pytest.mark.compose
@pytest.mark.parametrize("mapping", ["5432:5432", "127.0.0.1:5432:5432", "127.0.0.1:15432:5432"])
def test_db_port_publish_is_rejected(compose_project, mapping):
    db_file = compose_project / "compose.database.false.yaml"
    text = db_file.read_text()
    needle = "image: postgres:17-alpine\n"
    assert needle in text
    db_file.write_text(text.replace(needle, f'{needle}    ports:\n      - "{mapping}"\n', 1))
    with pytest.raises(AssertionError):
        require_postgres_unpublished(render_compose(compose_project))


@pytest.mark.compose
def test_default_file_port_publish_is_rejected(compose_project):
    compose_file = compose_project / "compose.yaml"
    text = compose_file.read_text()
    needle = "      service: db\nvolumes:\n"
    assert needle in text
    compose_file.write_text(text.replace(needle, '      service: db\n    ports:\n      - "5432:5432"\nvolumes:\n', 1))
    with pytest.raises(AssertionError):
        require_postgres_unpublished(render_compose(compose_project))
