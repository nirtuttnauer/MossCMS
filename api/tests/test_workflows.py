from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def test_docker_publication_depends_on_the_complete_same_commit_check_suite():
    checks = yaml.load((WORKFLOWS / "checks.yml").read_text(), Loader=yaml.BaseLoader)
    docker = yaml.load((WORKFLOWS / "docker.yml").read_text(), Loader=yaml.BaseLoader)

    assert "workflow_call" in checks["on"]
    assert "production_docker" in checks["jobs"]
    assert docker["jobs"]["checks"] == {"uses": "./.github/workflows/checks.yml"}
    image = docker["jobs"]["image"]
    assert image["needs"] == "checks"
    assert image["if"] == "github.event_name != 'pull_request'"
    assert image.get("continue-on-error", "false") == "false"
    assert all(job.get("continue-on-error", "false") == "false" for job in checks["jobs"].values())
    assert all("if" not in job for job in checks["jobs"].values())

    registry_steps = [step for step in image["steps"] if step.get("uses", "").startswith("docker/")]
    assert registry_steps
    assert all(step["if"] == "steps.registry.outputs.configured == 'true'" for step in registry_steps)
    publishing = next(step for step in registry_steps if step["uses"].startswith("docker/build-push-action@"))
    assert publishing["with"]["push"] == "true"
