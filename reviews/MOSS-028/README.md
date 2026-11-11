# MOSS-028 upgrade and rollback

Rehearsal on this Linux VM, labeled `local`. Loopback TLS. No public DNS, no registered domain, no external account, and no hosted deployment.

The recovery steps are in [deployment and recovery](../../docs/deployment-recovery.md). Rollback is the retained image plus the pre-upgrade database, media, and configuration. The drill does not ask Alembic to move the schema backward. PostgreSQL and SQLite both ran, because the recovery doc covers both.

## Why this older SHA

`3a87c73` and `d50e278` already contain migrations `0001` through `0014`, the same head as main `58a0f15`. An upgrade from either SHA would leave `alembic_version` at `0014` with no migration to apply.

The old image is `1d6d0ef5bcc2b2c8d7dd628098c89b680b060a9a` (`docs: remove private planning integration metadata`, on `main`, parent of `ecd5568`). That tree's migrations stop at `0009`. Current main adds `0010`, `0011`, `0012`, `0013`, and `0014`. The image was built from a detached worktree of that commit, not pulled from a registry.

| Image | Tag | ID |
| --- | --- | --- |
| Old, schema `0009` | `mosscms:moss028-1d6d0ef` | `sha256:1bca835ec6b7aff479d71257d53de0b9b92bf688afefbcf3185a720019d6a344` |
| Current main, schema `0014` | `mosscms:moss028-58a0f15` | `sha256:8817c47d07fe82e92f5d670f16bb3c7ea1d05c5f07e74321c681091fd2a71599` |

Build log: [image-build.txt](rehearsal/image-build.txt). Migration files inside each image: [migrations-moss028-1d6d0ef.txt](rehearsal/migrations-moss028-1d6d0ef.txt), [migrations-moss028-58a0f15.txt](rehearsal/migrations-moss028-58a0f15.txt).

## rehearsal (Linux VM)

Recorded 11 November 2026 (UTC), `2026-11-11T18:33:01Z` through `2026-11-11T18:34:08Z`, after the images had been built at `2026-11-11T18:18:19Z`. Linux kernel `6.12.113+`. Docker 29.1.3, Compose 2.40.3, nginx 1.24.0. Checkout at the start: `58a0f15fa5e75e446b210911d727340dc4ca67dd`. `git status --porcelain` showed only untracked `reviews/MOSS-028/`. Context: [context.txt](rehearsal/context.txt).

| | |
| --- | --- |
| CMS origin | `https://cms.moss.test:8443` |
| App bind | `127.0.0.1:8001` |
| Names | `cms.moss.test` resolves through `/etc/hosts` to `127.0.0.1` |
| Compose project | `moss028` |

`.test` is a reserved name. Nothing was registered in DNS. The TLS key stayed in `/tmp/moss-028-tls` and is not in this record. Passwords, `MOSS_SECRET_KEY`, `MOSS_SETUP_TOKEN`, and session tokens are not in this record. nginx config: [nginx.conf](rehearsal/nginx.conf). Driver: [drill.py](rehearsal/drill.py).

Legacy `FORWARD` policy on this VM is `DROP`, and Docker's bridge rules are in iptables-legacy. After each Compose network came up, the drill added `iptables-legacy -A DOCKER-FORWARD -i br-… -j ACCEPT` for that bridge. That is a VM firewall adjustment. It is not a repository change.

Each engine loaded an administrator, a `note` type, a published entry `upgrade-rehearsal-note`, a draft `upgrade-rehearsal-draft`, and one 800×400 PNG with `.320.webp`, `.640.webp`, and `.800.webp` variants. Checksums were taken with writers stopped, before the verification sign-in that would add a session row.

Editorial checksums cover every public table except `alembic_version`, `entry_field_indexes`, `publication_events`, `audit`, `tokens`, and `webhook_deliveries`. Those excluded tables are schema bookkeeping, the derived search projection, or worker and session state. Media checksums are SHA-256 of the sorted file list. SQLite media checksums omit `mosscms.db` and its wal/shm files; the database is checksummed as rows.

