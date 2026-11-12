# MOSS-089 delivery token reveal

local

Recorded 12 November 2026 (UTC). `scripts/verify.sh MOSS-089` ran on a clean tree at `9c42545b9c0d94c5363ec0770fbd2639d0c9a6a8` and exited 1 at `pytest-sqlite`. The script refuses a dirty tree and stops when a step exits non-zero. The commands after that step are the same commands from `scripts/verify.sh`, continued so SQLite, PostgreSQL, and web counts could be recorded. No skip, xfail, audit ignore, or allowlist was added.

## Code under test

| | |
| --- | --- |
| Ticket base | `b6c66870b98af990ee91766e5a965e823bf2b03d` |
| PR base (current `main`) | `5ea1d037bb85e47c2efc1d97f72998d130130878` |
| SHA tested | `9c42545b9c0d94c5363ec0770fbd2639d0c9a6a8` |
| Branch | `cursor/moss-089-delivery-token-once-1bdc` |
| `git status --porcelain` when `scripts/verify.sh` started | empty |
| Started | 2026-11-12T14:44:15Z |
| Finished | 2026-11-12T14:57:14Z |
| Logs | [9c42545](9c42545/) |

`main` at `5ea1d03` is `b6c6687` plus the GitHub Actions pin bump in `.github/workflows/checks.yml` and `.github/workflows/docker.yml`. Product files for this ticket differ from that `main` by `web/src/pages/Settings.tsx` and `web/src/pages/Settings.test.tsx`.

This evidence commit adds the run record. The counts below are for `9c42545`.

## Dependabot failure also on main

`tests/test_dependabot.py::test_dependabot_config_matches_schema_and_covers_manifests` fails because `starters/nextjs/package.json` is not covered by `.github/dependabot.yml`. The same assertion fails on `main` `5ea1d03` ([dependabot.txt](5ea1d03/dependabot.txt), exit 1) and on the ticket base `b6c6687` ([dependabot.txt](b6c6687/dependabot.txt), exit 1). `.github/dependabot.yml` and `starters/nextjs/` were not edited.

`tests/verify_required_runs.py` then reports that same id as the failed id in both required runs ([verify-required-runs.txt](9c42545/verify-required-runs.txt), exit 1).

## Counts against main `5ea1d03`

| Run | Main `5ea1d03` | This run `9c42545` | Skipped |
| --- | --- | --- | --- |
| SQLite `-m "not postgres"` | 497 passed, 1 failed, 4 deselected | 497 passed, 1 failed, 4 deselected | 0 |
| PostgreSQL, no marker filter | 501 passed, 1 failed | 501 passed, 1 failed | 0 |
| web `npm test` | 356 (36 files) | 357 (36 files) | 0 |
| example-site | unchanged tree | 50 passed | 0 |
| production Playwright | unchanged tree | 2 passed | 0 |

The web difference is the new Settings test. API counts match `main` on both database runs. The four ids deselected on SQLite run under PostgreSQL; that split is the same on `main`. Zero skipped.

Main logs: [5ea1d03/pytest-sqlite.txt](5ea1d03/pytest-sqlite.txt), [5ea1d03/pytest-postgres.txt](5ea1d03/pytest-postgres.txt), [5ea1d03/web-test.txt](5ea1d03/web-test.txt). Head summary: [9c42545/counts.txt](9c42545/counts.txt).

## Commands and exits

`scripts/verify.sh MOSS-089` (exit 1 at `pytest-sqlite`):

| Command | Exit |
| --- | --- |
| `uv sync --locked --group dev` | 0 |
| `ruff check` and `ruff format --check` | 0 |
| ruff check/format of scripts, example-site setup, telemetry smoke | 0 |
| `mypy app` | 0 |
| SQLite required run | 1 |

Continued with the same `scripts/verify.sh` commands, label `local`, SHA `9c42545`:

| Command | Exit |
| --- | --- |
| Throwaway `postgres:17-alpine` container | 0 |
| PostgreSQL required run | 1 |
| `tests/verify_required_runs.py` | 1 |
| OTLP Collector smoke | 0 |
| web `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| example-site `npm ci`, check, test, build, `npm audit --audit-level=high` | 0 |
| `pip-audit` against the frozen lock | 0 |
| `npm audit` web, example-site, and ci | 0 |
| `gitleaks` on `git archive HEAD` | 0 |
| production image, compose, Playwright, teardown | 0 |

Exit codes: [9c42545/exit-codes.txt](9c42545/exit-codes.txt).

## What the Settings change covers

After a delivery token is created, Settings shows the returned value in the “New delivery token” field until Dismiss. Dismiss clears that state. A later list load, including a payload that also carries `token`, `secret`, or `digest` fields, does not put those fields back on screen. Remounting Settings starts from empty reveal state. List rows show the name, scopes, and expiry. Revoke still sends `DELETE /api/tokens/<id>`. The value is not written to `console.log`, `console.info`, `console.debug`, `console.warn`, `console.error`, storage, or the page address. `api/app/accounts.py` was not edited.
