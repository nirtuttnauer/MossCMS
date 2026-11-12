# MOSS-030 REST delivery design

local

Recorded 29 October 2026 (UTC). Docs only: `docs/rest-delivery-design.md`. No application code, lockfiles, workflows, or tests were edited for this ticket. The design is marked **pending CTO approval**. MOSS-031 does not start until the CTO approves it.

## Code under test

| | |
| --- | --- |
| SHA tested | `6b0495772ea7b84f70b9a7ebc83a8edf619a6151` |
| Branch | `cursor/rest-delivery-design-49e9` |
| Parent | `24431f82d35824e18a184c6e6d9f9c8342a76a62` (main, MOSS-002) |
| Baseline | `3a87c73c8e925973608e373863813163b41f04a9` |
| `git status --porcelain` at the start of this run | empty (clean) |
| Date | 2026-10-29T04:17:50Z through 2026-10-29T04:19:54Z |
| Node / npm | v22.23.4 / 10.9.9 |
| Python / uv | 3.12.3 / 0.12.23 |
| PostgreSQL | 16.15 on 127.0.0.1:5432, role `moss` (local trust) |

`6b04957` is the design document rebased onto `24431f8`. API test files are unchanged from `3a87c73` through this SHA. This run is after `uv sync --locked --group dev` on the MOSS-002 lockfile (authlib 1.9.1, certifi 2026.10.23, opentelemetry-api 1.45.1).

## Commands

No `-k`, `--ignore`, new skips, or xfails. Working directory notes are in the command.

```sh
cd api
uv sync --locked --group dev
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run ruff check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py ../ci/telemetry_smoke.py
uv run ruff format --check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py ../ci/telemetry_smoke.py
uv run mypy app
MOSS_USE_SQLITE=false uv run pytest -ra --tb=line
MOSS_USE_SQLITE=false MOSS_TEST_DATABASE_URL='postgresql+psycopg://moss@127.0.0.1:5432/moss' uv run pytest -ra --tb=line

cd web
npm run check
npm test
npm run build

cd example-site
npm run check
npm test
npm run build
```

`web` and `example-site` lockfiles are unchanged from `8912ec1`, when `npm ci` last installed those trees. This run did not reinstall them.

## Results

| Command | Exit | Result |
| --- | --- | --- |
| `uv sync --locked --group dev` | 0 | locked deps installed |
| `uv run ruff check app tests migrations` | 0 | all checks passed |
| `uv run ruff format --check app tests migrations` | 0 | 79 files already formatted |
| ruff check scripts, example-site setup, telemetry smoke | 0 | all checks passed |
| ruff format check of those files | 0 | 15 files already formatted |
| `uv run mypy app` | 0 | no issues in 27 source files |
| SQLite `pytest -ra --tb=line` | 0 | 398 passed, 4 skipped, 6 warnings in 67.23s |
| PostgreSQL `pytest -ra --tb=line` | 0 | 402 passed, 6 warnings in 108.11s |
| `cd web && npm run check` | 0 | `tsc -b` |
| `cd web && npm test` | 0 | 35 files, 317 tests passed |
| `cd web && npm run build` | 0 | vite build succeeded |
| `cd example-site && npm run check` | 0 | `tsc --noEmit` |
| `cd example-site && npm test` | 0 | 46 passed, 0 failed, 0 skipped |
| `cd example-site && npm run build` | 0 | vite build succeeded |

SQLite skipped the four PostgreSQL-only tests that already skip on main and pass on PostgreSQL: `test_postgres_workers_skip_locked_rows_and_claim_once`, `test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`, `test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`, and `test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`. The PostgreSQL run executed the whole suite: 402 passed, 0 skipped. No xfail. Counts match the suite recorded at `3a87c73` (398 passed / 4 skipped on SQLite, 402 passed on PostgreSQL).

Logs: [pytest-sqlite.txt](6b04957/pytest-sqlite.txt), [pytest-postgres.txt](6b04957/pytest-postgres.txt), [lint.txt](6b04957/lint.txt), [web.txt](6b04957/web.txt), [example-site.txt](6b04957/example-site.txt).
