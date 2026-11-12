# MOSS-026 rehearsal deploy

Two records, kept apart:

- `rehearsal (Linux VM)` — this virtual machine only. Loopback TLS. No public DNS, no registered domain, no external account, and no hosted deployment.
- `local` — the repository test suite on the same checkout, after the rehearsal.

Source SHA for both: `a84eebd8c2fea163f60674c5e54ba03a7a2ae573` (`main` at the start of the run, MOSS-024). `git status --porcelain` was empty. Ignored rehearsal files (`.env`, `example-site/.env`, TLS keys) stayed out of git.

## rehearsal (Linux VM)

Recorded 29 October 2026 (UTC). Linux VM, Ubuntu 24.04.5, kernel 6.12.94+. Docker 29.1.3, Compose 2.40.3, nginx 1.24.0. The app image was built here with `docker compose up --build`. It was not pulled from a registry. `MOSS_IMAGE=mosscms:local`.

| | |
| --- | --- |
| SHA | `a84eebd8c2fea163f60674c5e54ba03a7a2ae573` |
| `git status --porcelain` | empty |
| Date | 2026-10-29T04:54:59Z through 2026-10-29T05:13:43Z |
| CMS public origin | `https://cms.moss.test:8443` |
| Website public origin | `https://site.moss.test:8444` |
| App bind | `127.0.0.1:8001` |
| Website bind | `127.0.0.1:5174` |
| Database | PostgreSQL 17, Compose service `db`, no published host port |
| Names | `cms.moss.test` and `site.moss.test` resolve only through `/etc/hosts` to `127.0.0.1` |

`.test` is a reserved test name. Nothing was registered in DNS. The TLS certificate is a local leaf for those two names, signed by a CA that exists only on this VM. The private key stayed in `/tmp/moss-026-tls` and is not in this record. Generated passwords, `MOSS_SECRET_KEY`, `MOSS_SETUP_TOKEN`, the delivery token, and `.env` are not in this record.

The Compose bridge could not open TCP to Postgres until this host accepted forwarded packets from that bridge: `iptables-legacy -A DOCKER-FORWARD -i br-a98760564e44 -j ACCEPT`. Legacy `FORWARD` policy is `DROP`, and Docker had written the new bridge rules to iptables-nft. That is a VM firewall adjustment. It is not a repository change.

### Commands

```sh
python3 scripts/configure.py --production --public-url https://cms.moss.test:8443
# .env then also received MOSS_WEBHOOK_ORIGINS=http://example-site:5174 and MOSS_IMAGE=mosscms:local
docker compose up --build -d
docker compose --profile website up --build -d example-site
```

`configure.py` exited 0. Both Compose commands exited 0. Logs: [compose-up.txt](rehearsal/compose-up.txt), [compose-site.txt](rehearsal/compose-site.txt). Process list: [compose-ps.txt](rehearsal/compose-ps.txt). Images: [compose-images.txt](rehearsal/compose-images.txt).

| Image | ID | How it arrived |
| --- | --- | --- |
| `mosscms:local` (first `up --build`) | `sha256:92c68af024ab5bd1395296fd50be08e68c9bea2ea0c0c117b1b70dec5c4c0256` | local build |
| `mosscms:local` (website `up --build` rebuilt the app and recreated the container) | `sha256:cb421c22afa7221689cb5e57ce715d5ad10553e4add5bf7cd84fd4f69b826053` | local build from the same checkout |
| `workspace-example-site:latest` | `sha256:486e913b33b0ce14ae624a564b513770528d5c6905489a3b6357003e8dc5871b` | local build |
| `postgres:17-alpine` | `sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b` | pulled database image |

The website command rebuilt the app from this checkout and recreated the app container. The database volume stayed. Sign-in, publish, schedule, and media ran on the first app container. Example-site delivery ran after the recreate, against the same database.

Non-secret configuration written by `configure.py --production`:

| Key | Value |
| --- | --- |
| `MOSS_ENV` | `production` |
| `MOSS_SKIP_AUTH` | `false` |
| `MOSS_USE_SQLITE` | `false` |
| `MOSS_PUBLIC_URL` | `https://cms.moss.test:8443` |
| `MOSS_ORIGINS` | `https://cms.moss.test:8443` |
| `MOSS_PORT` | `8001` |
| `MOSS_WEBHOOK_ORIGINS` | `http://example-site:5174` |
| `MOSS_IMAGE` | `mosscms:local` |

