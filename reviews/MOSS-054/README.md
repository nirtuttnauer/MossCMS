# MOSS-054 local verification script

local

Recorded 29 October 2026 (UTC). `scripts/verify.sh` runs the commands in `.github/workflows/checks.yml`, then `pip-audit` against `api/uv.lock`, a default `npm audit`, and `gitleaks`. It refuses a dirty tree. A runtime skip or xfail fails the run. There is no allowed-skip list and no audit ignore. PostgreSQL-only tests use the `postgres` marker and are excluded from the SQLite required run with `-m "not postgres"` before they execute.

Two clean runs are recorded. `a185dc3` is the script on the suite that matched the MOSS-023 counts exactly. `431fb3a` is that same script rebased onto main after MOSS-010, MOSS-031, and MOSS-056, which added API tests. 433 collected is above the MOSS-023 baseline of 403. Zero skipped in both runs.

## Code under test

| | |
| --- | --- |
| SHA tested | `a185dc3afc51ee124409721cc9b90fd5029f369d` |
| Branch | `cursor/moss-054-verify-script-b539` |
| Parent | `a84eebd8c2fea163f60674c5e54ba03a7a2ae573` (main, after MOSS-024) |
| Baseline | `1b55a1be7a91d79c6c1d73a28979c2c1ced40f43` (last recorded MOSS-023 run) |
| `git status --porcelain` at the start of this run | empty (clean) |
| Date | 2026-10-29T05:20:54Z through 2026-10-29T05:26:55Z |
| Python / uv | 3.12.3 / 0.12.23 |
| ruff / mypy / pip-audit | 0.16.10 / 2.4.0 / 2.10.1 |
| Node / npm | v22.23.4 / 10.9.9 |
| PostgreSQL | 17.11, throwaway `postgres:17-alpine` container `moss-verify-pg`, `127.0.0.1:5432`, role `pg`, database `postgres` |
| Docker / Compose | 29.1.3 / 2.40.3 |
| gitleaks | 8.30.1 |

Command: `scripts/verify.sh MOSS-054`. Exit 0. Logs are in [a185dc3](a185dc3/).

This VM's `iptables-legacy` FORWARD policy was set to ACCEPT before the run, the same host condition MOSS-024 needed for the Compose bridge. `python3.12-venv` is installed so `pip-audit` can create its temporary environment. Neither change is in the repository. The script does not set firewall policy and does not read secrets.

## Counts

These match the last recorded MOSS-023 run (403 collected, SQLite 399 passed and 4 deselected, PostgreSQL 403 passed, web 317, example-site 46). Zero skipped and zero xfailed.

| Run | Collected | Passed | Deselected | Skipped |
| --- | --- | --- | --- | --- |
| SQLite `-m "not postgres"` | 403 | 399 | 4 | 0 |
| PostgreSQL, no marker filter | 403 | 403 | 0 | 0 |
| web |  | 317 (35 files) |  | 0 |
| example-site |  | 46 |  | 0 |
| production Playwright |  | 2 |  | 0 |

The four ids deselected on SQLite and passed on PostgreSQL:

- `tests/test_concurrency.py::test_postgres_workers_skip_locked_rows_and_claim_once`
- `tests/test_indexing.py::test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`
- `tests/test_postgres_product_migration.py::test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`
- `tests/test_search.py::test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`

`tests/verify_required_runs.py` reported the union of passed ids is 403. [counts.json](a185dc3/counts.json).

## Commands and results

| Command | Exit | Result |
| --- | --- | --- |
| `uv sync --locked --group dev` | 0 | locked deps installed |
| `ruff check` and `ruff format --check` for `app tests migrations` | 0 | all checks passed; 82 files already formatted |
| ruff check/format of scripts, example-site setup, telemetry smoke | 0 | all checks passed; 16 files and 1 file already formatted |
| `mypy app` | 0 | no issues in 27 source files |
| SQLite required run | 0 | 399 passed, 4 deselected, 0 skipped, 6 warnings in 60.25s |
| PostgreSQL required run in the throwaway container | 0 | 403 passed, 0 deselected, 0 skipped, 6 warnings in 121.54s |
| `tests/verify_required_runs.py` | 0 | union 403, `ok: true` |
| OTLP Collector smoke | 0 | metrics ready, container removed |
| web `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 | 35 files, 317 passed, build succeeded, 0 vulnerabilities |
| example-site `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 | 46 passed, 0 failed, 0 skipped, build succeeded, 0 vulnerabilities |
| `pip-audit` 2.10.1 against the frozen lock | 0 | No known vulnerabilities found |
| `npm audit` web, example-site, and ci | 0 | found 0 vulnerabilities in each (devDependencies included, no `--audit-level`, no `--omit=dev`) |
| `gitleaks detect` | 0 | 90 commits scanned, no leaks found |
| production image, compose, Playwright, teardown | 0 | 2 passed in 2.9s, stack removed |

No `--ignore-vuln`, npm override, or gitleaks allowlist was added.

