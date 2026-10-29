# MOSS-031 REST delivery entry reads

local

Recorded 29 October 2026 (UTC). The API required runs below executed against `20cedbe307318e7dbabf0ee87e68f02a4228b16f` with a clean working tree. This evidence commit only updates the run record.

## Code under test

| | |
| --- | --- |
| SHA tested | `20cedbe307318e7dbabf0ee87e68f02a4228b16f` |
| Branch | `cursor/rest-delivery-entries-dc8d` |
| Parent | `2d4c6082d308c638c981a3ed6a26f02142ac2532` (main, MOSS-045) |
| Baseline | `3a87c73c8e925973608e373863813163b41f04a9` |
| Main required-run baseline | `d50e2788485e4ef0c65598c4c2f2bd7536e1ed96` (MOSS-023/024): collected 403, SQLite 399 passed / 4 deselected / 0 skipped, PostgreSQL 403 passed / 0 skipped |
| `git status --porcelain` at the start of the API rerun | empty (clean) |
| API rerun | 2026-10-29T05:06:10Z through 2026-10-29T05:08:28Z |
| Earlier checks on the same application bytes | 2026-10-29T04:55:50Z through 2026-10-29T05:03:15Z |
| Python / uv | 3.12.3 / 0.12.23 |
| ruff / mypy / pip-audit | 0.16.10 / 2.4.0 / 2.10.1 |
| Node / npm | v22.23.4 / 10.9.9 |
| PostgreSQL required run | 17.11, `postgres:17-alpine`, `127.0.0.1:5433`, role `pg`, database `postgres` |
| Docker / Compose | 29.1.3 / 2.40.3 |

`20cedbe` adds `GET`/`HEAD` `/delivery` routes for types, entries, resolved assets, redirects, and reserved paths. They call `identify(..., delivery=True)`, `require`, `public_fields` / `public_data`, `entry_page`, `get_entry`, and `resolved_image_assets` unchanged. The GraphQL ETag block is the shared `delivery_representation` helper. `MAX_FILTERS_BYTES = 4096` is the raw `filters` query-parameter length, counted before URL-decoding and before `parse_filters`. The design status line is `approved by CTO (Oct 29, 2026)`.

The checkout during the API rerun was `7da1dc5`, which adds only `reviews/MOSS-031` on top of `20cedbe`. No application, test, lockfile, or workflow file differs. Lint, web, example-site, audits, OTLP, production Docker, and the mutation checks ran on that same application source before a documentation-only rebase onto `2d4c608`. `git diff` of `api`, `web`, `example-site`, `ci`, `docs`, and `.github` between that source and `20cedbe` is empty.

## Commands

No `-k`, `--ignore`, new skips, or xfails. A runtime skip or xfail fails the API required runs. PostgreSQL-only tests use the `postgres` marker and are excluded from the SQLite required run with `-m "not postgres"`. Compose tests ran in both required runs. `npm ci` had already installed `web`, `example-site`, and `ci` from their lockfiles.

```sh
cd api
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run ruff check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run ruff format --check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run ruff check --config pyproject.toml ../ci/telemetry_smoke.py
uv run ruff format --check --config pyproject.toml ../ci/telemetry_smoke.py
uv run mypy app
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres" -ra --tb=line
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres \
  MOSS_TEST_DATABASE_URL='postgresql+psycopg://pg:pgtestpw@127.0.0.1:5433/postgres' \
  uv run pytest -ra --tb=line
uv run python tests/verify_required_runs.py
uv export --frozen --all-groups --no-emit-project -o /tmp/moss-031-evidence/requirements.txt
uv run --with pip-audit pip-audit --progress-spinner off -r /tmp/moss-031-evidence/requirements.txt

cd web
npm run check && npm test && npm run build && npm audit --audit-level=high
npm audit

cd example-site
npm run check && npm test && npm run build && npm audit --audit-level=high
npm audit

cd ci
npm audit --audit-level=high
npm audit
npx playwright install --with-deps chromium
docker build --tag mosscms:smoke .
docker compose -f ci/compose.yaml -p mosscms-smoke up --no-build -d --wait --wait-timeout 180
npm test
docker compose -f ci/compose.yaml -p mosscms-smoke down --volumes
```

The OTLP step used the pinned image `otel/opentelemetry-collector-contrib:0.156.0` and `ops/otel-collector.yaml`, then `ci/telemetry_smoke.py`. `pip-audit` had no ignore, allowlist, or override. The host `iptables-legacy` FORWARD policy was `DROP`; it was set to `ACCEPT` so the Compose bridge could reach Postgres. That change is not in the repository.

## Results

