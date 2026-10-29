# MOSS-029 password reset without email

local

Recorded 29 October 2026 (UTC). An operator can reset an account password when MossCMS has no mail delivery. The CLI prints one recovery link. The link works once, expires after one day, and a successful reset replaces the password and signs out existing sessions.

## Code under test

| | |
| --- | --- |
| SHA tested | `c71a1f80aebc5b5c5243fa39fc7959757ce99706` |
| Code commit | `03eaf42` (reset command, tests, and operator steps) |
| Branch | `cursor/moss-029-password-reset-83ab` |
| Parent | `ae66eb0a9218cce4d24a45fa887126ea974013b8` (main, after MOSS-033) |
| Baseline | `3a87c73c8e925973608e373863813163b41f04a9` |
| Previous suite | `28c3dc9` / MOSS-026 at `835fbf6`: 433 collected |
| `git status --porcelain` at the start of this run | empty (clean) |
| Date | 2026-10-29T05:51:06Z through 2026-10-29T05:54:27Z |
| Python / uv | 3.12.3 / 0.12.23 |
| ruff / mypy | 0.16.10 / 2.4.0 |
| Node / npm | v22.23.4 / 10.9.9 |
| PostgreSQL | 16.15, role `ubuntu`, local socket |
| Docker | CLI 29.1.3, Compose 2.40.3 (compose config tests ran; the daemon was not started) |

`main` moved from `28c3dc9` to `ae66eb0` after the first suite. This branch was rebased onto `ae66eb0`. `git diff 8611b1a 03eaf42` for `api/app/cli.py`, `api/tests/test_cli.py`, `README.md`, and `docs/deployment-recovery.md` is empty, so the reset behavior is the same bytes as the earlier run. The API commands below were run again on the rebased tree. Web and example-site sources are unchanged from that earlier run (317 and 46), which used the same commands on 2026-10-29T05:37:08Z through 2026-10-29T05:40:54Z.

`UV_NO_ENV_FILE=1`. No `.env` was present in the checkout.

## Commands

No `-k`, `--ignore`, new skips, or xfails. Working directory `api` unless noted.

```sh
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run ruff check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py ../ci/telemetry_smoke.py
uv run ruff format --check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py ../ci/telemetry_smoke.py
uv run mypy app
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -ra --tb=line -m "not postgres"
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres \
  MOSS_TEST_DATABASE_URL='postgresql+psycopg://ubuntu@/ubuntu' \
  uv run pytest -ra --tb=line
uv run python tests/verify_required_runs.py

cd web && npm ci && npm run check && npm test && npm run build
cd example-site && npm ci && npm run check && npm test && npm run build
```

| Command | Exit | Result |
| --- | --- | --- |
| `ruff check app tests migrations` | 0 | all checks passed |
| `ruff format --check app tests migrations` | 0 | 87 files already formatted |
| ruff check scripts, example-site setup, and telemetry smoke | 0 | all checks passed |
| ruff format check of those files | 0 | 17 files already formatted |
| `mypy app` | 0 | no issues in 28 source files |
| SQLite required run | 0 | collected 441, **437 passed, 4 deselected, 0 skipped**, 6 warnings in 70.68s |
| PostgreSQL required run | 0 | collected 441, **441 passed, 0 deselected, 0 skipped**, 6 warnings in 104.24s |
| `tests/verify_required_runs.py` | 0 | union of passed ids is 441 |
| web `npm ci`, `npm run check`, `npm test`, `npm run build` | 0 | `tsc -b`; 35 files, 317 tests passed; vite build |
| example-site `npm ci`, `npm run check`, `npm test`, `npm run build` | 0 | `tsc --noEmit`; 46 passed, 0 failed, 0 skipped; vite build |

