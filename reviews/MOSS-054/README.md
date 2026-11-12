# MOSS-054 local verification script

local

Recorded 29 October 2026 (UTC). `scripts/verify.sh` runs the commands in `.github/workflows/checks.yml`, then `pip-audit` against `api/uv.lock`, a default `npm audit`, and `gitleaks` on the tracked tree. It refuses a dirty tree. A runtime skip or xfail fails the run. There is no allowed-skip list and no audit ignore. PostgreSQL-only tests use the `postgres` marker and are excluded from the SQLite required run with `-m "not postgres"` before they execute.

Earlier runs on older main commits recorded the same script and are redundant with this one. This folder is the run after rebasing onto current main (`687ac7c`, MOSS-034).

## Code under test

| | |
| --- | --- |
| SHA tested | `c684c24a8128bdfb32e8e06279a9481e613fbbe7` |
| Branch | `cursor/moss-054-verify-script-b539` |
| Rebased onto | `687ac7c4278d25efad560694b03ca751afc8f984` (main, MOSS-034) |
| Baseline | `1b55a1be7a91d79c6c1d73a28979c2c1ced40f43` (last recorded MOSS-023 run) |
| `git status --porcelain` at the start of this run | empty (clean) |
| Date | 2026-10-29T06:33:21Z through 2026-10-29T06:38:36Z |
| Python / uv | 3.12.3 / 0.12.23 |
| ruff / mypy / pip-audit | 0.16.10 / 2.4.0 / 2.10.1 |
| Node / npm | v22.23.4 / 10.9.9 |
| PostgreSQL | 17.11, throwaway `postgres:17-alpine` container `moss-verify-pg`, `127.0.0.1:5432`, role `pg`, database `postgres` |
| Docker / Compose | 29.1.3 / 2.40.3 |
| gitleaks | 8.30.1 |

Command: `scripts/verify.sh MOSS-054`. Exit 0. Logs are in [c684c24](c684c24/).

This VM's `iptables-legacy` FORWARD policy was set to ACCEPT before the run, the same host condition MOSS-024 needed for the Compose bridge. `python3.12-venv` is installed so `pip-audit` can create its temporary environment. Neither change is in the repository. The script does not set firewall policy and does not read secrets.

## Counts

492 collected is above the MOSS-023 baseline of 403. The extra API, web, and example-site tests came in on main. Zero skipped and zero failed.

| Run | Collected | Passed | Deselected | Skipped |
| --- | --- | --- | --- | --- |
| SQLite `-m "not postgres"` | 492 | 488 | 4 | 0 |
| PostgreSQL, no marker filter | 492 | 492 | 0 | 0 |
| web |  | 356 (36 files) |  | 0 |
| example-site |  | 47 |  | 0 |
| production Playwright |  | 2 |  | 0 |

The four ids deselected on SQLite and passed on PostgreSQL:

- `tests/test_concurrency.py::test_postgres_workers_skip_locked_rows_and_claim_once`
- `tests/test_indexing.py::test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`
- `tests/test_postgres_product_migration.py::test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`
- `tests/test_search.py::test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`

`tests/verify_required_runs.py` reported the union of passed ids is 492. [counts.json](c684c24/counts.json).

## Commands and results

| Command | Exit | Result |
| --- | --- | --- |
| `uv sync --locked --group dev` | 0 | locked deps installed |
| `ruff check` and `ruff format --check` for `app tests migrations` | 0 | all checks passed; 91 files already formatted |
| ruff check/format of scripts, example-site setup, telemetry smoke | 0 | all checks passed; 18 files and 1 file already formatted |
| `mypy app` | 0 | no issues in 30 source files |
| SQLite required run | 0 | 488 passed, 4 deselected, 0 skipped, 6 warnings in 70.99s |
| PostgreSQL required run in the throwaway container | 0 | 492 passed, 0 deselected, 0 skipped, 6 warnings in 140.97s |
| `tests/verify_required_runs.py` | 0 | union 492, `ok: true` |
| OTLP Collector smoke | 0 | metrics ready, container removed |
| web `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 | 36 files, 356 passed, build succeeded, 0 vulnerabilities |
| example-site `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 | 47 passed, 0 failed, 0 skipped, build succeeded, 0 vulnerabilities |
| `pip-audit` 2.10.1 against the frozen lock | 0 | No known vulnerabilities found |
| `npm audit` web, example-site, and ci | 0 | found 0 vulnerabilities in each (devDependencies included, no `--audit-level`, no `--omit=dev`) |
| `gitleaks` on `git archive HEAD` | 0 | no leaks found |
| production image, compose, Playwright, teardown | 0 | 2 passed in 2.2s, stack removed |

No `--ignore-vuln`, npm override, or gitleaks allowlist was added. gitleaks scans the tracked tree at HEAD. It does not walk older commits, so a fixture removed from the tip is not reported from published history, and dependency installs stay out of the scan.

The skip-auth private marker in `api/tests/test_delivery_authorization.py` is built at runtime. The runtime image copies `shared/` to `/shared/` so production can read the Unicode script table.

## Red-first tests

`python3 scripts/test_verify.py` on this script, before the clean run. Each case exits non-zero, and the script stops on the first failure.

| Test | Result |
| --- | --- |
| dirty tree | non-zero, stderr contains `dirty`, no evidence directory |
| planted `assert False` | `pytest-sqlite` non-zero, PostgreSQL step not started |
| planted `pytest.skip("planted")` | `pytest-sqlite` non-zero, PostgreSQL step not started |
| planted `cookie@0.4.2` devDependency | web `npm audit --audit-level=high` exit 0; default `npm audit` non-zero; gitleaks not started |
| `checks.yml` command diff | every `run` body is present in `scripts/verify.sh` with the same working directory |

`cookie@0.4.2` is a low advisory, so the CI `--audit-level=high` step stays green and the stricter default audit is what fails.