| Command | Exit | Result |
| --- | --- | --- |
| ruff check app, tests, migrations | 0 | all checks passed |
| ruff format check of those files | 0 | 84 files already formatted |
| ruff check scripts, example-site setup, telemetry smoke | 0 | all checks passed |
| ruff format check of those files | 0 | 14 files and 1 file already formatted |
| `uv run mypy app` | 0 | no issues in 28 source files |
| SQLite required run | 0 | collected 412, **408 passed, 4 deselected, 0 skipped**, 6 warnings in 57.94s |
| PostgreSQL 17 required run | 0 | collected 412, **412 passed, 0 deselected, 0 skipped**, 6 warnings in 123.49s |
| `tests/verify_required_runs.py` | 0 | union of passed ids is 412 |
| `pip-audit` 2.10.1 | 0 | No known vulnerabilities found |
| `cd web && npm run check` | 0 | `tsc -b` |
| `cd web && npm test` | 0 | 35 files, 317 tests passed |
| `cd web && npm run build` | 0 | vite build succeeded |
| `cd web && npm audit` and `--audit-level=high` | 0 | found 0 vulnerabilities |
| `cd example-site && npm run check` | 0 | `tsc --noEmit` |
| `cd example-site && npm test` | 0 | 46 passed, 0 failed, 0 skipped |
| `cd example-site && npm run build` | 0 | vite build succeeded |
| `cd example-site && npm audit` and `--audit-level=high` | 0 | found 0 vulnerabilities |
| `cd ci && npm audit` and `--audit-level=high` | 0 | found 0 vulnerabilities |
| OTLP collector smoke | 0 | metrics ready, container removed |
| `npx playwright install --with-deps chromium` | 0 | Chromium headless shell installed |
| `docker build --tag mosscms:smoke .` | 0 | image `mosscms:smoke` built |
| `compose up --wait` | 0 | app healthy |
| `cd ci && npm test` | 0 | 2 passed in 2.9s |
| `compose down --volumes` | 0 | stack removed |

The four ids deselected on SQLite are the committed list in `api/tests/required_runs.json`. No xfail. `tests/test_compose.py` executed in both required runs.

Against `3a87c73` (398 passed / 4 skipped on SQLite, 402 passed on PostgreSQL) this run is above the baseline. Against the MOSS-024 required-run counts (399 / 403) this run is +9 API tests, the nine tests in `api/tests/test_delivery_rest.py`. Web stayed at 317. The example site stayed at 46.

Logs: [pytest-sqlite.txt](20cedbe/pytest-sqlite.txt), [pytest-postgres.txt](20cedbe/pytest-postgres.txt), [verify.txt](20cedbe/verify.txt), [lint.txt](20cedbe/lint.txt), [web.txt](20cedbe/web.txt), [example-site.txt](20cedbe/example-site.txt), [pip-audit.txt](20cedbe/pip-audit.txt), [ci-npm-audit.txt](20cedbe/ci-npm-audit.txt), [otel.txt](20cedbe/otel.txt), [docker-build.txt](20cedbe/docker-build.txt), [playwright-install.txt](20cedbe/playwright-install.txt), [compose-up.txt](20cedbe/compose-up.txt), [production-playwright.txt](20cedbe/production-playwright.txt), [compose-down.txt](20cedbe/compose-down.txt).

## Mutation checks

Each guard was removed or switched on this source, the focused test was run, and the source was restored before the API required runs above. All three mutated runs exited 1. The restored tree is the tree that was tested (`filters_measured_length` returns `len(raw)`; the delivery kind check is present).

1. Session-cookie guard. In `identify`, the delivery kind check was removed so any unexpired token was accepted:

```diff
-    if not token or token.expires_at <= now() or token.kind != ("delivery" if delivery else "session"):
+    if not token or token.expires_at <= now():
```

`test_session_cookie_without_bearer_is_401_on_every_delivery_rest_get` still authenticated `/auth/me` and `/api/tokens` with the `moss_session` cookie, then failed on the first discovered delivery GET: `assert 403 == 401` at `tests/test_delivery_rest.py:274`. Log: [cookie-kind-check.txt](20cedbe/mutations/cookie-kind-check.txt).

2. Filters size guard. These two lines were deleted from `load_filters`:

```diff
-    if filters_measured_length(raw) > MAX_FILTERS_BYTES:
-        raise CmsError("Filters value is too long.")
```

A 4097-byte `filters` value then returned 200, and the `parse_filters` spy recorded the value. `test_filters_limit_uses_raw_bytes_before_decoding_and_parsing` failed at `tests/test_delivery_rest.py:323`: `assert 200 == 422`. Log: [filters-remove-check.txt](20cedbe/mutations/filters-remove-check.txt).

3. Raw versus decoded length. `filters_measured_length` was switched to the decoded size:

```diff
-    return len(raw)
+    return len(urllib.parse.unquote_to_bytes(raw))
```

The 4096-byte and 4097-byte unencoded values still behaved. A value of 4098 raw bytes that decodes to 1366 bytes returned 200 instead of 422. The test failed at `tests/test_delivery_rest.py:333`: `assert 200 == 422`, body `{"nodes":[],"endCursor":null,"hasNextPage":false}`. Log: [filters-decoded-length.txt](20cedbe/mutations/filters-decoded-length.txt).