### TLS proxy

nginx listens on `127.0.0.1:8443` (CMS) and `127.0.0.1:8444` (website) and forwards to the loopback app ports. Config: [nginx.conf](rehearsal/nginx.conf). `nginx -t` succeeded. `/api/events` has `proxy_buffering off`. `/api/preview` and `/preview` are not cached. The access log records method, path, and status, and does not record cookies, authorization, or bodies.

Response headers seen by the client on `GET https://cms.moss.test:8443/ready` at 2026-10-29T05:13:43Z ([ready.headers](rehearsal/ready.headers)):

| Header | Value |
| --- | --- |
| status | `200` `{"status":"ready"}` |
| `x-request-id` | present |
| `server-timing` | `app;dur=3.0` |
| `x-content-type-options` | `nosniff` |
| `referrer-policy` | `same-origin` |
| `x-frame-options` | `DENY` |
| `strict-transport-security` | `max-age=300` (set by the TLS proxy) |

`GET https://site.moss.test:8444/api/events` returned `200`, `content-type: text/event-stream`, `x-accel-buffering: no`, and `cache-control: no-cache`. The stream stayed open until the client timed out, which is what an unbuffered event stream does.

### Checks

A local administrator was created with `/auth/setup`, then signed out and signed in with `/auth/login`. The password and setup token are not recorded. Workspace and entry ids below are the rows created on this VM.

| Check | Result |
| --- | --- |
| `/ready` through TLS | `200` `{"status":"ready"}` |
| `/auth/status` before setup | `initialized: false`, `authSkipped: false` |
| setup | `200`, then logout `200`, then `/auth/me` `401` |
| sign-in | `200`, email `rehearsal-admin@example.com`, role `admin`, workspace `Rehearsal workspace` (`238c3975-172e-4e4e-876d-85c02a2da241`) |
| publish | `note` / `linux-vm-rehearsal`, `isLive: true`, revision 1, id `1a889c0e-4bc6-4da0-ae55-989c750c3315` |
| delivery API | scoped token read that live slug and title `Linux VM rehearsal` |
| scheduled publish | due `2026-10-29T05:00:56.773602+00:00`; observed live at `2026-10-29T05:00:59.934162+00:00`, slug `scheduled-rehearsal`, title `Scheduled rehearsal` |
| media | local PNG 800×400, variants 320, 640, and 800; variant fetched through the TLS origin as `image/webp` (172 bytes). Files in the `moss_assets` volume: original plus `.320.webp`, `.640.webp`, `.800.webp` |
| example-site setup | exit 0, workspace `ce24f4c7-1fd0-4f74-96b0-1eb3afd867b8`, `SITE_PUBLIC_URL=https://site.moss.test:8444` |
| delivery read | `GET https://site.moss.test:8444/blog/linux-vm-note` `200`, title `Linux VM note — site.moss.test`. Starter post `/blog/building-this-space` `200` |
| scheduled post on the site | `sitePost` `scheduled-site-note` saved as `scheduled` with a due time eight seconds ahead. The first public GET was `404`. `GET` at `2026-10-29T05:03:16Z` was `200`, title `Scheduled site note — site.moss.test` |

Machine-readable check summary: [checks.json](rehearsal/checks.json). Later header captures: [site-note.headers](rehearsal/site-note.headers), [site-scheduled.headers](rehearsal/site-scheduled.headers).

After the scheduler ran, both scheduled slugs were `published` with `scheduled_at` empty, which is the stored state once publication has happened.

## local

Recorded 29 October 2026 (UTC). Same SHA, still a clean `git status --porcelain`. This section is the test suite. It is separate from the rehearsal above.