### Documented backup command, then the correction

With the default `pull_policy: build`, `scripts/backup.py` and the SQLite `docker compose run … tar` capture stdout that is the image build log. `gzip -t` exits 1. The Compose image tag moves to the new build. A second tag of the old image stayed at `sha256:1bca835ec6b7…`.

| Probe | Archive starts with | `gzip -t` | Probe tag rebuilt |
| --- | --- | --- | --- |
| PostgreSQL `backup.py` | `#0 building with "default" instance` | 1 | yes |
| SQLite `tar` redirect | the same build log | 1 | yes |

Logs: [probe-backup.json](postgres/probe-backup.json), [probe-tar.json](sqlite/probe-tar.json).

`MOSS_PULL_POLICY=never` keeps the image that is already present, and the archive is gzip. `docker compose run` has no `--no-build` flag, so the recovery override also sets `pull_policy: never`. Otherwise `restore_media.py` rebuilds the retained tag from the current checkout before `up --no-build`. [deployment and recovery](../../docs/deployment-recovery.md) now says so. The successful path used that corrected step.

### PostgreSQL

Revision `0009` to `0014` on the same database volume. `entry_field_indexes` appeared with 9 rows. Entries, revisions, assets, and the other editorial tables kept their row checksums. Media manifest `74155ed9a497f2ffd7511dad50804ef6e30970281d88e073b29a6e3156a03e6a` was unchanged (4 files).

The publication-event row changed from its stored state to `processed` when the new process ran. That is the outbox worker, not the entry body. The pre-upgrade dump, restored into empty `mosscms_recovery` before the old image started, matched the pre-upgrade database on every public table, including that event. After the retained image became ready, the worker marked the same event processed again. Editorial tables and media still matched. The upgraded database `mosscms` was still at revision `0014` after rollback.

| | |
| --- | --- |
| Retained tag | `mosscms:backup-20261111T183312Z` |
| Dump | 42651 bytes, `dea974ef19727c8dba72e3abd504471d1db2882ba1efbbc748402e033b4dea30` |
| Media archive | 732 bytes, gzip, `10c972bbbf394db69b952c094649880fb8514a5e73f3ddce73bc636a4c5082af` |
| Published entry | `9718195e-ef9b-4871-b8cb-d1497fc4fbd9`, revision 1 |
| Draft | `be83b471-c54a-41d1-94ac-ec18813f2104`, revision 1 |
| Rollback container image | the retained image id above |
| Second media restore | exit 1, populated volume refused |

Override: [recovery.compose.yaml](rehearsal/recovery.compose.yaml). Result: [result.json](postgres/result.json).

### SQLite

Same content shape on a new SQLite volume. Revision `0009` to `0014`, with `entry_field_indexes` added. Editorial row checksums matched after the upgrade. The archive restore, read before the old image started, matched the pre-upgrade database on every table. After the retained image became ready, the full row checksum, including the publication event, still matched, and the media manifest `fb8df9d3caec3229a986116a7da103585752281fefceb4eb8597fbe004400a72` matched (4 files).

| | |
| --- | --- |
| Retained tag | `mosscms:backup-sqlite-20261111T183347Z` |
| Archive | 7350 bytes, gzip, `565a68cd11ce6c3ae162f134ae81203206f40988a5fe7b1c59d7fd843e22e8c1` |
| Published entry | `04a01435-0cb5-48d6-9271-a07fd59c2ddc`, revision 1 |
| Draft | `56ad98de-90c9-4a87-8ba7-c32c0a64a333`, revision 1 |
| Second restore | exit 1, populated volume refused |

Override: [sqlite-recovery.compose.yaml](rehearsal/sqlite-recovery.compose.yaml). Result: [result.json](sqlite/result.json).

Backup archives stayed in `/tmp/moss028` and are not in git. The machine-readable pair of results is [summary.json](summary.json).
