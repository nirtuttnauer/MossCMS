# MOSS-010 local Compose image

local

Recorded 29 October 2026 (UTC). Option A: Compose builds the app image from this checkout. Nothing was published, and no registry credential was added. A runtime skip or xfail fails the API required runs. There is no allowed-skip list. PostgreSQL-only tests use the `postgres` marker and are excluded from the SQLite required run with `-m "not postgres"` before they execute. Compose tests use the `compose` marker and ran in both required runs.

## Code under test

| | |
| --- | --- |
| SHA tested | `853363af4d744f4b2bd0504c4c1eb1b04a0c6a08` |
| Rebased code commit | `1b26f0fb07617e5d55303df2d25441281347f0d5` on `2d4c608` (main, after MOSS-045). `git diff 853363a 1b26f0f` is empty for `compose.yaml`, `compose.database.true.yaml`, `.env.example`, `docs/docker.md`, `docs/deployment-recovery.md`, and `api/tests/test_compose.py`. README also contains the MOSS-045 sentence that landed on main. |
| Branch | `cursor/moss-010-local-compose-image-13cd` |
| Parent at test time | `a84eebd8c2fea163f60674c5e54ba03a7a2ae573` (main, after MOSS-024) |
| Baseline | `3a87c73c8e925973608e373863813163b41f04a9` |
| Previous main | `a84eebd8c2fea163f60674c5e54ba03a7a2ae573` (same tests as `d50e278`, 403 collected) |
| `git status --porcelain` at the start of this run | empty (clean) |
| Date | 2026-10-29T04:57:54Z through 2026-10-29T05:04:40Z |
| Python / uv | 3.12.3 / 0.12.23 |
| ruff / mypy | 0.16.10 / 2.4.0 |
| Node / npm | v22.23.4 / 10.9.9 |
| PostgreSQL | 17.11, `postgres:17-alpine`, container `moss-010-pg`, `127.0.0.1:5432`, role `pg`, database `postgres` |
| Docker / Compose | 29.9.2 / v5.6.1 |

`853363a` changes `compose.yaml`, `compose.database.true.yaml`, `.env.example`, `README.md`, `docs/docker.md`, `docs/deployment-recovery.md`, and `api/tests/test_compose.py`. The default app image is `mosscms:local` with `pull_policy: build`. The SQLite `db` stub uses that same tag with `pull_policy: never`. A published image is selected only by setting both `MOSS_IMAGE` and `MOSS_PULL_POLICY=missing`.

## README start

```sh
python3 scripts/start.py
```

First run, cold image, `2026-10-29T04:57:54Z` through `2026-10-29T04:59:29Z`. Compose printed `Image mosscms:local Building` and `Image mosscms:local Built`. The log does not contain `nirtuttnauer/mosscms`, `Pulling`, or `pull access denied`. Exit code 1: the app container was unhealthy because this VM's iptables-legacy `FORWARD` policy dropped the Compose bridge. That policy was set to `ACCEPT` on the host only. Full log: [start-first.txt](853363a/start-first.txt).

After that host change, `docker compose up -d --force-recreate --no-build --wait --wait-timeout 180 app` exited 0. `http://127.0.0.1:8001/ready` returned `{"status":"ready"}`.

Second README command, `2026-10-29T05:04:39Z` through `2026-10-29T05:04:40Z`, on the already built image:

| Command | Exit | Result |
| --- | --- | --- |
| `python3 scripts/start.py` | 0 | `Image mosscms:local Building`, app healthy, `MossCMS is ready: http://localhost:8001`. No pull of an app image. The setup token line was redacted before this record was committed. |

Log: [start-ok.txt](853363a/start-ok.txt).

## API, web, and example site

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

cd web
npm run check
npm test
npm run build
npm audit --audit-level=high

cd example-site
npm run check
npm test
npm run build
npm audit --audit-level=high
```

| Command | Exit | Result |
| --- | --- | --- |
| ruff check/format for `app`, `tests`, `migrations` | 0 | all checks passed; 82 files already formatted |
| ruff check/format for scripts, example-site setup, telemetry smoke | 0 | all checks passed; 14 files and 1 file already formatted |
| `uv run mypy app` | 0 | no issues in 27 source files |
| SQLite required run | 0 | 406 collected, **402 passed, 4 deselected, 0 skipped**, 6 warnings in 59.81s |
| PostgreSQL required run | 0 | 406 collected, **406 passed, 0 deselected, 0 skipped**, 6 warnings in 116.68s |
| `tests/verify_required_runs.py` | 0 | union of passed ids is 406 |
| `cd web && npm run check` | 0 | `tsc -b` |
| `cd web && npm test` | 0 | 35 files, 317 tests passed |
| `cd web && npm run build` | 0 | vite build succeeded |
| `cd web && npm audit --audit-level=high` | 0 | 0 vulnerabilities |
| `cd example-site && npm run check` | 0 | `tsc --noEmit` |
| `cd example-site && npm test` | 0 | 46 passed, 0 failed, 0 skipped |
| `cd example-site && npm run build` | 0 | vite build succeeded |
| `cd example-site && npm audit --audit-level=high` | 0 | 0 vulnerabilities |

Baseline on `3a87c73`: 402 collected. Previous main `d50e278` / `a84eebd`: 403 collected (adds `tests/test_required_runs.py`). This run collects 406 because it adds three compose tests. 406 ≥ 403 ≥ 402. No new skip and no xfail.

The four ids deselected on SQLite and passed on PostgreSQL:

- `tests/test_concurrency.py::test_postgres_workers_skip_locked_rows_and_claim_once`
- `tests/test_indexing.py::test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`
- `tests/test_postgres_product_migration.py::test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`
- `tests/test_search.py::test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`

Logs: [api-lint.txt](853363a/api-lint.txt), [pytest-sqlite.txt](853363a/pytest-sqlite.txt), [pytest-postgres.txt](853363a/pytest-postgres.txt), [verify.txt](853363a/verify.txt), [web.txt](853363a/web.txt), [example-site.txt](853363a/example-site.txt).
