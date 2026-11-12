# MOSS-024 local release run

local

Recorded 29 October 2026 (UTC). One local run of the checks in `.github/workflows/checks.yml` at the current main SHA, plus the MOSS-023 union check, `pip-audit`, and `npm audit`. A runtime skip or xfail fails the API required runs. There is no allowed-skip list. PostgreSQL-only tests use the `postgres` marker and are excluded from the SQLite required run with `-m "not postgres"` before they execute. Compose tests use the `compose` marker and ran in both required runs.

## Code under test

| | |
| --- | --- |
| SHA tested | `d50e2788485e4ef0c65598c4c2f2bd7536e1ed96` |
| Branch during the run | `cursor/moss-024-local-release-4458` at the same commit as `main` |
| `main` | `d50e2788485e4ef0c65598c4c2f2bd7536e1ed96` (MOSS-023, after MOSS-001, MOSS-002, and MOSS-025) |
| Baseline | `3a87c73c8e925973608e373863813163b41f04a9` |
| `git status --porcelain` at the start of this run | empty (clean) |
| Date | 2026-10-29T04:32:22Z through 2026-10-29T04:44:51Z |
| Python / uv | 3.12.3 / 0.12.23 |
| ruff / mypy / pip-audit | 0.16.10 / 2.4.0 / 2.10.1 |
| Node / npm | v22.23.4 / 10.9.9 |
| PostgreSQL | 17.11, `postgres:17-alpine`, Docker Compose project `moss-024-pg`, `127.0.0.1:5432`, role `pg`, database `postgres` |
| Docker / Compose | 29.1.3 / 2.40.3 |

No application code, lockfile, workflow, or test was edited for this ticket. The only commit is this record.

## Expected counts, stated before the API runs

Collected at 2026-10-29T04:32:36Z with `required_runs.collect_full_suite()` and the committed marker expressions, before either required run. The manifest check reported no problems. Full statement: [expected-before-run.json](d50e278/expected-before-run.json).

| Run | Collected | Deselected by marker | Passed | Skipped |
| --- | --- | --- | --- | --- |
| SQLite `-m "not postgres"` | 403 | 4 | 399 | 0 |
| PostgreSQL, no marker filter | 403 | 0 | 403 | 0 |

The four ids deselected on SQLite:

- `tests/test_concurrency.py::test_postgres_workers_skip_locked_rows_and_claim_once`
- `tests/test_indexing.py::test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`
- `tests/test_postgres_product_migration.py::test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`
- `tests/test_search.py::test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`

Baseline on `3a87c73`: 402 collected, SQLite 398 passed and 4 runtime skips, PostgreSQL 402 passed. This tree adds `tests/test_required_runs.py`. 403 ≥ 402.

## API

PostgreSQL came from Docker Compose, matching the `api_postgres` service in `checks.yml` (`postgres:17-alpine`, user `pg`, database `postgres`). `MOSS_USE_SQLITE=false` is the README local prefix. This checkout had no `.env`. The workflow's SQLite job sets only `MOSS_REQUIRED_RUN=sqlite`.

```sh
cd api
uv sync --locked --group dev
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run ruff check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run ruff format --check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run ruff check --config pyproject.toml ../ci/telemetry_smoke.py
uv run ruff format --check --config pyproject.toml ../ci/telemetry_smoke.py
uv run mypy app
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres"
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres \
  MOSS_TEST_DATABASE_URL='postgresql+psycopg://pg:pgtestpw@localhost:5432/postgres' \
  uv run pytest
uv run python tests/verify_required_runs.py
```

| Command | Exit | Result |
| --- | --- | --- |
| `uv sync --locked --group dev` | 0 | locked deps installed, Pillow 13.0.0 |
| `ruff check app tests migrations` | 0 | all checks passed |
| `ruff format --check app tests migrations` | 0 | 82 files already formatted |
| ruff check/format of scripts, example-site setup, telemetry smoke | 0 | all checks passed; 14 files and 1 file already formatted |
| `mypy app` | 0 | no issues in 27 source files |
| SQLite required run | 0 | collected 403, **399 passed, 4 deselected, 0 skipped**, 6 warnings in 69.03s |
| PostgreSQL required run | 0 | collected 403, **403 passed, 0 deselected, 0 skipped**, 6 warnings in 145.05s |
| `tests/verify_required_runs.py` | 0 | union of passed ids is 403 |

