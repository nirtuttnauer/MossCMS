"""Read verify.sh logs: reject runtime skips and record test counts."""

import json
import re
import sys
from pathlib import Path


def skip_problems(text):
    """Return human-readable problems for any runtime skip or xfail in a log."""
    problems = []
    for line in text.splitlines():
        stripped = line.strip()
        if _pytest_summary(stripped):
            for kind in ("skipped", "xfailed", "xpassed"):
                match = re.search(rf"\b(\d+) {kind}\b", stripped)
                if match and int(match.group(1)) > 0:
                    problems.append(stripped)
                    break
        vitest = re.match(r"Tests\s+(.+)$", stripped)
        if vitest:
            for kind in ("skipped", "todo"):
                match = re.search(rf"\b(\d+) {kind}\b", vitest.group(1))
                if match and int(match.group(1)) > 0:
                    problems.append(stripped)
                    break
        if re.match(r"\d+ skipped$", stripped):
            problems.append(stripped)
    for kind in ("skipped", "todo"):
        match = re.search(rf"^# {kind} (\d+)\s*$", text, re.M)
        if match and int(match.group(1)) > 0:
            problems.append(f"node:test {kind} {match.group(1)}")
    return problems


def _pytest_summary(stripped):
    if re.search(r"\bin \d", stripped) is None:
        return False
    return re.search(r"\b(passed|failed|skipped|xfailed|xpassed|deselected)\b", stripped) is not None


def _pytest_counts(text):
    for line in text.splitlines():
        stripped = line.strip()
        if not _pytest_summary(stripped):
            continue

        def grab(kind, line=stripped):
            match = re.search(rf"\b(\d+) {kind}\b", line)
            return int(match.group(1)) if match else 0

        passed = grab("passed")
        failed = grab("failed")
        skipped = grab("skipped")
        deselected = grab("deselected")
        xfailed = grab("xfailed")
        xpassed = grab("xpassed")
        return {
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "deselected": deselected,
            "xfailed": xfailed,
            "xpassed": xpassed,
            "collected": passed + failed + skipped + deselected + xfailed + xpassed,
        }
    return None


def _json_objects(text):
    decoder = json.JSONDecoder()
    index = 0
    while True:
        start = text.find("{", index)
        if start < 0:
            return
        try:
            value, offset = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(value, dict):
            yield value
        index = start + offset


def _required_run_counts(text):
    for value in _json_objects(text):
        runs = value.get("runs")
        if isinstance(runs, dict) and "sqlite" in runs and "postgres" in runs:
            return runs
    return None


def _vitest_counts(text):
    files = re.search(r"^\s*Test Files\s+(\d+) passed", text, re.M)
    tests = re.search(r"^\s*Tests\s+(\d+) passed(?:\s+\|\s+(\d+) skipped)?", text, re.M)
    if not tests:
        return None
    skipped = int(tests.group(2) or 0)
    counts = {"passed": int(tests.group(1)), "skipped": skipped}
    if files:
        counts["files_passed"] = int(files.group(1))
    return counts


def _node_counts(text):
    passed = re.search(r"^# pass (\d+)\s*$", text, re.M)
    if not passed:
        return None

    def grab(kind):
        match = re.search(rf"^# {kind} (\d+)\s*$", text, re.M)
        return int(match.group(1)) if match else 0

    return {"passed": int(passed.group(1)), "failed": grab("fail"), "skipped": grab("skipped"), "todo": grab("todo")}


def _playwright_counts(text):
    match = re.search(r"^\s+(\d+) passed(?: \(|$)", text, re.M)
    if not match:
        return None
    skipped = re.search(r"^\s+(\d+) skipped\s*$", text, re.M)
    return {"passed": int(match.group(1)), "skipped": int(skipped.group(1)) if skipped else 0}


def collect_counts(evidence):
    evidence = Path(evidence)
    counts = {}
    required = _required_run_counts(
        (evidence / "verify-required-runs.txt").read_text(encoding="utf-8", errors="replace")
    )
    if required:
        for name in ("sqlite", "postgres"):
            counts[name] = required[name]
    else:
        for name, filename in (("sqlite", "pytest-sqlite.txt"), ("postgres", "pytest-postgres.txt")):
            parsed = _pytest_counts((evidence / filename).read_text(encoding="utf-8", errors="replace"))
            if parsed:
                counts[name] = parsed
    web = _vitest_counts((evidence / "web.txt").read_text(encoding="utf-8", errors="replace"))
    if web:
        counts["web"] = web
    example = _node_counts((evidence / "example-site.txt").read_text(encoding="utf-8", errors="replace"))
    if example:
        counts["example_site"] = example
    production = evidence / "production-test.txt"
    if production.is_file():
        playwright = _playwright_counts(production.read_text(encoding="utf-8", errors="replace"))
        if playwright:
            counts["production"] = playwright
    return counts


def write_counts(evidence):
    evidence = Path(evidence)
    counts = collect_counts(evidence)
    (evidence / "counts.json").write_text(json.dumps(counts, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(counts, indent=2))
    return counts


def main(argv):
    if len(argv) == 3 and argv[1] == "scan":
        problems = skip_problems(Path(argv[2]).read_text(encoding="utf-8", errors="replace"))
        if problems:
            print("runtime skip or xfail is a failure:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        return 0
    if len(argv) == 3 and argv[1] == "counts":
        write_counts(argv[2])
        return 0
    print("usage: verify_report.py scan LOG | verify_report.py counts EVIDENCE", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