| | |
| --- | --- |
| SHA tested | `a84eebd8c2fea163f60674c5e54ba03a7a2ae573` |
| Baseline | `3a87c73c8e925973608e373863813163b41f04a9` |
| Previous main suite | `d50e2788485e4ef0c65598c4c2f2bd7536e1ed96` (MOSS-024; `a84eebd` only adds that evidence commit) |
| `git status --porcelain` at the start | empty |
| Date | 2026-10-29T05:04:13Z through 2026-10-29T05:12:56Z |
| Python / uv | 3.12.3 / 0.12.23 |
| ruff / mypy / pip-audit | 0.16.10 / 2.4.0 / 2.10.1 |
| Node / npm | v22.23.4 / 10.9.9 |
| PostgreSQL for the API run | 17-alpine, `127.0.0.1:5432`, role `pg`, database `postgres`, container `moss-026-pg` |
| Docker Compose | 2.40.3 (compose config tests ran) |

`app.main` calls `load_dotenv()`, which walks up to the repository root. The gitignored rehearsal `.env` would have set `MOSS_ENV=production` and failed import (`Production SQLite requires MOSS_USE_SQLITE=true` when `POSTGRES_HOST` is unset). Both ignored env files were moved out of the tree before the commands below and restored afterward. `git status --porcelain` stayed empty because those paths are ignored. `UV_NO_ENV_FILE=1` was set for `uv run`.

Expected counts, collected at 2026-10-29T05:05:41Z with `required_runs.collect_full_suite()` before the PostgreSQL run finished (SQLite was already in progress). `check_manifest` reported no problems. [expected-before-run.json](a84eebd/expected-before-run.json).

| Run | Collected | Deselected by marker | Expected passed | Runtime skips |
| --- | --- | --- | --- | --- |
| SQLite `-m "not postgres"` | 403 | 4 | 399 | 0 |
| PostgreSQL, no marker filter | 403 | 0 | 403 | 0 |

The four ids deselected on SQLite are the committed PostgreSQL-only tests:

- `tests/test_concurrency.py::test_postgres_workers_skip_locked_rows_and_claim_once`
- `tests/test_indexing.py::test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`
- `tests/test_postgres_product_migration.py::test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`
- `tests/test_search.py::test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`

Baseline `3a87c73`: 402 collected, SQLite 398 passed and 4 runtime skips, PostgreSQL 402 passed. This tree collects 403. 403 ≥ 402. The added test file, `tests/test_required_runs.py`, was already on `main` before this ticket. This run adds no tests, skips, or xfails.

### Commands and results

Working directory `api` unless noted. No `-k`, `--ignore`, new skips, or xfails.

```sh
uv sync --locked --group dev
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run ruff check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run ruff format --check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run ruff check --config pyproject.toml ../ci/telemetry_smoke.py
uv run ruff format --check --config pyproject.toml ../ci/telemetry_smoke.py
uv run mypy app
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -ra --tb=line -m "not postgres"
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres \
  MOSS_TEST_DATABASE_URL='postgresql+psycopg://pg:pgtestpw@127.0.0.1:5432/postgres' \
  uv run pytest -ra --tb=line
uv run python tests/verify_required_runs.py
```

| Command | Exit | Result |
| --- | --- | --- |
| `uv sync --locked --group dev` | 0 | locked deps installed, Pillow 13.0.0 |
| `ruff check app tests migrations` | 0 | all checks passed |
| `ruff format --check app tests migrations` | 0 | 82 files already formatted |
| ruff check scripts and example-site setup | 0 | all checks passed |
| ruff format check of those files | 0 | 14 files already formatted |
| ruff check `ci/telemetry_smoke.py` | 0 | all checks passed |
| ruff format check of that file | 0 | 1 file already formatted |
| `mypy app` | 0 | no issues in 27 source files |
| SQLite required run | 0 | collected 403, **399 passed, 4 deselected, 0 skipped**, 6 warnings in 61.44s |
| PostgreSQL required run | 0 | collected 403, **403 passed, 0 deselected, 0 skipped**, 6 warnings in 120.97s |
| `tests/verify_required_runs.py` | 0 | union of passed ids is 403 |

Logs: [ruff-check.txt](a84eebd/ruff-check.txt), [ruff-format.txt](a84eebd/ruff-format.txt), [ruff-scripts.txt](a84eebd/ruff-scripts.txt), [ruff-scripts-format.txt](a84eebd/ruff-scripts-format.txt), [ruff-telemetry.txt](a84eebd/ruff-telemetry.txt), [ruff-telemetry-format.txt](a84eebd/ruff-telemetry-format.txt), [mypy.txt](a84eebd/mypy.txt), [pytest-sqlite.txt](a84eebd/pytest-sqlite.txt), [pytest-postgres.txt](a84eebd/pytest-postgres.txt), [verify.txt](a84eebd/verify.txt).

