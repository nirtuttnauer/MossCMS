# MOSS-033 REST authorization and isolation

local

Recorded 29 October 2026 (UTC). The API required runs below executed against `2ba3f42cee8c7ef9960d63cdc995e9d8ffd6bfac` with a clean working tree. This evidence commit only updates the run record.

## Code under test

| | |
| --- | --- |
| SHA tested | `2ba3f42cee8c7ef9960d63cdc995e9d8ffd6bfac` |
| Branch | `cursor/moss-033-rest-auth-e689` |
| Parent | `28c3dc969c4d5d36a6aa08c4f0103a5b512cd03a` (main, after MOSS-026 / MOSS-056) |
| Baseline in the ticket | `3a87c73c8e925973608e373863813163b41f04a9` |
| Previous main required run | `28c3dc9`: collected 433, SQLite 429 passed / 4 deselected / 0 skipped, PostgreSQL 433 passed / 0 skipped |
| `git status --porcelain` at the start of the API run | empty (clean) |
| API run | 2026-10-29T05:32:31Z through 2026-10-29T05:35:41Z |
| Web and example-site run | 2026-10-29T05:31:14Z. `git diff 1a005f2 HEAD -- web example-site` is empty, so those trees match this SHA |
| Python / uv | 3.12.3 / 0.13.6 |
| ruff | 0.16.10 |
| Node / npm | v22.23.4 / 10.9.9 |
| PostgreSQL | 16.15, role `ubuntu`, local socket, database `postgres` |
| Docker / Compose | 27.5.1 / 2.40.3 (compose tests ran) |

`2ba3f42` adds `api/tests/test_delivery_authorization.py`. It does not change application code. The new tests are collected in both required runs: no `postgres` marker and no runtime skip.

Every `GET` and `HEAD` delivery route registered on the app is checked. The route set is `/delivery/types`, `/delivery/types/{typeKey}`, `/delivery/entries`, `/delivery/entries/{id}`, `/delivery/entries/{id}/resolved-assets`, `/delivery/website/redirects`, and `/delivery/website/reserved-paths`.

- Unauthenticated calls, session cookies, session bearers for admin, reader, and editor, an expired delivery token, a revoked delivery token, a garbage bearer, an empty bearer, a raw token without the `Bearer` scheme, and the same delivery secret in `token`, `access_token`, and `moss_session` query parameters are HTTP 401 `{"detail": "A valid delivery token is required."}` with `Cache-Control: no-store` and no `ETag`.
- A delivery token from another project, including when `X-Moss-Project` names the other workspace, cannot read that workspace's types, entries, resolved assets, redirects, or reserved paths.
- A delivery token scoped to another content type is unprivileged for article and website routes: those types, entries, and paths are omitted or 404.
- Draft-only, scheduled-only, trashed, and unpublished entries stay 404 for every live delivery token (empty scope, named scope, other-project scope). A live entry with a later draft and a pending schedule still returns the published snapshot. `status`, `snapshot`, and `scheduledAt` query parameters stay rejected and do not reveal those rows. `MOSS_SKIP_AUTH` still requires a delivery token on every route.

## Commands

No `-k`, `--ignore`, new skips, or xfails. A runtime skip or xfail fails the API required runs. PostgreSQL-only tests use the `postgres` marker and are excluded from the SQLite required run with `-m "not postgres"`. Compose tests ran in both required runs. `npm ci` installed `web` and `example-site` from their lockfiles.

```sh
cd api
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
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
| ruff format check of those files | 0 | 86 files already formatted |
| SQLite required run | 0 | collected 437, **433 passed, 4 deselected, 0 skipped**, 6 warnings in 66.41s |
| PostgreSQL 16 required run | 0 | collected 437, **437 passed, 0 deselected, 0 skipped**, 6 warnings in 99.84s |
| `tests/verify_required_runs.py` | 0 | union of passed ids is 437 |
| `cd web && npm run check` | 0 | `tsc -b` |
| `cd web && npm test` | 0 | 35 files, 317 tests passed |
| `cd web && npm run build` | 0 | vite build succeeded |
| `cd example-site && npm run check` | 0 | `tsc --noEmit` |
| `cd example-site && npm test` | 0 | 46 passed, 0 failed, 0 skipped |
| `cd example-site && npm run build` | 0 | vite build succeeded |

The four ids deselected on SQLite are the committed list in `api/tests/required_runs.json`. No xfail. `tests/test_compose.py` executed in both required runs.

Against `3a87c73` (398 passed / 4 skipped on SQLite, 402 passed on PostgreSQL) this run is above the baseline. Against main at `28c3dc9` (429 / 433) this run adds the four tests in `api/tests/test_delivery_authorization.py`. No new skip or failure. Web stayed at 317. The example site stayed at 46.

Logs: [pytest-sqlite.txt](2ba3f42/pytest-sqlite.txt), [pytest-postgres.txt](2ba3f42/pytest-postgres.txt), [verify.txt](2ba3f42/verify.txt), [ruff-check.txt](2ba3f42/ruff-check.txt), [ruff-format.txt](2ba3f42/ruff-format.txt), [web.txt](2ba3f42/web.txt), [example-site.txt](2ba3f42/example-site.txt), [toolchain.txt](2ba3f42/toolchain.txt).
