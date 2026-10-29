"""Check that the saved SQLite and PostgreSQL runs passed every collected test id."""

import json
import sys

import required_runs


def main():
    problems = required_runs.verify_saved_runs()
    if problems:
        sys.stderr.write("\n".join(problems) + "\n")
        return 1
    counts = {}
    for name in required_runs.REQUIRED_RUNS:
        payload = json.loads(required_runs.result_path(name).read_text())
        counts[name] = {
            "collected": len(payload["collected"]),
            "passed": len(payload["passed"]),
            "deselected": len(payload["deselected"]),
            "failed": len(payload["failed"]),
            "skipped": len(payload["skipped"]),
        }
    print(json.dumps({"ok": True, "runs": counts}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
