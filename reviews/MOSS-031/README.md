# MOSS-031 REST delivery entry reads

local

Recorded 29 October 2026 (UTC). The suite below ran against `c62ec2c61f9fe60f56cf93df55d4486e3fccf471` with a clean working tree. This evidence commit only adds the run record.

## Code under test

| | |
| --- | --- |
| SHA tested | `c62ec2c61f9fe60f56cf93df55d4486e3fccf471` |
| Branch | `cursor/rest-delivery-entries-dc8d` |
| Parent | `fd1f0b0c953f1bf77bdca4903c660af72f33342e` (main, MOSS-030) |
| Baseline | `3a87c73c8e925973608e373863813163b41f04a9` |
| `git status --porcelain` at the start of this run | empty (clean) |
| Date | 2026-10-29T04:48:16Z through 2026-10-29T04:52:00Z |
| Node / npm | v22.23.4 / 10.9.9 |
| Python / uv | 3.12.3 / 0.12.23 |
| PostgreSQL | 16.15 on 127.0.0.1:5432, role `moss` (local trust) |
| Docker Compose | 2.40.3 (client only; `docker compose config` does not need the daemon) |

`c62ec2c` adds `GET`/`HEAD` `/delivery` routes for types, entries, resolved assets, redirects, and reserved paths. They call `identify(..., delivery=True)`, `require`, `public_fields` / `public_data`, `entry_page`, `get_entry`, and `resolved_image_assets` unchanged. The GraphQL ETag block is the shared `delivery_representation` helper. `MAX_FILTERS_BYTES = 4096` is the raw `filters` query-parameter length, counted before URL-decoding and before `parse_filters`. The design status line is `approved by CTO (Oct 29, 2026)`.

## Commands

No `-k`, `--ignore`, new skips, or xfails. Working directory notes are in the command. `npm ci` installed `web`, `example-site`, and `ci` from their lockfiles before the audits.

```sh
cd api
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run ruff check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py ../ci/telemetry_smoke.py
uv run ruff format --check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py ../ci/telemetry_smoke.py
uv run mypy app
MOSS_USE_SQLITE=false uv run pytest -ra --tb=line
MOSS_USE_SQLITE=false MOSS_TEST_DATABASE_URL='postgresql+psycopg://moss@127.0.0.1:5432/moss' uv run pytest -ra --tb=line
uv export --frozen --all-groups --no-emit-project -o /tmp/moss-031-requirements.txt
uv run --with pip-audit pip-audit --progress-spinner off -r /tmp/moss-031-requirements.txt

cd web
npm ci
npm run check
npm test
npm run build
npm audit --audit-level=high
npm audit

cd example-site
npm ci
npm run check
npm test
npm run build
npm audit --audit-level=high
npm audit

cd ci
npm ci
npm audit --audit-level=high
npm audit
```

`pip-audit` had no ignore, allowlist, or override. The ephemeral audit environment needed the distro `python3.12-venv` package so `uv run --with` could create it. That package is not part of the repo.

## Results

| Command | Exit | Result |
| --- | --- | --- |
| ruff check app, tests, migrations | 0 | all checks passed |
| ruff format check of those files | 0 | 81 files already formatted |
| ruff check scripts, example-site setup, telemetry smoke | 0 | all checks passed |
| ruff format check of those files | 0 | 15 files already formatted |
| `uv run mypy app` | 0 | no issues in 28 source files |
| SQLite `pytest -ra --tb=line` | 0 | 407 passed, 4 skipped, 6 warnings in 66.63s |
| PostgreSQL `pytest -ra --tb=line` | 0 | 411 passed, 6 warnings in 96.20s |
| `pip-audit` | 0 | No known vulnerabilities found |
| `cd web && npm run check` | 0 | `tsc -b` |
| `cd web && npm test` | 0 | 35 files, 317 tests passed |
| `cd web && npm run build` | 0 | vite build succeeded |
| `cd web && npm audit` and `--audit-level=high` | 0 | found 0 vulnerabilities |
| `cd example-site && npm run check` | 0 | `tsc --noEmit` |
| `cd example-site && npm test` | 0 | 46 passed, 0 failed, 0 skipped |
| `cd example-site && npm run build` | 0 | vite build succeeded |
| `cd example-site && npm audit` and `--audit-level=high` | 0 | found 0 vulnerabilities |
| `cd ci && npm audit` and `--audit-level=high` | 0 | found 0 vulnerabilities |

SQLite skipped the four PostgreSQL-only tests that already skip on main and pass on PostgreSQL: `test_postgres_workers_skip_locked_rows_and_claim_once`, `test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`, `test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`, and `test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`. The PostgreSQL run executed the whole suite: 411 passed, 0 skipped. No xfail.

Against `3a87c73` (398 passed / 4 skipped on SQLite, 402 passed on PostgreSQL) this run is +9 API tests, which are the nine tests in `api/tests/test_delivery_rest.py`. Web stayed at 317. The example site stayed at 46.

Logs: [pytest-sqlite.txt](c62ec2c/pytest-sqlite.txt), [pytest-postgres.txt](c62ec2c/pytest-postgres.txt), [lint.txt](c62ec2c/lint.txt), [web.txt](c62ec2c/web.txt), [example-site.txt](c62ec2c/example-site.txt), [pip-audit.txt](c62ec2c/pip-audit.txt), [ci-npm-audit.txt](c62ec2c/ci-npm-audit.txt).

## Mutation checks

Each guard was removed or switched on the `c62ec2c` tree, the focused test was run, and the source was restored before the suite above. All three mutated runs exited 1. The restored tree is the tree that was tested.

1. Session-cookie guard. In `identify`, the delivery kind check was removed so any unexpired token was accepted:

```diff
-    if not token or token.expires_at <= now() or token.kind != ("delivery" if delivery else "session"):
+    if not token or token.expires_at <= now():
```

`test_session_cookie_without_bearer_is_401_on_every_delivery_rest_get` still authenticated `/auth/me` and `/api/tokens` with the `moss_session` cookie, then failed on the first discovered delivery GET: `assert 403 == 401`. Log: [cookie-kind-check.txt](c62ec2c/mutations/cookie-kind-check.txt).

2. Filters size guard. These two lines were deleted from `load_filters`:

```diff
-    if filters_measured_length(raw) > MAX_FILTERS_BYTES:
-        raise CmsError("Filters value is too long.")
```

A 4097-byte `filters` value then returned 200, and the `parse_filters` spy recorded the value. `test_filters_limit_uses_raw_bytes_before_decoding_and_parsing` failed: `assert 200 == 422`. Log: [filters-remove-check.txt](c62ec2c/mutations/filters-remove-check.txt).

3. Raw versus decoded length. `filters_measured_length` was switched to the decoded size:

```diff
-    return len(raw)
+    return len(urllib.parse.unquote_to_bytes(raw))
```

The 4096-byte and 4097-byte unencoded values still behaved (the failure is later in the same test). A value of 4098 raw bytes that decodes to 1366 bytes returned 200 instead of 422. Log: [filters-decoded-length.txt](c62ec2c/mutations/filters-decoded-length.txt).
