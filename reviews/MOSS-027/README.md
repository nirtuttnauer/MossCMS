# MOSS-027 backup, wipe, and restore

Two records, kept apart:

- `rehearsal (Linux VM)` — this virtual machine only. Loopback TLS. No public DNS, no registered domain, no external account, and no hosted deployment.
- `local` — the repository test suite on the same checkout, after the rehearsal.

The rehearsal follows [deployment and recovery](../../docs/deployment-recovery.md) and the MOSS-026 Linux VM setup in [reviews/MOSS-026/README.md](../MOSS-026/README.md). PostgreSQL is the required path. SQLite is included because `configure.py --sqlite` is part of the product.

Source SHA for both: `28c3dc969c4d5d36a6aa08c4f0103a5b512cd03a` (`main` after MOSS-026, PR #22). Product files are unchanged. `git status --porcelain` was empty before this evidence directory existed ([git-status-postgres-start.txt](postgres/git-status-postgres-start.txt)). Ignored rehearsal files (`.env`, `example-site/.env`, TLS keys, backup archives) stayed out of git. Passwords, `MOSS_SECRET_KEY`, `MOSS_SETUP_TOKEN`, and delivery tokens are not in this record.

## rehearsal (Linux VM)

Recorded 29 October 2026 (UTC), 2026-10-29T05:51:08Z through 2026-10-29T05:53:43Z. Linux VM, kernel 6.12.94+. Docker 29.9.2, Compose 2.40.3 (the same Compose release MOSS-026 used; the image originally had the Compose 5.6.1 plugin), nginx 1.24.0. The app image was built here with `docker compose up --build`. It was not pulled from a registry.

Compose writes image-build progress to the stdout of `docker compose run`. `scripts/backup.py` and the SQLite `tar` capture that stdout, so the progress must be quiet or the archive is not gzip. Every documented command below ran with `COMPOSE_PROGRESS=quiet`. That is recorded in [compose-progress.txt](postgres/compose-progress.txt).

The Compose bridge could not be assumed to forward to Postgres while legacy `FORWARD` policy is `DROP` and Docker's rules are in iptables-nft. This host accepted the bridge with `iptables-legacy -A DOCKER-FORWARD -i br-… -j ACCEPT`. That is a VM firewall adjustment. It is not a repository change.

| | |
| --- | --- |
| SHA | `28c3dc969c4d5d36a6aa08c4f0103a5b512cd03a` |
| `git status --porcelain` | empty at the start |
| CMS public origin | `https://cms.moss.test:8443` |
| Website public origin | `https://site.moss.test:8444` |
| App bind | `127.0.0.1:8001` |
| Website bind | `127.0.0.1:5174` |
| Database | PostgreSQL 17, Compose service `db`, no published host port |
| Names | `cms.moss.test` and `site.moss.test` resolve only through `/etc/hosts` to `127.0.0.1` |

`.test` is a reserved test name. Nothing was registered in DNS. The TLS certificate is a local leaf for those two names. The private key stayed in `/tmp/moss-027-tls` and is not in this record. nginx config: [nginx.conf](rehearsal/nginx.conf).

### What was checked

`docs/deployment-recovery.md` is the method this ticket cites. After restore, and again after the original database and media volume were removed, the running instance was checked for:

- `/ready`
- sign-in as the same administrator
- workspace, type, and entry identity (full public-table counts and row checksums, plus known ids, slugs, and revision numbers)
- public delivery of the live entry, and absence of the draft
- the private field still present for the editor and absent from delivery, from a secret-word search, and from preview
- original PNG bytes and the 320 WebP variant bytes
- website public path, starter post, sitemap, and RSS
- preview of the saved draft revision
- a schedule that was still pending in the backup and then published by the restored process

### PostgreSQL

```sh
python3 scripts/configure.py --production --public-url https://cms.moss.test:8443
# .env then also received MOSS_WEBHOOK_ORIGINS=http://example-site:5174 and MOSS_IMAGE=mosscms:local
docker compose up --build -d
docker compose --profile website up --build -d example-site
docker compose stop app example-site
python3 scripts/backup.py --directory /tmp/moss-027/backups
docker compose exec db sh -c 'createdb -U "$POSTGRES_USER" mosscms_recovery'
python3 scripts/restore.py backups/20261029T055151Z.dump --target mosscms_recovery --confirm-target mosscms_recovery
# COMPOSE_FILE=compose.yaml:recovery.compose.yaml
python3 scripts/restore_media.py backups/20261029T055151Z.media.tar.gz --confirm-empty-volume
# POSTGRES_DB=mosscms_recovery
docker compose up -d --no-deps --no-build app
docker compose --profile website up -d --no-build example-site
```

`configure.py` exited 0. Compose up, backup, `createdb`, `restore.py`, and the first `restore_media.py` exited 0. The recovery database had 0 public tables before restore ([recovery-db-empty.txt](postgres/recovery-db-empty.txt)). The recovery volume was empty before `restore_media.py`. The second `restore_media.py` exited 1 with `The assets volume must be empty; existing files are never overwritten.` ([restore-media-refused.txt](postgres/restore-media-refused.txt)).

Non-secret configuration: [env-public.json](postgres/env-public.json). Recovery override: [recovery.compose.yaml](rehearsal/recovery.compose.yaml).

| Image | ID | How it arrived |
| --- | --- | --- |
| `mosscms:local`, tagged `mosscms:backup-20261029T055151Z` at backup | `sha256:7f0c73b05fbd201a7cebc20cbd780d627f934981bf0fb74c4b47f5d89e099a47` | local build |
| `workspace-example-site:latest` | `sha256:65dac0faa07c3fcb8513a84358c68a64b0244bd3110f8c4c7156b1e58cd9da97` | local build |
| `postgres:17-alpine` | `sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b` | pulled database image |

The restored app container mounted `workspace_recovered_assets` at `/data` ([app-mounts.txt](postgres/app-mounts.txt)).

Backup files stayed in `/tmp` (mode 0600) and are not in git.

| File | Bytes | SHA-256 |
| --- | --- | --- |
| `20261029T055151Z.dump` | 68617 | `75f2fad8af6b3a8f729486a7d57c9addaabe5bfcf282b1d4fe47901a2afc9e01` |
| `20261029T055151Z.media.tar.gz` | 695 | `4f2073dab409db05544fd1f67e25832561aa606ae4eb26a648a8197a26d20245` |

Before the app was started on the recovered database, every public table's row count and `md5` of `row_to_json` matched the stopped source database, and the source database was still unchanged. Media file hashes matched. [fingerprint.json](postgres/fingerprint.json).

| Table | Rows |
| --- | --- |
| projects | 2 |
| users | 1 |
| content_types | 6 |
| entries | 18 |
| revisions | 18 |
| assets | 1 |
| preview_grants | 2 |
| website_paths | 8 |
| alembic_version | 1 |

Other public tables matched as well (audit 38, entry_field_indexes 204, memberships 2, publication_events 14, schema_revisions 6, tokens 8, and the empty tables). Media files: one PNG and `.320.webp`, `.640.webp`, `.800.webp`.

Known content, same ids before backup, after restore, and after the wipe:

| Check | Result |
| --- | --- |
| `/ready` through TLS | `200` `{"status":"ready"}` |
| sign-in | `rehearsal-admin@example.com` |
| workspaces | Client workspace `cc8da371-8f3c-4071-bdeb-5278a4a773a0`; Example website `394fcc3f-11d5-4044-8190-be277015d21a` |
| live entry | `client-restore-note` `66d41093-d3c3-47fc-b900-35b08962b007`, published, revision 1, private field present for the editor |
| draft | `client-restore-draft` not live; absent from delivery |
| delivery | live slug returned; private-field search total 0; response has no private value |
| preview | draft title `Hidden draft`; private value absent |
| media | PNG SHA-256 `f5ab25a3634b73c5a28ddc23a7d3ec21c038b37b53399170c1a9a2000c22ef0d`, 800×400; 320 WebP 160 bytes, `image/webp` |
| website | `GET /blog/client-restore-post` 200 with title `Client restore post`; starter `/blog/building-this-space` 200; draft URL 404 |
| feeds | `/sitemap.xml` contains `/blog/client-restore-post`; `/rss.xml` contains the title |
| website preview | saved draft body `Private draft body.` |
| schedule in the backup | `client-restore-scheduled` and `scheduled-restore-note` were still `scheduled` ([scheduled-before-backup.txt](postgres/scheduled-before-backup.txt)); public GET was 404; due `2026-10-29T05:53:08Z` |
| schedule after restore | `scheduled-restore-note` live at `2026-10-29T05:53:12Z`; `GET /blog/scheduled-restore-note` 200 |

Logs: [checks-before-backup.json](postgres/checks-before-backup.json), [checks-after-restore.json](postgres/checks-after-restore.json), [checks-after-wipe.json](postgres/checks-after-wipe.json), [scheduled-after-restore.json](postgres/scheduled-after-restore.json).

### Wipe

The original data was removed only after the restored instance had passed those checks.

| Step | Exit | Result |
| --- | --- | --- |
| `docker volume rm workspace_moss_assets` | 0 | original media volume removed; app still mounted `workspace_recovered_assets` |
| `dropdb` of `mosscms` | 0 | only `mosscms_recovery` remained ([databases-after-wipe.txt](postgres/databases-after-wipe.txt)) |

The same ready, sign-in, entry id, private-field split, media hash, website page, feeds, and live scheduled post were read again from the recovered database and volume ([checks-after-wipe.json](postgres/checks-after-wipe.json)).

### SQLite

The PostgreSQL stack was stopped. `python3 scripts/configure.py --production --sqlite --public-url https://cms.moss.test:8443` set `MOSS_USE_SQLITE=true` and exited 0. `backup.py` / `restore.py` do not handle SQLite. The documented archive is a tar of `/data`.

```sh
docker compose up -d --no-build
docker compose stop app
docker compose run --rm --no-deps -T --entrypoint tar app -C /data -czf - . > backups/20261029T055337Z.sqlite-data.tar.gz
python3 scripts/restore_media.py backups/20261029T055337Z.sqlite-data.tar.gz --confirm-empty-volume
docker compose up -d --no-deps --no-build app
```

The archive is 9736 bytes, SHA-256 `d72b373e3d4a917e9b233c3fb70adc974da441a38dd8fbd92d487e1e695b12f8`. The new volume `sqlite_recovered_assets` was empty, then the five files matched the stopped volume byte for byte: `mosscms.db` and the same PNG plus three WebP variants ([sqlite-fingerprint.json](sqlite/sqlite-fingerprint.json)). A second `restore_media.py` exited 1 and refused the populated volume.

After start, and again after `docker volume rm` of the original `workspace_moss_assets`:

| Check | Result |
| --- | --- |
| sign-in | `rehearsal-admin@example.com` |
| live entry | `client-restore-note`, revision 1, private field present for the editor |
| delivery | that slug only; private value absent; secret-word search total 0 |
| media | same PNG SHA-256, 800×400, variant `image/webp` |
| mount | `workspace_sqlite_recovered_assets` at `/data` |

Log: [sqlite-checks.json](sqlite/sqlite-checks.json).

## local

Recorded 29 October 2026 (UTC). Same SHA. This section is the test suite. It is separate from the rehearsal above.

| | |
| --- | --- |
| SHA tested | `28c3dc969c4d5d36a6aa08c4f0103a5b512cd03a` |
| Baseline | `3a87c73c8e925973608e373863813163b41f04a9` |
| Previous main suite | `835fbf6` in the MOSS-026 record (433 collected) |
| `git status --porcelain` | `?? reviews/MOSS-027/` only; no product file was modified. The drill's own status file is empty. |
| Date | 2026-10-29T05:57:16Z through 2026-10-29T06:01:50Z |
| Python / uv | 3.12.3 / 0.12.23 |
| Node / npm | v22.23.4 / 10.9.9 |
| PostgreSQL for the API run | 17-alpine, `127.0.0.1:5432`, role `pg`, database `postgres`, container `moss-027-pg` |
| Docker Compose | 2.40.3 (compose config tests ran) |

`app.main` calls `load_dotenv()`. The gitignored rehearsal `.env` would have set `MOSS_ENV=production`. Both ignored env files were moved out of the tree before the commands below. `UV_NO_ENV_FILE=1` was set for `uv run`.

Baseline `3a87c73`: 402 collected, SQLite 398 passed and 4 runtime skips, PostgreSQL 402 passed. This tree collects 433. 433 ≥ 402. No new skip or xfail. The four SQLite deselections are the committed PostgreSQL-only tests, and they passed in the PostgreSQL run:

- `tests/test_concurrency.py::test_postgres_workers_skip_locked_rows_and_claim_once`
- `tests/test_indexing.py::test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan`
- `tests/test_postgres_product_migration.py::test_postgres_0009_preserves_localized_live_scheduled_and_revision_data`
- `tests/test_search.py::test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches`

### Commands and results

Working directory `api` unless noted. No `-k`, `--ignore`, new skips, or xfails.

```sh
uv sync --locked --group dev
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run ruff check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run ruff format --check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run mypy app
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -ra --tb=line -m "not postgres"
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres \
  MOSS_TEST_DATABASE_URL='postgresql+psycopg://pg:pgtestpw@127.0.0.1:5432/postgres' \
  uv run pytest -ra --tb=line
uv run python tests/verify_required_runs.py
cd ../web && npm ci && npm run check && npm test && npm run build
cd ../example-site && npm ci && npm run check && npm test && npm run build
```

| Command | Exit | Result |
| --- | --- | --- |
| `uv sync --locked --group dev` | 0 | locked deps installed |
| `ruff check app tests migrations` | 0 | all checks passed |
| `ruff format --check app tests migrations` | 0 | 85 files already formatted |
| ruff check scripts and example-site setup | 0 | all checks passed |
| ruff format check of those files | 0 | 15 files already formatted |
| `mypy app` | 0 | no issues in 28 source files |
| SQLite required run | 0 | collected 433, **429 passed, 4 deselected, 0 skipped**, 6 warnings in 63.40s |
| PostgreSQL required run | 0 | collected 433, **433 passed, 0 deselected, 0 skipped**, 6 warnings in 128.07s |
| `tests/verify_required_runs.py` | 0 | union of passed ids is 433 |
| web `npm ci`, `npm run check` | 0 | `tsc -b` |
| web `npm test` | 0 | 35 files, 317 tests passed |
| web `npm run build` | 0 | vite build succeeded |
| example-site `npm ci`, `npm run check` | 0 | `tsc --noEmit` |
| example-site `npm test` | 0 | 46 passed, 0 failed, 0 skipped |
| example-site `npm run build` | 0 | vite build succeeded |

Logs: [pytest-sqlite.txt](local/pytest-sqlite.txt), [pytest-postgres.txt](local/pytest-postgres.txt), [verify.txt](local/verify.txt), [ruff-check.txt](local/ruff-check.txt), [ruff-format.txt](local/ruff-format.txt), [ruff-scripts.txt](local/ruff-scripts.txt), [ruff-scripts-format.txt](local/ruff-scripts-format.txt), [mypy.txt](local/mypy.txt), [web-check.txt](local/web-check.txt), [web-test.txt](local/web-test.txt), [web-build.txt](local/web-build.txt), [site-check.txt](local/site-check.txt), [site-test.txt](local/site-test.txt), [site-build.txt](local/site-build.txt), [exits.txt](local/exits.txt).