## Rebased run on current main

local

`431fb3a8527427a80982b9b98ddd42e875294cf2` is `a185dc3` replayed onto `28c3dc9` (main after MOSS-026, which includes MOSS-010, MOSS-031, and MOSS-056). `git status --porcelain` was empty. 2026-10-29T05:28:32Z through 2026-10-29T05:33:28Z. Same toolchain as the run above. `scripts/verify.sh MOSS-054` exited 0.

| Run | Collected | Passed | Deselected | Skipped |
| --- | --- | --- | --- | --- |
| SQLite `-m "not postgres"` | 433 | 429 | 4 | 0 |
| PostgreSQL, no marker filter | 433 | 433 | 0 | 0 |
| web |  | 317 (35 files) |  | 0 |
| example-site |  | 46 |  | 0 |
| production Playwright |  | 2 |  | 0 |

The same four PostgreSQL ids are deselected on SQLite and passed on PostgreSQL. `tests/verify_required_runs.py` reported the union is 433. SQLite finished in 64.02s (429 passed, 4 deselected, 0 skipped). PostgreSQL finished in 126.26s (433 passed, 0 skipped). mypy reported 28 source files. ruff format reported 85 API files and 17 script files. `pip-audit` reported no known vulnerabilities. `npm audit` reported 0 vulnerabilities for web, example-site, and ci. gitleaks scanned 106 commits and found no leaks. Playwright reported 2 passed.

433 ≥ 403. The extra 30 API tests come from main, not from this ticket. This ticket adds no API, web, or example-site test.

Logs: [431fb3a](431fb3a/).

## Run after the changelog landed

local

`d870650c9f21be9dacbb3b24007c6599cea36593` is the same script and evidence replayed onto `5804733` (main, MOSS-057 changelog). `git status --porcelain` was empty. 2026-10-29T05:34:26Z through 2026-10-29T05:39:17Z. `scripts/verify.sh MOSS-054` exited 0. Counts were unchanged from `431fb3a`: SQLite 429 passed, 4 deselected, 0 skipped; PostgreSQL 433 passed, 0 skipped; web 317; example-site 46 passed, 0 failed, 0 skipped. `pip-audit`, `npm audit`, and gitleaks were clean. Logs: [d870650](d870650/).

## Run after MOSS-032

local

`e8ec4cb` is the script replayed onto `d9db93d` (main, MOSS-032). `git status --porcelain` was empty. `scripts/verify.sh MOSS-054` exited 0. SQLite collected 435, **431 passed, 4 deselected, 0 skipped**. PostgreSQL collected 435, **435 passed, 0 skipped**. Web 317 and example-site 46 were unchanged. Audits and gitleaks were clean. 435 ≥ 403. Logs: [e8ec4cb](e8ec4cb/).

## Run after MOSS-033, not merged

local

`4740f0f8a77aebaaaeea962690accf4836909fe1` is the script replayed onto `ae66eb0` (main, MOSS-033). `git status --porcelain` was empty. 2026-10-29T05:45:36Z through the gitleaks step. `scripts/verify.sh MOSS-054` exited 1.

| Check | Exit | Result |
| --- | --- | --- |
| SQLite required run | 0 | 439 collected, **435 passed, 4 deselected, 0 skipped** |
| PostgreSQL required run | 0 | 439 collected, **439 passed, 0 skipped** |
| web | 0 | 317 passed |
| example-site | 0 | 46 passed, 0 failed, 0 skipped |
| `pip-audit` | 0 | No known vulnerabilities found |
| `npm audit` (web, example-site, ci) | 0 | found 0 vulnerabilities |
| `gitleaks detect` | 1 | 2 `generic-api-key` hits |

439 ≥ 403. Zero runtime skips. The same four PostgreSQL ids are deselected on SQLite and passed on PostgreSQL.

gitleaks stopped the run before production Docker. Both hits are the fixture `"secret": "moss033-skip-secret"` in `api/tests/test_delivery_authorization.py` (lines 686 and 693), added on main by MOSS-033 (`ae66eb0`). No allowlist, baseline, or audit ignore was added. Logs: [4740f0f](4740f0f/).

## Red-first tests

`python3 scripts/test_verify.py` on this script, before the clean run above. Each case exits non-zero, and the script stops on the first failure.

| Test | Result |
| --- | --- |
| dirty tree | non-zero, stderr contains `dirty`, no evidence directory |
| planted `assert False` | `pytest-sqlite` non-zero, PostgreSQL step not started |
| planted `pytest.skip("planted")` | `pytest-sqlite` non-zero, PostgreSQL step not started |
| planted `cookie@0.4.2` devDependency | web `npm audit --audit-level=high` exit 0; default `npm audit` non-zero; gitleaks not started |
| `checks.yml` command diff | every `run` body is present in `scripts/verify.sh` with the same working directory |

`cookie@0.4.2` is a low advisory, so the CI `--audit-level=high` step stays green and the stricter default audit is what fails.
