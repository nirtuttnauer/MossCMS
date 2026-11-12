# MOSS-034 OpenAPI artifact, schema diff, ETag, and docs

local

Recorded 29 October 2026 (UTC). The runs below executed against `524a805fec6b77033a8badc4287d7d76a92958ab` with a clean working tree. This evidence commit only adds the run record. GitHub Actions was not used.

## Code under test

| | |
| --- | --- |
| SHA tested | `524a805fec6b77033a8badc4287d7d76a92958ab` |
| Branch | `cursor/moss-034-openapi-b148` |
| What that SHA is | MOSS-034 rebased onto main `0a641e132bacd622d5e843a48cfbccc70ae2347d` |
| Baseline in the ticket | `3a87c73c8e925973608e373863813163b41f04a9` |
| Previous main | `0a641e132bacd622d5e843a48cfbccc70ae2347d` (MOSS-027) |
| `git status --porcelain` at the start of each API run | empty (clean) |
| API, web, and example-site start | 2026-10-29T06:19:35Z |
| PostgreSQL run end | 2026-10-29T06:23:34Z |
| Lint | 2026-10-29T06:21:19Z through 2026-10-29T06:21:20Z |
| Python / uv | 3.12.3 / 0.12.23 |
| ruff / mypy | 0.16.10 / 2.4.0 |
| Node / npm | v22.23.4 / 10.9.9 |
| PostgreSQL | 16.15, role `ubuntu`, local socket, database `postgres` |
| Docker / Compose | 29.1.3 / 2.40.3 (compose tests ran) |

`524a805` commits the FastAPI-generated OpenAPI document at `api/openapi.json`. `api/tests/test_openapi.py` fails when that file differs from the generated schema. `GET` and `HEAD /openapi.json` are public and use the delivery ETag helper, including 304. `/docs` renders the document. The written reference is `docs/rest-openapi.md`.

## Commands

No `-k`, `--ignore`, new skips, or xfails. A runtime skip or xfail fails the API required runs. PostgreSQL-only tests use the `postgres` marker and are excluded from the SQLite required run with `-m "not postgres"`. Compose tests ran in both required runs.

```sh
cd api
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run ruff check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py ../ci/telemetry_smoke.py
uv run ruff format --check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py ../ci/telemetry_smoke.py
uv run mypy app
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres" -ra --tb=line
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres \
  MOSS_TEST_DATABASE_URL='postgresql+psycopg://ubuntu@/postgres' \
  uv run pytest -ra --tb=line
uv run python tests/verify_required_runs.py

cd web
npm run check && npm test && npm run build

cd example-site
npm run check && npm test && npm run build
```

## Results

| Command | Exit | Result |
| --- | --- | --- |
| ruff check app, tests, migrations | 0 | all checks passed |
| ruff format check of those files | 0 | 91 files already formatted |
| ruff check scripts, example-site setup, telemetry smoke | 0 | all checks passed |
| ruff format check of those files | 0 | 17 files already formatted |
| `uv run mypy app` | 0 | no issues in 30 source files |
| SQLite required run | 0 | collected 492, **488 passed, 4 deselected, 0 skipped**, 6 warnings in 82.63s |
| PostgreSQL 16 required run | 0 | collected 492, **492 passed, 0 deselected, 0 skipped**, 6 warnings in 110.09s |
| `tests/verify_required_runs.py` | 0 | union of passed ids is 492 |
| `cd web && npm run check` | 0 | `tsc -b` |
| `cd web && npm test` | 0 | 36 files, 356 tests passed |
| `cd web && npm run build` | 0 | vite build succeeded |
| `cd example-site && npm run check` | 0 | `tsc --noEmit` |
| `cd example-site && npm test` | 0 | 47 passed, 0 failed, 0 skipped |
| `cd example-site && npm run build` | 0 | vite build succeeded |

The four ids deselected on SQLite are the committed list in `api/tests/required_runs.json`: `test_postgres_workers_skip_locked_rows_and_claim_once`, `test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`, `test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`, and `test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`. They passed in the PostgreSQL run. No xfail. `tests/test_compose.py` executed in both required runs.

Against `3a87c73` (398 passed / 4 skipped on SQLite, 402 passed on PostgreSQL) this run is above the baseline. Against MOSS-033 on `ae66eb0` (435 / 439) it is also above. Collected tests are 492. Three of them are the new tests in `api/tests/test_openapi.py`. Web is 356 and the example site is 47 because `0a641e1` already contains the slug and example-site tests that landed after `ae66eb0`; this change does not add web or example-site tests. No new skip or failure.

Logs: [pytest-sqlite.txt](524a805/pytest-sqlite.txt), [pytest-postgres.txt](524a805/pytest-postgres.txt), [verify.txt](524a805/verify.txt), [lint.txt](524a805/lint.txt), [web.txt](524a805/web.txt), [example-site.txt](524a805/example-site.txt).