441 ≥ 402 at `3a87c73`, and 441 ≥ 433 on the MOSS-026 suite. The two tests added here are `test_reset_password_cli_link_replaces_the_password_once` and `test_reset_password_cli_link_expires_on_an_injected_clock`. The four SQLite deselections are the committed PostgreSQL-only tests, and they passed in the PostgreSQL run:

- `tests/test_concurrency.py::test_postgres_workers_skip_locked_rows_and_claim_once`
- `tests/test_indexing.py::test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`
- `tests/test_postgres_product_migration.py::test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`
- `tests/test_search.py::test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`

No xfail. No new skip.

Logs: [pytest-sqlite.txt](c71a1f8/pytest-sqlite.txt), [pytest-postgres.txt](c71a1f8/pytest-postgres.txt), [verify.txt](c71a1f8/verify.txt), [ruff-check.txt](c71a1f8/ruff-check.txt), [ruff-format.txt](c71a1f8/ruff-format.txt), [ruff-scripts.txt](c71a1f8/ruff-scripts.txt), [ruff-scripts-format.txt](c71a1f8/ruff-scripts-format.txt), [mypy.txt](c71a1f8/mypy.txt), [web-check.txt](c71a1f8/web-check.txt), [web-test.txt](c71a1f8/web-test.txt), [web-build.txt](c71a1f8/web-build.txt), [example-site-check.txt](c71a1f8/example-site-check.txt), [example-site-test.txt](c71a1f8/example-site-test.txt), [example-site-build.txt](c71a1f8/example-site-build.txt).

## rehearsal (Linux VM)

Recorded 29 October 2026 (UTC), 2026-10-29T05:46Z through 2026-10-29T05:49:24Z. The reset sources were `8611b1a`, byte-identical to `03eaf42` on this rebased branch. `git status --porcelain` was empty before the browser session. This section is the operator command and the opened link. It is separate from the `local` suite above.

This VM had no running Docker daemon, so the command was the module the documented Compose command runs:

```sh
cd api
uv run python -m app.cli reset-password --email reset-rehearsal@example.com
```

The API was `uvicorn` on `127.0.0.1:8001` with `MOSS_PUBLIC_URL=http://127.0.0.1:5173` and PostgreSQL 16.15 database `moss_rehearsal`. The admin was the Vite dev server on `127.0.0.1:5173`, proxying `/auth` to that API. Passwords, the setup token, `MOSS_SECRET_KEY`, and the reset tokens are not in this record.

| Step | Result |
| --- | --- |
| `/auth/setup` | 200, account `reset-rehearsal@example.com`, workspace `Rehearsal workspace` |
| Login with the original password, before reset | 200 |
| CLI | exit 0. One printed line. Prefix `http://127.0.0.1:5173/#reset/`. Token length 43 |
| Open that link | Page title MossCMS. Heading “Reset your password”. Button “Set password” |
| Submit the account email and a new password | Landed on `#content` in `Rehearsal workspace` as admin |
| Sign out, then sign in with the original password | Stayed on `#login`. Alert: “Invalid email or password.” |
| Sign in with the new password | Landed on `#content` again |
| Open the same link and submit again | Stayed on the reset URL. Alert: “This invitation or recovery link is invalid or expired.” |
| Second CLI link, then `expires_at` set to `2020-01-01` | Submit stayed on the reset URL with the same alert. The reset row was still stored |
| Login with the original password after that | 401 |
| Login with the password typed into the expired link | 401 |
| Login with the password from the first successful reset | 200 |

Audit rows included `account.recovery.issue` with actor `operator` and `account.reset.accept` for the account email. The injected-clock test in `tests/test_cli.py` is the one-day boundary: a link still works one second before `days=1`, and the next link fails when the clock reaches that expiry. The rehearsal check above is the same expiry comparison on the running server, with the stored timestamp moved into the past.

Operator steps for a client installation are in the [client guide](../../README.md#reset-a-password-without-email) and the [operator guide](../../docs/deployment-recovery.md#reset-a-password-without-email).
