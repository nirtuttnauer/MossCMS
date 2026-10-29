# MOSS-032 REST pagination, filters, and locale parity

local

Recorded 29 October 2026 (UTC). The runs below executed against `79f3cbdf0458058f1b12bba7c3b79cbfc2fe47ae` with a clean working tree. This evidence commit only adds the run record.

## Code under test

| | |
| --- | --- |
| SHA tested | `79f3cbdf0458058f1b12bba7c3b79cbfc2fe47ae` |
| Branch | `cursor/rest-list-parity-b069` |
| What that SHA is | MOSS-032 rebased onto main `58047337e9fb1cc67b63866445c8b2e6318f307f` |
| Baseline in the ticket | `3a87c73c8e925973608e373863813163b41f04a9` |
| Previous main | `1a005f233c39617f5dd564354eee7b64801fc263` (MOSS-031): SQLite 411 passed / 4 deselected / 0 skipped, PostgreSQL 415 passed / 0 skipped, collected 415 |
| Main at this run | `58047337e9fb1cc67b63866445c8b2e6318f307f` (includes MOSS-056 Dependabot tests) |
| `git status --porcelain` at the start of the API run | empty (clean) |
| API run | 2026-10-29T05:33:26Z through 2026-10-29T05:37:06Z |
| Web and example site | 2026-10-29T05:33:26Z through 2026-10-29T05:34:08Z |
| Python / uv | 3.12.3 / 0.13.6 |
| ruff / mypy | 0.16.10 / 2.4.0 |
| Node / npm | v22.23.4 / 10.9.9 |
| PostgreSQL | 17.11, `postgres:17-alpine`, `127.0.0.1:5432`, role `pg`, database `postgres` |
| Docker / Compose | 29.1.3 / 2.40.3 |

`79f3cbd` adds optional `locale` on `GET /delivery/entries` and `GET /delivery/entries/{id}`. Omitted, localized values stay maps. A locale code selects that translation from every localized public field, including objects and lists, with no fallback. Reference and asset fields stay ids. Cursors, filters, search, order, and `total` still come from `entry_page` and match delivery GraphQL. `api/tests/test_delivery_rest_parity.py` compares the two protocols.

## Commands

No `-k`, `--ignore`, new skips, or xfails. A runtime skip or xfail fails the API required runs. PostgreSQL-only tests use the `postgres` marker and are excluded from the SQLite required run with `-m "not postgres"`. GitHub Actions was not used.

```sh
cd api
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run mypy app
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres" -ra --tb=line
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres \
  MOSS_TEST_DATABASE_URL='postgresql+psycopg://pg:pgtestpw@127.0.0.1:5432/postgres' \
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
| ruff format check of those files | 0 | 86 files already formatted |
| `uv run mypy app` | 0 | no issues in 28 source files |
| SQLite required run | 0 | collected 435, **431 passed, 4 deselected, 0 skipped**, 6 warnings in 69.26s |
| PostgreSQL 17 required run | 0 | collected 435, **435 passed, 0 deselected, 0 skipped**, 6 warnings in 125.74s |
| `tests/verify_required_runs.py` | 0 | union of passed ids is 435 |
| `cd web && npm run check` | 0 | `tsc -b` |
| `cd web && npm test` | 0 | 35 files, 317 tests passed |
| `cd web && npm run build` | 0 | vite build succeeded |
| `cd example-site && npm run check` | 0 | `tsc --noEmit` |
| `cd example-site && npm test` | 0 | 46 passed, 0 failed, 0 skipped |
| `cd example-site && npm run build` | 0 | vite build succeeded |

The four ids deselected on SQLite are the committed list in `api/tests/required_runs.json`. No xfail.

Against `3a87c73` (398 passed / 4 skipped on SQLite, 402 passed on PostgreSQL) this run is above the baseline. Against MOSS-031 on `1a005f2` (411 / 415) this run is also above. The increase from that main is the Dependabot tests already on `5804733` plus the two parity tests in this change. Web stayed at 317. The example site stayed at 46. No new skips or failures.
