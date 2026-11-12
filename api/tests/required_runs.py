"""Required-run selection for the API suite.

A skip or xfail reported at runtime fails the run. There is no allowed-skip list.
The SQLite required run excludes PostgreSQL-only tests before they execute with
``-m "not postgres"``. The PostgreSQL required run uses no marker filter and
includes the Docker Compose tests. Both runs record the test ids they deselect,
and that list is committed in ``required_runs.json``. Every collected test id
has to pass in at least one of those runs.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from _pytest.mark import MarkMatcher
from _pytest.mark.expression import Expression

MANIFEST_PATH = Path(__file__).with_name("required_runs.json")
RESULTS_DIR = Path(__file__).resolve().parents[1] / ".required-run-results"
REQUIRED_RUNS = ("sqlite", "postgres")
COLLECTED = pytest.StashKey[list]()


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text())


class _Marker:
    def __init__(self, name):
        self.name = name
        self.kwargs = {}


class _Collected:
    def __init__(self, nodeid, markers):
        self.nodeid = nodeid
        self._markers = [_Marker(name) for name in markers]

    def iter_markers(self):
        return self._markers


def collect_full_suite():
    """Collect every API test id and marker, independent of the current pytest selection."""
    api_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "collected.json"
        script = """
import json, os
from pathlib import Path
import pytest

class Plugin:
    def pytest_collection_modifyitems(self, config, items):
        rows = [
            {"id": item.nodeid, "markers": sorted({mark.name for mark in item.iter_markers()})}
            for item in items
        ]
        Path(os.environ["MOSS_COLLECT_PATH"]).write_text(json.dumps(rows))

raise SystemExit(pytest.main(["--collect-only", "-q", "-p", "no:cacheprovider"], plugins=[Plugin()]))
"""
        env = os.environ.copy()
        env["MOSS_COLLECT_PATH"] = str(target)
        env.pop("MOSS_REQUIRED_RUN", None)
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=api_root,
            env=env,
            capture_output=True,
            text=True,
        )
        if not target.is_file():
            raise RuntimeError(completed.stdout + completed.stderr)
        if completed.returncode not in (0, 5):
            raise RuntimeError(completed.stdout + completed.stderr)
        rows = json.loads(target.read_text())
        return [_Collected(row["id"], row["markers"]) for row in rows]


def deselected_by_marker(items, expression):
    if not expression:
        return []
    compiled = Expression.compile(expression)
    deselected = [item.nodeid for item in items if not compiled.evaluate(MarkMatcher.from_markers(item.iter_markers()))]
    return sorted(deselected)


def check_manifest(items):
    manifest = load_manifest()
    problems = []
    runs = manifest.get("runs")
    if not isinstance(runs, dict) or set(runs) != set(REQUIRED_RUNS):
        return [f"required_runs.json must define the runs {', '.join(REQUIRED_RUNS)}"]
    all_ids = [item.nodeid for item in items]
    if len(all_ids) != len(set(all_ids)):
        problems.append("collected test ids are not unique")
    covered = set()
    for name in REQUIRED_RUNS:
        spec = runs[name]
        expression = spec.get("marker", "")
        expected = spec.get("deselected")
        if not isinstance(expression, str):
            problems.append(f"{name} marker must be a string")
            expression = ""
        if not isinstance(expected, list) or expected != sorted(expected):
            problems.append(f"{name} deselected ids must be a sorted list")
            expected = expected if isinstance(expected, list) else []
        actual = deselected_by_marker(items, expression)
        if actual != expected:
            problems.append(
                f"{name} deselected ids do not match marker {expression!r}\n"
                f"  missing from manifest: {sorted(set(actual) - set(expected))}\n"
                f"  extra in manifest: {sorted(set(expected) - set(actual))}"
            )
        covered.update(set(all_ids) - set(actual))
    missing = sorted(set(all_ids) - covered)
    if missing:
        problems.append("collected test ids selected by no required run:\n  " + "\n  ".join(missing))
    return problems


def result_path(run):
    return RESULTS_DIR / f"{run}.json"


def write_result(run, payload):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path(run).write_text(json.dumps(payload, indent=2) + "\n")


def _ids(payload, key):
    value = payload.get(key)
    if not isinstance(value, list):
        return None
    return value


def verify_saved_runs():
    manifest = load_manifest()
    problems = []
    payloads = {}
    for name in REQUIRED_RUNS:
        path = result_path(name)
        if not path.is_file():
            problems.append(f"missing required-run result {path}")
            continue
        payloads[name] = json.loads(path.read_text())
    if len(payloads) != len(REQUIRED_RUNS):
        return problems
    collected = {name: _ids(payload, "collected") for name, payload in payloads.items()}
    if any(ids is None for ids in collected.values()):
        problems.append("required-run results must list collected test ids")
        return problems
    if collected["sqlite"] != collected["postgres"]:
        problems.append("sqlite and postgres runs collected different test ids; rerun both on the same tree")
        return problems
    collected_ids = collected["sqlite"]
    passed_union = set()
    for name, payload in payloads.items():
        deselected = _ids(payload, "deselected")
        passed = _ids(payload, "passed")
        failed = _ids(payload, "failed")
        skipped = _ids(payload, "skipped")
        if None in (deselected, passed, failed, skipped):
            problems.append(f"{name} result is missing deselected, passed, failed, or skipped ids")
            continue
        expected = manifest["runs"][name]["deselected"]
        if deselected != expected:
            problems.append(
                f"{name} run deselected ids do not match the committed list\n"
                f"  missing from run: {sorted(set(expected) - set(deselected))}\n"
                f"  extra in run: {sorted(set(deselected) - set(expected))}"
            )
        if skipped:
            problems.append(f"{name} run skipped at runtime:\n  " + "\n  ".join(skipped))
        if failed:
            problems.append(f"{name} run failed:\n  " + "\n  ".join(failed))
        expected_passed = sorted(set(collected_ids) - set(expected))
        if sorted(passed) != expected_passed:
            problems.append(
                f"{name} passed ids do not match the tests that run executes\n"
                f"  missing: {sorted(set(expected_passed) - set(passed))}\n"
                f"  unexpected: {sorted(set(passed) - set(expected_passed))}"
            )
        passed_union.update(passed)
    missing = sorted(set(collected_ids) - passed_union)
    if missing:
        problems.append("collected test ids that did not pass in any required run:\n  " + "\n  ".join(missing))
    return problems


def reject_runtime_skip(report):
    """Turn a runtime skip or xfail into a failure. There is no allowed-skip list."""
    if hasattr(report, "wasxfail"):
        detail = report.wasxfail
        del report.wasxfail
    else:
        longrepr = report.longrepr
        detail = longrepr[2] if isinstance(longrepr, tuple) and len(longrepr) >= 3 else longrepr
    report.outcome = "failed"
    report.longrepr = f"runtime skip is a failure; there is no allowed-skip list: {detail}"