### OTLP smoke

Same Collector invocation as `.github/workflows/checks.yml`. Exit 0. The container was removed afterward.

Log: [otel.txt](a84eebd/otel.txt). Evidence: [collector-smoke.json](a84eebd/collector-smoke.json).

### pip-audit

No `--ignore-vuln`, allowlist, or audit exception. The first `uv run --with pip-audit` failed because `python3.12-venv` was absent (`ensurepip is not available`). After `apt install python3.12-venv`, the same command exited 0. `pip-audit` 2.10.1 printed `No known vulnerabilities found`.

```sh
cd api
uv export --frozen --all-groups --no-emit-project -o /tmp/moss-026-local/requirements.txt
uv run --with pip-audit pip-audit --progress-spinner off -r /tmp/moss-026-local/requirements.txt
```

| Command | Exit | Result |
| --- | --- | --- |
| `uv export --frozen` | 0 | requirements written outside the repo |
| `pip-audit` | 0 | No known vulnerabilities found |

Log: [pip-audit.txt](a84eebd/pip-audit.txt).

### Web and example-site

`npm ci` exited 0 in `web` and `example-site` (0 vulnerabilities during install).

```sh
cd web && npm run check && npm test && npm run build && npm audit --audit-level=high && npm audit
cd example-site && npm run check && npm test && npm run build && npm audit --audit-level=high && npm audit
cd ci && npm audit
```

| Command | Exit | Result |
| --- | --- | --- |
| web `npm run check` | 0 | `tsc -b` |
| web `npm test` | 0 | 35 files, 317 tests passed |
| web `npm run build` | 0 | vite build succeeded |
| web `npm audit` and `--audit-level=high` | 0 | 0 vulnerabilities |
| example-site `npm run check` | 0 | `tsc --noEmit` |
| example-site `npm test` | 0 | 46 passed, 0 failed, 0 skipped |
| example-site `npm run build` | 0 | vite build succeeded |
| example-site `npm audit` and `--audit-level=high` | 0 | 0 vulnerabilities |
| ci `npm audit` | 0 | 0 vulnerabilities |

Logs: [web-check.txt](a84eebd/web-check.txt), [web-test.txt](a84eebd/web-test.txt), [web-build.txt](a84eebd/web-build.txt), [web-audit.txt](a84eebd/web-audit.txt), [web-audit-high.txt](a84eebd/web-audit-high.txt), [example-site-check.txt](a84eebd/example-site-check.txt), [example-site-test.txt](a84eebd/example-site-test.txt), [example-site-build.txt](a84eebd/example-site-build.txt), [example-site-audit.txt](a84eebd/example-site-audit.txt), [example-site-audit-high.txt](a84eebd/example-site-audit-high.txt), [ci-audit.txt](a84eebd/ci-audit.txt).

## local, after merging main

`main` moved while this record was open (MOSS-010, MOSS-031, MOSS-045). Those commits were merged into this branch as `e991dd2bc22c7e7efae64b0c74031a241fd536ac`. The rehearsal above stays the `a84eebd` deploy. This section is the suite on the merged tree, still labeled `local`.

| | |
| --- | --- |
| SHA tested | `e991dd2bc22c7e7efae64b0c74031a241fd536ac` |
| `git status --porcelain` | empty |
| Date | 2026-10-29T05:15:55Z through 2026-10-29T05:20Z |
| Compared with | `3a87c73` (402 collected) and the MOSS-031 run on `1a005f2` (415 collected) |

The gitignored rehearsal `.env` files were moved aside for the same `load_dotenv()` reason, then restored. `UV_NO_ENV_FILE=1`.