The counts after the runs match the counts stated before them. `tests/test_compose.py` executed 5 tests in each run. No xfail.

Logs: [ruff-check.txt](d50e278/ruff-check.txt), [ruff-format.txt](d50e278/ruff-format.txt), [ruff-scripts.txt](d50e278/ruff-scripts.txt), [mypy.txt](d50e278/mypy.txt), [pytest-sqlite.txt](d50e278/pytest-sqlite.txt), [pytest-postgres.txt](d50e278/pytest-postgres.txt), [verify.txt](d50e278/verify.txt).

## OTLP smoke

The `api` job's Collector step, with the pinned image `otel/opentelemetry-collector-contrib:0.156.0` and `ops/otel-collector.yaml`.

| Command | Exit | Result |
| --- | --- | --- |
| Collector smoke | 0 | metrics ready, evidence written, container removed |

Log: [otel.txt](d50e278/otel.txt).

## pip-audit

No `--ignore-vuln`, allowlist, or audit exception. `uv export` wrote the frozen all-groups requirements. Its listing is in the log. `pip-audit` printed `No known vulnerabilities found`.

```sh
cd api
uv export --frozen --all-groups --no-emit-project -o /tmp/moss-024/requirements.txt
uv run --with pip-audit pip-audit --progress-spinner off -r /tmp/moss-024/requirements.txt
```

| Command | Exit | Result |
| --- | --- | --- |
| `uv export --frozen` | 0 | requirements written |
| `pip-audit` 2.10.1 | 0 | No known vulnerabilities found |

Log: [pip-audit.txt](d50e278/pip-audit.txt). Version: [pip-audit-version.txt](d50e278/pip-audit-version.txt).

## Web and example-site

`npm ci` had already installed the lockfiles (web 0 vulnerabilities, example-site 0 vulnerabilities, ci 0 vulnerabilities). The recorded commands:

```sh
cd web && npm run check && npm test && npm run build && npm audit --audit-level=high
cd example-site && npm run check && npm test && npm run build && npm audit --audit-level=high
npm audit   # web, example-site, and ci, default audit, no --audit-level and no --omit=dev
```

| Command | Exit | Result |
| --- | --- | --- |
| web check, test, build, `npm audit --audit-level=high` | 0 | `tsc -b`; 35 files, 317 tests passed; vite build succeeded; 0 vulnerabilities |
| example-site check, test, build, `npm audit --audit-level=high` | 0 | `tsc --noEmit`; 46 passed, 0 failed, 0 skipped; vite build succeeded; 0 vulnerabilities |
| `npm audit` web | 0 | info 0, low 0, moderate 0, high 0, critical 0, total 0 |
| `npm audit` example-site | 0 | info 0, low 0, moderate 0, high 0, critical 0, total 0 |
| `npm audit` ci | 0 | info 0, low 0, moderate 0, high 0, critical 0, total 0 |

Logs: [web.txt](d50e278/web.txt), [example-site.txt](d50e278/example-site.txt), [npm-audit-web.txt](d50e278/npm-audit-web.txt), [npm-audit-example-site.txt](d50e278/npm-audit-example-site.txt), [npm-audit-ci.txt](d50e278/npm-audit-ci.txt), and the matching `.json` files.

## Production Docker

```sh
cd ci && npx playwright install --with-deps chromium
docker build --tag mosscms:smoke .
docker compose -f ci/compose.yaml -p mosscms-smoke up --no-build -d --wait --wait-timeout 180
cd ci && npm test
docker compose -f ci/compose.yaml -p mosscms-smoke down --volumes
```

| Command | Exit | Result |
| --- | --- | --- |
| `npx playwright install --with-deps chromium` | 0 | Chromium headless shell installed |
| `docker build --tag mosscms:smoke .` | 0 | image `mosscms:smoke` built |
| first `compose up --wait` | 1 | app unhealthy: this VM's `iptables-legacy` FORWARD policy was DROP and did not accept the Compose bridge, so the app stayed in SYN_SENT to Postgres |
| rerun `compose up --wait` after `iptables-legacy -P FORWARD ACCEPT` | 0 | same image, app healthy |
| `npm test` (playwright) | 0 | 2 passed in 2.7s |
| `compose down --volumes` | 0 | stack removed |

The host firewall change is not a repository change. The two Playwright tests were `production readiness and packaged branding assets` and `production setup, login and branding on desktop and mobile`.

Log: [production-docker.txt](d50e278/production-docker.txt).
