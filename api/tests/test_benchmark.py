import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://localhost/production",
        "postgresql://example.com/moss_benchmark_test",
        "sqlite:///moss_benchmark_test",
        "postgresql://localhost",
        "postgresql://[::1]/moss_benchmark_test",
    ],
)
def test_fixture_guard_rejects_other_databases(url):
    with pytest.raises(ValueError, match="disposable"):
        load("benchmark").guarded_url(url)


def test_fixture_mix_is_deterministic_and_references_live_content():
    script = load("benchmark")
    records = [script.fixture_entry(i) for i in range(100)]
    assert records == [script.fixture_entry(i) for i in range(100)]
    assert [sum(row["project_id"] == f"benchmark-workspace-{group}" for row in records) for group in range(3)] == [
        80,
        10,
        10,
    ]
    assert sum(row["published_data"] is not None for row in records) == 60
    assert sum(row["scheduled_data"] is not None for row in records) == 40
    by_id = {row["id"]: row for row in records}
    for row in records:
        target = by_id[row["data"]["related"]]
        assert target["published_data"] and target["project_id"] == row["project_id"]
    assert records[4]["data"]["title"] != records[4]["published_data"]["title"]
    assert records[4]["scheduled_data"]["title"] != records[4]["published_data"]["title"]


def test_fingerprint_covers_locales_content_and_media(tmp_path):
    script = load("benchmark")
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE projects (id TEXT PRIMARY KEY, locales TEXT, default_locale TEXT)"))
        connection.execute(text("INSERT INTO projects VALUES ('fixture', '[\"en\"]', 'en')"))
    (tmp_path / "image.png").write_bytes(b"original")
    before = script.fingerprint(engine, tmp_path)
    with engine.begin() as connection:
        connection.execute(text("UPDATE projects SET locales = '[\"he\"]'"))
    assert script.fingerprint(engine, tmp_path) != before
    (tmp_path / "image.png").write_bytes(b"changed")
    assert script.fingerprint(engine, tmp_path)["media"] != before["media"]
    engine.dispose()


def test_percentiles_errors_and_resource_units():
    script = load("benchmark")
    assert script.summarize([1, 2, 3, 4, 100], 10) == {
        "requests": 5,
        "requestsPerSecond": 0.5,
        "p50Ms": 3,
        "p95Ms": 100,
        "p99Ms": 100,
    }
    assert script.summarize([], 10)["p95Ms"] is None
    runner = load("run_benchmark")
    assert runner.memory_bytes("1.5GiB") == 1610612736
    assert runner.memory_bytes("128 MiB") == 134217728
    result = runner.resource_summary(
        [
            {
                "containers": [
                    {"Name": "moss-benchmark-abc-app-1", "MemUsage": "128MiB / 4GiB", "CPUPerc": "45.2%"},
                ]
            }
        ]
    )
    assert result["app"]["peakMemoryBytes"] == 134217728
    assert result["app"]["peakCpuPercent"] == 45.2


def test_cost_example_and_overages():
    import json

    calculator = load("benchmark_cost")
    values = json.loads((SCRIPTS.parent / "docs/benchmarks/cost-inputs-2026-10-12.json").read_text())["inputs"]
    result = calculator.calculate(values)
    assert result["infrastructure"] == "62.60"
    assert result["total"] == "162.60"
    values.update({"object_storage_gib": "300", "compute_transfer_gib": "5100", "object_transfer_gib": "1124"})
    result = calculator.calculate(values)
    assert result["objectStorageAndBackups"] == "6.00"
    assert result["computeTransferOverage"] == "1.00"
    assert result["objectTransferOverage"] == "1.00"
    assert result["total"] == "165.60"
    for bad in ("NaN", "Infinity", "-1", "invalid"):
        values["operator_hours_monthly"] = bad
        with pytest.raises(ValueError):
            calculator.calculate(values)


def test_cleanup_removes_only_owned_fixture_volumes(monkeypatch):
    runner = load("run_benchmark")
    commands = []

    def output(command, **kwargs):
        commands.append(command)
        if "ls" in command:
            return "moss-benchmark-test_media\n"
        return '[{"Labels": {"com.docker.compose.project": "moss-benchmark-test"}}]'

    monkeypatch.setattr(runner.subprocess, "check_output", output)
    monkeypatch.setattr(runner.subprocess, "run", lambda command, **kwargs: commands.append(command))
    runner.remove_fixture_volumes("moss-benchmark-test")
    assert commands[0][4] == "label=com.docker.compose.project=moss-benchmark-test"
    assert commands[-1] == ["docker", "volume", "rm", "moss-benchmark-test_media"]


def test_cleanup_refuses_normal_projects_and_foreign_volumes(monkeypatch):
    runner = load("run_benchmark")
    with pytest.raises(ValueError, match="non-benchmark"):
        runner.remove_fixture_volumes("moss-production")

    def output(command, **kwargs):
        if "ls" in command:
            return "foreign_media\n"
        return '[{"Labels": {"com.docker.compose.project": "production"}}]'

    monkeypatch.setattr(runner.subprocess, "check_output", output)
    monkeypatch.setattr(
        runner.subprocess, "run", lambda *args, **kwargs: pytest.fail("Must not remove foreign volumes")
    )
    with pytest.raises(ValueError, match="another project"):
        runner.remove_fixture_volumes("moss-benchmark-test")
