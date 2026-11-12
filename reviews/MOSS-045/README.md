# MOSS-045 verification counts

local

Recorded 29 October 2026 (UTC). Documentation only: `TODO.md` and `README.md` now quote suite counts from the [MOSS-024 record](../MOSS-024/README.md) at `d50e2788485e4ef0c65598c4c2f2bd7536e1ed96`. This directory is the local run of the checks in `.github/workflows/checks.yml` on the documentation commit. No application code, lockfile, workflow, or test was edited. No skip, xfail, audit ignore, allowlist, or override was added.

## Code under test

| | |
| --- | --- |
| SHA tested | `b9c336d397b37c9075bad0765fb375c0c513faaa` |
| Branch | `cursor/moss-045-refresh-verification-cc3e` |
| Parent | `a84eebd8c2fea163f60674c5e54ba03a7a2ae573` (`main`, MOSS-024 merge) |
| Baseline in the ticket | `3a87c73c8e925973608e373863813163b41f04a9` |
| `git status --porcelain` at the start of this run | empty (clean) |
| Date | 2026-10-29T04:53:29Z through 2026-10-29T04:58:41Z |
| Python / uv | 3.12.3 / 0.12.23 |
| ruff / mypy | 0.16.10 / 2.4.0 |
| Node / npm | v22.23.4 / 10.9.9 |
| PostgreSQL for the API required run | 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1), role `pg`, database `postgres`, `localhost:5432` |
| Production Compose database | `postgres:17-alpine` from `ci/compose.yaml` |
| Docker / Compose | 29.1.3 / 2.40.3 |

`git status --porcelain` was empty again after the run. The API required-run plugin wrote `api/.required-run-results/`, which is gitignored.

MOSS-024 records the baseline at `3a87c73` as 402 collected. This run collected 403. 403 is greater than 402.

## Commands

Working directory is the repository root unless noted. The SQLite marker expression was one pytest argument, `not postgres` (the log's COMMAND line does not show the shell quotes).

```sh
cd api
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

cd web && npm run check && npm test && npm run build && npm audit --audit-level=high
cd example-site && npm run check && npm test && npm run build && npm audit --audit-level=high

docker run --rm -d --name moss-otel-smoke \
  -p 127.0.0.1:14318:4318 -p 127.0.0.1:19464:9464 \
  -v "$PWD/ops/otel-collector.yaml:/etc/otelcol/config.yaml:ro" \
  otel/opentelemetry-collector-contrib:0.156.0@sha256:125bdbeb7590cc1952c5b3430ecf14063568980c2c93d5b38676cc0446ed8108 \
  --config=/etc/otelcol/config.yaml
cd api && MOSS_USE_SQLITE=false PYTHONPATH=. uv run python ../ci/telemetry_smoke.py \
  --endpoint http://127.0.0.1:14318 --metrics-url http://127.0.0.1:19464/metrics \
  --output /tmp/moss-otel-evidence/collector-smoke.json

cd ci && npx playwright install --with-deps chromium
docker build --tag mosscms:smoke .
docker compose -f ci/compose.yaml -p mosscms-smoke up --no-build -d --wait --wait-timeout 180
cd ci && npm test
docker compose -f ci/compose.yaml -p mosscms-smoke down --volumes
```

Before Compose `--wait`, this host's FORWARD policies were set to ACCEPT (`iptables` and `iptables-legacy`). That is a host change, not a repository change. Compose `--wait` then exited 0 on the first attempt.

## Results

| Command | Exit | Result |
| --- | --- | --- |
| `ruff check app tests migrations` | 0 | all checks passed |
| `ruff format --check app tests migrations` | 0 | 82 files already formatted |
| ruff check of scripts and example-site setup | 0 | all checks passed |
| ruff format check of those files | 0 | 14 files already formatted |
| ruff check of `ci/telemetry_smoke.py` | 0 | all checks passed |
| ruff format check of that file | 0 | 1 file already formatted |
| `mypy app` | 0 | no issues in 27 source files |
| SQLite required run | 0 | collected 403 items / 4 deselected / 399 selected; 399 passed, 4 deselected, 6 warnings in 56.84s |
| PostgreSQL required run | 0 | collected 403 items; 403 passed, 6 warnings in 93.78s |
| `tests/verify_required_runs.py` | 0 | `"ok": true`; sqlite passed 399, deselected 4, skipped 0; postgres passed 403, deselected 0, skipped 0 |
| web check, test, build, `npm audit --audit-level=high` | 0 | 35 files, 317 tests passed; vite build succeeded; `found 0 vulnerabilities` |
| example-site check, test, build, `npm audit --audit-level=high` | 0 | 46 tests, 46 pass, 0 fail, 0 cancelled, 0 skipped, 0 todo; vite build succeeded; `found 0 vulnerabilities` |
| OTLP collector smoke | 0 | evidence written, container removed |
| `npx playwright install --with-deps chromium` | 0 | Chromium headless shell installed |
| `docker build --tag mosscms:smoke .` | 0 | image `mosscms:smoke` built |
| `compose up --wait` | 0 | `mosscms-smoke-db-1` healthy, `mosscms-smoke-app-1` healthy |
| `ci` `npm test` | 0 | 2 passed (3.0s) |
| `compose down --volumes` | 0 | stack removed |

`tests/verify_required_runs.py` is the skip count: both required runs recorded `"skipped": 0`. The four SQLite deselections are the PostgreSQL-only ids already committed in `api/tests/required_runs.json`. They ran in the PostgreSQL required run. No xfail.

The two Playwright tests were `production readiness and packaged branding assets` and `production setup, login and branding on desktop and mobile`.

Passed counts on this SHA match the MOSS-024 record cited in `TODO.md` and `README.md`: PostgreSQL 403 passed, SQLite 399 passed and 4 deselected, admin 317 passed, example-site server 46 passed. Durations differ from that record and are the ones in the table above. The documentation quotes the MOSS-024 log figures, including Playwright 2 passed (2.7s) at `d50e278`, and names that SHA.

Logs: [pytest-sqlite.txt](b9c336d/pytest-sqlite.txt), [pytest-postgres.txt](b9c336d/pytest-postgres.txt), [verify.txt](b9c336d/verify.txt), [ruff-check.txt](b9c336d/ruff-check.txt), [ruff-format.txt](b9c336d/ruff-format.txt), [ruff-scripts-check.txt](b9c336d/ruff-scripts-check.txt), [ruff-scripts-format.txt](b9c336d/ruff-scripts-format.txt), [ruff-telemetry-check.txt](b9c336d/ruff-telemetry-check.txt), [ruff-telemetry-format.txt](b9c336d/ruff-telemetry-format.txt), [mypy.txt](b9c336d/mypy.txt), [web.txt](b9c336d/web.txt), [example-site.txt](b9c336d/example-site.txt), [otel.txt](b9c336d/otel.txt), [playwright-install.txt](b9c336d/playwright-install.txt), [docker-build.txt](b9c336d/docker-build.txt), [iptables.txt](b9c336d/iptables.txt), [compose-up.txt](b9c336d/compose-up.txt), [playwright.txt](b9c336d/playwright.txt), [compose-down.txt](b9c336d/compose-down.txt).