| Command | Exit | Result |
| --- | --- | --- |
| ruff check app, tests, migrations | 0 | all checks passed |
| ruff format check | 0 | 84 files already formatted |
| ruff check/format scripts, setup, telemetry smoke | 0 | all checks passed |
| `mypy app` | 0 | no issues in 28 source files |
| SQLite required run | 0 | collected 415, **411 passed, 4 deselected, 0 skipped**, 6 warnings in 74.93s |
| PostgreSQL required run | 0 | collected 415, **415 passed, 0 skipped**, 6 warnings in 125.33s |
| `tests/verify_required_runs.py` | 0 | union of passed ids is 415 |
| web check, test, build | 0 | `tsc -b`; 35 files, 317 tests; vite build |
| example-site check, test, build | 0 | `tsc --noEmit`; 46 passed, 0 skipped; vite build |

415 ≥ 402. The four SQLite deselections are the same committed PostgreSQL-only ids, and they passed in the PostgreSQL run. No new skip or xfail. Counts match the MOSS-031 run already on `main`. `web/` and `example-site/` sources are unchanged from the `a84eebd` run, so the earlier npm audit and pip-audit results still describe those lockfiles. `api/uv.lock` is unchanged from `1a005f2`.

Logs: [pytest-sqlite.txt](e991dd2/pytest-sqlite.txt), [pytest-postgres.txt](e991dd2/pytest-postgres.txt), [verify.txt](e991dd2/verify.txt), [ruff-check.txt](e991dd2/ruff-check.txt), [ruff-format.txt](e991dd2/ruff-format.txt), [ruff-scripts.txt](e991dd2/ruff-scripts.txt), [ruff-scripts-format.txt](e991dd2/ruff-scripts-format.txt), [mypy.txt](e991dd2/mypy.txt), [web-check.txt](e991dd2/web-check.txt), [web-test.txt](e991dd2/web-test.txt), [web-build.txt](e991dd2/web-build.txt), [example-site-check.txt](e991dd2/example-site-check.txt), [example-site-test.txt](e991dd2/example-site-test.txt), [example-site-build.txt](e991dd2/example-site-build.txt).

## local, after merging MOSS-056

`main` moved again to `9a4c81c` (MOSS-056). Merged here as `835fbf612895e18aec4c8508eae2b236a3cdd0b4`. This run is labeled `local`. The rehearsal deploy remains the `a84eebd` record.

| | |
| --- | --- |
| SHA tested | `835fbf612895e18aec4c8508eae2b236a3cdd0b4` |
| `git status --porcelain` | empty |
| Date | 2026-10-29T05:21:31Z through 2026-10-29T05:25Z |

Ignored rehearsal `.env` files were moved aside for `load_dotenv()`, then restored. `UV_NO_ENV_FILE=1`.

| Command | Exit | Result |
| --- | --- | --- |
| ruff check app, tests, migrations | 0 | all checks passed |
| ruff format check | 0 | 85 files already formatted |
| ruff check/format scripts, setup, telemetry smoke | 0 | all checks passed; 16 files formatted |
| `mypy app` | 0 | no issues in 28 source files |
| `python3 scripts/check_dependabot.py` | 0 | schema valid; uv, npm, github-actions, and docker manifests covered |
| SQLite required run | 0 | collected 433, **429 passed, 4 deselected, 0 skipped**, 6 warnings in 62.66s |
| PostgreSQL required run | 0 | collected 433, **433 passed, 0 skipped**, 6 warnings in 124.29s |
| `tests/verify_required_runs.py` | 0 | union of passed ids is 433 |

433 ≥ 402 at `3a87c73`. Counts match the MOSS-056 run on `9a4c81c`. The four SQLite deselections are the committed PostgreSQL-only tests and passed on PostgreSQL. No new skip or xfail. `web` and `example-site` sources are unchanged from the `e991dd2` run (317 and 46 tests).

Logs: [pytest-sqlite.txt](835fbf6/pytest-sqlite.txt), [pytest-postgres.txt](835fbf6/pytest-postgres.txt), [verify.txt](835fbf6/verify.txt), [ruff-check.txt](835fbf6/ruff-check.txt), [ruff-format.txt](835fbf6/ruff-format.txt), [ruff-scripts.txt](835fbf6/ruff-scripts.txt), [ruff-scripts-format.txt](835fbf6/ruff-scripts-format.txt), [mypy.txt](835fbf6/mypy.txt), [dependabot.txt](835fbf6/dependabot.txt).
