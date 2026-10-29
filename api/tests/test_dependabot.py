import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_dependabot.py"


def load():
    spec = importlib.util.spec_from_file_location("check_dependabot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load()


def test_dependabot_config_matches_schema_and_covers_manifests():
    assert MODULE.check() == []


def test_ticket_command_and_nested_dockerfile_are_discovered():
    paths = MODULE.manifest_paths()
    ticket = set(MODULE.git_ls_files(MODULE.TICKET_PATHSPECS))
    assert ticket
    assert ticket <= set(paths)
    assert "example-site/Dockerfile" in paths
    assert "Dockerfile" in paths
    assert "api/pyproject.toml" in paths
    assert "web/package.json" in paths
    assert "example-site/package.json" in paths
    assert "ci/package.json" in paths
    assert ".github/workflows/checks.yml" in paths
    assert ".github/workflows/docker.yml" in paths


def test_parser_reads_weekly_limit_and_ignores_comments():
    document = MODULE.parse_yaml(
        """
        # comment
        version: 2
        updates:
          - package-ecosystem: "uv" # api
            directory: '/api'
            schedule:
              interval: weekly
            open-pull-requests-limit: 5
        """
    )
    assert document["version"] == 2
    entry = document["updates"][0]
    assert entry["package-ecosystem"] == "uv"
    assert entry["directory"] == "/api"
    assert entry["schedule"]["interval"] == "weekly"
    assert entry["open-pull-requests-limit"] == 5


def _document():
    return MODULE.parse_yaml((ROOT / ".github" / "dependabot.yml").read_text())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda document: document.__setitem__("version", 1),
        lambda document: document.__setitem__("version", "2"),
        lambda document: document.__setitem__("extra", True),
        lambda document: document["updates"][0].__setitem__("package-ecosystem", "not-an-ecosystem"),
        lambda document: document["updates"][0].pop("schedule"),
        lambda document: document["updates"][0].pop("directory"),
        lambda document: document["updates"][0].__setitem__("directories", ["/api"]),
        lambda document: document["updates"][0]["schedule"].__setitem__("interval", "hourly"),
        lambda document: document["updates"][0].__setitem__("open-pull-requests-limit", -1),
    ],
)
def test_schema_rejects_invalid_dependabot_documents(mutate):
    document = copy.deepcopy(_document())
    mutate(document)
    assert MODULE.schema_errors(document, MODULE.load_schema())


def test_schema_accepts_the_checked_in_config():
    assert MODULE.schema_errors(_document(), MODULE.load_schema()) == []


def test_coverage_reports_a_missing_manifest_directory():
    updates = [
        {
            "package-ecosystem": "npm",
            "directory": "/web",
            "schedule": {"interval": "weekly"},
            "open-pull-requests-limit": 5,
        }
    ]
    problems = MODULE.coverage_problems(["web/package.json", "ci/package.json"], updates)
    assert problems == ["ci/package.json (npm /ci) is not covered by .github/dependabot.yml"]


def test_directories_list_and_root_actions_count_as_coverage():
    updates = [
        {
            "package-ecosystem": "npm",
            "directories": ["/web", "/ci"],
            "schedule": {"interval": "weekly"},
            "open-pull-requests-limit": 5,
        },
        {
            "package-ecosystem": "github-actions",
            "directory": "/",
            "schedule": {"interval": "weekly"},
            "open-pull-requests-limit": 5,
        },
    ]
    paths = ["web/package.json", "ci/package.json", ".github/workflows/checks.yml"]
    assert MODULE.coverage_problems(paths, updates) == []


def test_workflow_directory_is_the_repository_root():
    updates = [
        {
            "package-ecosystem": "github-actions",
            "directory": "/.github/workflows",
            "schedule": {"interval": "weekly"},
            "open-pull-requests-limit": 5,
        }
    ]
    problems = MODULE.coverage_problems([".github/workflows/checks.yml"], updates)
    assert problems


def test_open_pull_request_limit_must_stay_small_and_weekly():
    daily = [
        {
            "package-ecosystem": "npm",
            "directory": "/web",
            "schedule": {"interval": "daily"},
            "open-pull-requests-limit": 5,
        }
    ]
    unlimited = [
        {
            "package-ecosystem": "npm",
            "directory": "/web",
            "schedule": {"interval": "weekly"},
            "open-pull-requests-limit": 10,
        }
    ]
    assert MODULE.policy_problems(daily)
    assert MODULE.policy_problems(unlimited)
    assert (
        MODULE.policy_problems(
            [
                {
                    "package-ecosystem": "npm",
                    "directory": "/web",
                    "schedule": {"interval": "weekly"},
                    "open-pull-requests-limit": 5,
                }
            ]
        )
        == []
    )
