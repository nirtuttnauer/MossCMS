import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.compose


@pytest.fixture
def compose(tmp_path):
    if not shutil.which("docker"):
        pytest.fail("Docker is required to validate deployment configuration.")
    version = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True)
    if version.returncode:
        pytest.fail(f"Docker Compose is unavailable.\n{version.stderr}")

    project = tmp_path / "project"
    project.mkdir()
    for name in ["compose.yaml", "compose.database.false.yaml", "compose.database.true.yaml"]:
        shutil.copyfile(ROOT / name, project / name)
    website = project / "example-site"
    website.mkdir()
    (website / ".env").write_text(
        "MOSS_API_URL=http://app:8001\nMOSS_PROJECT_ID=fixture\nMOSS_DELIVERY_TOKEN=fixture-token\n"
    )

    def config(flag, website=False, postgres=True, extra=None):
        values = {"MOSS_SECRET_KEY": "s" * 40, "MOSS_SETUP_TOKEN": "t" * 30}
        if flag is not None:
            values["MOSS_USE_SQLITE"] = flag
        if postgres:
            values.update(POSTGRES_DB="fixture", POSTGRES_USER="fixture", POSTGRES_PASSWORD="fixture-password")
        if extra:
            values.update(extra)
        file = tmp_path / "fixture.env"
        file.write_text("\n".join(f"{key}={value}" for key, value in values.items()))
        environment = {
            key: value for key, value in os.environ.items() if not key.startswith(("MOSS_", "POSTGRES_", "COMPOSE_"))
        }
        command = ["docker", "compose", "--env-file", str(file), "-f", str(project / "compose.yaml")]
        if website:
            command += ["--profile", "website"]
        return subprocess.run(
            [*command, "config", "--no-env-resolution", "--format", "json"],
            cwd=project,
            env=environment,
            capture_output=True,
            text=True,
        )

    return config


@pytest.mark.parametrize("website", [False, True])
def test_sqlite_compose_replaces_postgres_without_credentials(compose, website):
    result = compose("true", website=website, postgres=False)
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    assert set(services) == ({"app", "db", "example-site"} if website else {"app", "db"})
    assert services["app"]["depends_on"]["db"]["condition"] == "service_completed_successfully"
    assert services["db"]["image"] == services["app"]["image"]
    assert services["db"]["entrypoint"] == ["/bin/true"]
    assert services["db"]["restart"] == "no"
    assert not services["db"].get("volumes")
    assert not services["db"].get("healthcheck")
    assert not any(key.startswith("POSTGRES_") for key in services["app"]["environment"])
    assert services["app"]["environment"]["MOSS_USE_SQLITE"] == "true"
    assert services["app"]["volumes"][0]["target"] == "/data"
    if website:
        assert services["example-site"]["depends_on"]["app"]["condition"] == "service_healthy"


@pytest.mark.parametrize("flag", ["false", None])
def test_postgres_compose_preserves_default_dependency(compose, flag):
    result = compose(flag)
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    assert set(services) == {"app", "db"}
    assert services["app"]["depends_on"]["db"]["condition"] == "service_healthy"
    assert services["app"]["environment"]["POSTGRES_HOST"] == "db"
    assert services["db"]["environment"]["POSTGRES_PASSWORD"] == "fixture-password"


def test_postgres_compose_still_requires_credentials(compose):
    result = compose("false", postgres=False)
    assert result.returncode != 0
    assert "POSTGRES_" in result.stderr


def test_default_app_image_builds_locally(compose):
    result = compose(None)
    assert result.returncode == 0, result.stderr
    app = json.loads(result.stdout)["services"]["app"]
    assert app["image"] == "mosscms:local"
    assert app["pull_policy"] == "build"
    assert app["build"]["context"]
    assert "nirtuttnauer/mosscms" not in app["image"]


def test_sqlite_stub_reuses_local_image_without_pulling(compose):
    result = compose("true", postgres=False)
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    assert services["app"]["image"] == "mosscms:local"
    assert services["app"]["pull_policy"] == "build"
    assert services["db"]["image"] == "mosscms:local"
    assert services["db"]["pull_policy"] == "never"


def test_published_image_is_opt_in(compose):
    result = compose(
        "false",
        extra={"MOSS_IMAGE": "nirtuttnauer/mosscms:1.2.3", "MOSS_PULL_POLICY": "missing"},
    )
    assert result.returncode == 0, result.stderr
    app = json.loads(result.stdout)["services"]["app"]
    assert app["image"] == "nirtuttnauer/mosscms:1.2.3"
    assert app["pull_policy"] == "missing"
    assert app["build"]["context"]
