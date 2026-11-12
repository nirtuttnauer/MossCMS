# MOSS-063 Dependabot coverage for the Next.js starter

local

Recorded 11 November 2026 (UTC). `scripts/verify.sh MOSS-063` ran on a clean tree at `79dc63b932eab7e805835f1cbf872a344beb0db1`. The script refuses a dirty tree, writes this folder, and exits non-zero on a failed step or a runtime skip or xfail. There is no allowed-skip list and no audit ignore. GitHub Actions was not used.

## Code under test

| | |
| --- | --- |
| Base | `b6c66870b98af990ee91766e5a965e823bf2b03d` (`main`) |
| SHA tested | `79dc63b932eab7e805835f1cbf872a344beb0db1` |
| Branch | `cursor/moss-063-dependabot-nextjs-790b` |
| `git status --porcelain` at the start of `scripts/verify.sh` | empty |
| Date | 2026-11-11T21:51:13Z through 2026-11-11T22:00:06Z |
| Command | `scripts/verify.sh MOSS-063` |
| Exit | 0 |
| Logs | [79dc63b](79dc63b/) |

The evidence files in this directory were committed after the run, so the pull request head is the evidence commit. The counts below are for `79dc63b`. That commit adds `"/starters/nextjs"` to the npm `directories` list in `.github/dependabot.yml`. The uv, GitHub Actions, and Docker entries are unchanged. No package version was bumped. `starters/nextjs/`, `api/`, `web/`, `example-site/`, `CHANGELOG.md`, and `README.md` are unchanged from `b6c6687`.

This VM needed `iptables-legacy` FORWARD set to ACCEPT so Compose containers on a bridge can reach each other (the policy was DROP), and `python3.12-venv` so `pip-audit` can create its temporary environment. Docker was started with `service docker start` because systemd is not pid 1. None of those changes are in the repository.

## What changed

`python3 scripts/check_dependabot.py` on `b6c6687` exits 1:

```
starters/nextjs/package.json (npm /starters/nextjs) is not covered by .github/dependabot.yml
```

The same command on `79dc63b` exits 0 and lists `npm /starters/nextjs  starters/nextjs/package.json` with the existing uv, npm, github-actions, and docker manifests. Log: [dependabot.txt](79dc63b/dependabot.txt). Base log: [b6c6687/dependabot.txt](b6c6687/dependabot.txt).

`tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests` failed on `b6c6687` and passed on `79dc63b`.

## Counts against main `b6c6687`

Base commands were run on a clean checkout of `b6c6687` (label local, 2026-11-11T21:42:25Z onward). Logs: [b6c6687](b6c6687/).

| Run | Main `b6c6687` | This run `79dc63b` |
| --- | --- | --- |
| SQLite `-m "not postgres"` | 502 collected, 497 passed, 1 failed, 4 deselected, 0 skipped | 502 collected, 498 passed, 0 failed, 4 deselected, 0 skipped |
| PostgreSQL, no marker filter | 502 collected, 501 passed, 1 failed, 0 skipped | 502 collected, 502 passed, 0 failed, 0 skipped |
| web vitest | 36 files, 356 passed, 0 skipped | 36 files, 356 passed, 0 skipped |
| example-site `node --test` | 50 pass, 0 fail, 0 skipped | 50 pass, 0 fail, 0 skipped |
| production Playwright | not run on the base in this session | 2 passed, 0 skipped |

The API delta is `tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests`, which failed on the base in both required runs and passed here. Collected counts are unchanged. Web and example-site counts match the base. `ci/` matches `b6c6687`, and the production Playwright run on this tree passed 2 tests.

The four ids deselected on SQLite are the PostgreSQL-marked tests committed in `api/tests/required_runs.json`:

- `tests/test_concurrency.py::test_postgres_workers_skip_locked_rows_and_claim_once`
- `tests/test_indexing.py::test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`
- `tests/test_postgres_product_migration.py::test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`
- `tests/test_search.py::test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`

They are deselected before they run. The skipped count is 0 on both required runs, on the base and on this tree. The PostgreSQL run passed them. `tests/verify_required_runs.py` reported `"ok": true`. [counts.txt](79dc63b/counts.txt).

## Commands and results

Command: `scripts/verify.sh MOSS-063`. Exit 0. Every step in [exit-codes.txt](79dc63b/exit-codes.txt) exited 0.

| Command | Exit | Result |
| --- | --- | --- |
| `uv sync --locked --group dev` | 0 | locked deps installed |
| `ruff check` and `ruff format --check` for `app tests migrations` | 0 | all checks passed; 96 files already formatted |
| ruff check/format of scripts, example-site setup, telemetry smoke | 0 | all checks passed; 18 files and 1 file already formatted |
| `mypy app` | 0 | no issues in 30 source files |
| SQLite required run | 0 | 498 passed, 4 deselected, 0 skipped, 6 warnings in 164.75s |
| PostgreSQL required run in the throwaway container | 0 | 502 passed, 0 deselected, 0 skipped, 6 warnings in 234.11s |
| `tests/verify_required_runs.py` | 0 | union recorded, `ok: true` |
| OTLP Collector smoke | 0 | container removed |
| web `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 | 36 files, 356 passed, build succeeded, 0 vulnerabilities |
| example-site `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 | 50 passed, 0 failed, 0 skipped, build succeeded, 0 vulnerabilities |
| `pip-audit` 2.10.1 against the frozen lock | 0 | No known vulnerabilities found |
| `npm audit` web, example-site, and ci | 0 | found 0 vulnerabilities in each |
| `gitleaks` on `git archive HEAD` | 0 | no leaks found |
| production image, compose, Playwright, teardown | 0 | 2 passed in 2.7s, stack removed |

No `--ignore-vuln`, npm override, or gitleaks allowlist was added.

Versions: Python 3.12.3, uv 0.13.7, ruff 0.16.10, mypy 2.4.0, Node v22.23.4, npm 10.9.9, Docker 29.9.3, Compose v5.7.1, gitleaks 8.30.1, pip-audit 2.10.1. [versions.txt](79dc63b/versions.txt).
