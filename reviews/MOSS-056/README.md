# MOSS-056 Dependabot

local

Recorded 29 October 2026 (UTC). `.github/dependabot.yml` schedules monthly version updates, one group per ecosystem, with `open-pull-requests-limit: 3`. The checker validates that file against the vendored SchemaStore Dependabot 2.0 schema and requires every manifest directory to be covered. No audit ignore, allowlist, or override was added. Repository settings were not changed.

MOSS-004 covers only SECURITY.md. This change does not add that file.

## Code under test

| | |
| --- | --- |
| SHA tested | `5d6aff6a99024d23894078e58ff110332c2bf337` |
| Branch | `cursor/moss-056-dependabot-91c6` |
| Parent on main | `1a005f233c39617f5dd564354eee7b64801fc263` (main, MOSS-031) |
| Baseline in the ticket | `d50e2788485e4ef0c65598c4c2f2bd7536e1ed96` (403 collected) |
| `git status --porcelain` at the start of this run | empty (clean) |
| Date | 2026-10-29T05:15:51Z through 2026-10-29T05:19:21Z |
| Python / uv | 3.12.3 / 0.12.23 |
| ruff / mypy | 0.16.10 / 2.4.0 |
| Node / npm | v22.23.4 / 10.9.9 |
| PostgreSQL | 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1), role `ubuntu`, database `ubuntu` |
| Docker / Compose | 29.1.3 / 2.40.3 |

`git status --porcelain` was empty again after the run. `api/.required-run-results/` is gitignored.

Collected API tests: 433. The ticket baseline at `d50e278` collected 403. 433 is greater than 403. The extra tests are `tests/test_dependabot.py` plus tests that landed on main after that baseline (MOSS-010 Compose coverage and MOSS-031 delivery REST).

## Commands

```sh
cd api
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run ruff check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run ruff format --check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run ruff check --config pyproject.toml ../ci/telemetry_smoke.py
uv run ruff format --check --config pyproject.toml ../ci/telemetry_smoke.py
uv run mypy app
python3 ../scripts/check_dependabot.py
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres"
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres \
  MOSS_TEST_DATABASE_URL='postgresql+psycopg://ubuntu@/ubuntu' \
  uv run pytest
uv run python tests/verify_required_runs.py

cd web && npm run check && npm test && npm run build && npm audit --audit-level=high
cd example-site && npm run check && npm test && npm run build && npm audit --audit-level=high
cd ci && npm audit --audit-level=high

docker run --rm -d --name moss-otel-smoke \
  -p 127.0.0.1:14318:4318 -p 127.0.0.1:19464:9464 \
  -v "$PWD/ops/otel-collector.yaml:/etc/otelcol/config.yaml:ro" \
  otel/opentelemetry-collector-contrib:0.156.0@sha256:125bdbeb7590cc1952c5b3430ecf14063568980c2c93d5b38676cc0446ed8108 \
  --config=/etc/otelcol/config.yaml
cd api && MOSS_USE_SQLITE=false PYTHONPATH=. uv run python ../ci/telemetry_smoke.py \
  --endpoint http://127.0.0.1:14318 --metrics-url http://127.0.0.1:19464/metrics \
  --output /tmp/moss-otel-evidence/collector-smoke.json

docker build --tag mosscms:smoke .
sudo iptables-legacy -P FORWARD ACCEPT
docker compose -f ci/compose.yaml -p mosscms-smoke up --no-build -d --wait --wait-timeout 180
cd ci && npm test
docker compose -f ci/compose.yaml -p mosscms-smoke down --volumes
```

`iptables-legacy` FORWARD was already ACCEPT before this run. Setting it again did not change the policy. That is a host setting, not a repository change.

## Results

| Command | Exit | Result |
| --- | --- | --- |
| `ruff check app tests migrations` | 0 | all checks passed |
| `ruff format --check app tests migrations` | 0 | 85 files already formatted |
| ruff check of scripts and example-site setup | 0 | all checks passed |
| ruff format check of those files | 0 | 15 files already formatted |
| ruff check of `ci/telemetry_smoke.py` | 0 | all checks passed |
| ruff format check of that file | 0 | 1 file already formatted |
| `mypy app` | 0 | no issues in 28 source files |
| `scripts/check_dependabot.py` | 0 | schema valid; uv `/api`, npm `/web` `/example-site` `/ci`, github-actions `/`, docker `/` and `/example-site` |
| SQLite required run | 0 | 433 collected, 429 passed, 4 deselected, 0 skipped, 6 warnings in 82.15s |
| PostgreSQL required run | 0 | 433 collected, 433 passed, 0 deselected, 0 skipped, 6 warnings in 99.73s |
| `tests/verify_required_runs.py` | 0 | `"ok": true` |
| web check, test, build, `npm audit --audit-level=high` | 0 | 35 files, 317 passed; build succeeded; `found 0 vulnerabilities` |
| example-site check, test, build, `npm audit --audit-level=high` | 0 | 46 passed, 0 failed, 0 skipped; build succeeded; `found 0 vulnerabilities` |
| `ci` `npm audit --audit-level=high` | 0 | `found 0 vulnerabilities` |
| OTLP collector smoke | 0 | evidence written, container removed |
| `docker build --tag mosscms:smoke .` | 0 | image `mosscms:smoke` |
| `compose up --wait` | 0 | app and database healthy |
| `ci` `npm test` | 0 | 2 passed (2.7s) |
| `compose down --volumes` | 0 | stack removed |

Both required runs recorded `"skipped": 0`. The four SQLite deselections are the PostgreSQL-only ids already committed in `api/tests/required_runs.json`, and the PostgreSQL run passed them. No xfail.

Logs: [api.txt](5d6aff6/api.txt), [web.txt](5d6aff6/web.txt), [example-site.txt](5d6aff6/example-site.txt), [otel.txt](5d6aff6/otel.txt), [image.txt](5d6aff6/image.txt), [ci-audit.txt](5d6aff6/ci-audit.txt).
