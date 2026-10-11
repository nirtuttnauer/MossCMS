# Deployment, diagnosis and recovery

Run commands from the repository root. [Release evidence](release-acceptance-2026-10-08.md) records the local checks and limits; these instructions do not establish public deployment, DNS, OAuth or real S3 configuration.

## Configuration and first deployment

For a fresh instance, run `python3 scripts/configure.py --production --public-url https://cms.example.com`, review `.env`, then `docker compose up --build -d`. Preserve generated secrets and keep `.env` private. Existing development databases require an operator password rotation before production; changing `.env` alone does not change a PostgreSQL role password. Production rejects development auth bypass, SQLite, default database credentials and HTTP browser origins.

For a published Docker Hub image, set `MOSS_IMAGE` in `.env` to a published `nirtuttnauer/mosscms` version or digest, run `docker compose pull app db`, then `docker compose up --no-build -d --wait app`. The same configuration, volumes and recovery tools apply. See [Docker publishing and upgrades](docker.md).

Terminate TLS at a reverse proxy. Keep the default loopback bindings (CMS 8001, website 5174); PostgreSQL has no published host port. Allow required request/upload sizes and timeouts. Proxy website `/api/events` with streaming enabled and buffering disabled; polling remains a recovery path. Do not cache preview pages or `/api/preview`, and do not log preview bodies, cookies, bearer tokens or authorization headers. Keep the website's server routes available; uploading only its static build is insufficient.

| Location | Setting | Purpose |
| --- | --- | --- |
| Root `.env` | `MOSS_ENV=production`, `MOSS_SKIP_AUTH=false` | Enforce real authentication |
| Root `.env` | `MOSS_PUBLIC_URL`, `MOSS_ORIGINS` | Canonical CMS HTTPS origin and explicit trusted browser origins |
| Root `.env` | `MOSS_SECRET_KEY`, `MOSS_SETUP_TOKEN`, PostgreSQL credentials | Stable secrets and protected setup/database access |
| Root `.env` | `MOSS_WEBHOOK_ORIGINS` | Optional exact private callback origins; Compose website uses `http://example-site:5174` |
| Website `.env` | `MOSS_API_URL`, `MOSS_DELIVERY_TOKEN` | Server-only CMS connection; Compose overrides the URL to `http://app:8001` |
| Website `.env` | `MOSS_PROJECT_ID` | Setup script's workspace identity; distinct from event validation below |
| Website `.env` | `SITE_PUBLIC_URL` | Canonical HTTPS site origin, normally `http://localhost:5174`; local HTTP testing can use `http://localhost:5174` |
| Website `.env` | `SITE_SOCIAL_IMAGE` | Optional permanent static HTTPS URL/path, without query/fragment; omit to omit image cards |
| Website `.env` | `MOSS_WEBHOOK_SECRET`, `SITE_MOSS_WORKSPACE_ID` | One-time webhook signing secret and matching workspace UUID |
| Website `.env` | `SITE_PREVIEW_ORIGINS` | Optional additional trusted redemption origins; the configured public origin is always included |
| CMS workspace Settings | Website preview origin | Exact browser-facing site origin used to construct editor preview links |

Create the five website types/content and a scoped delivery token using [website setup](../example-site/README.md). The automatic setup script is for temporary **local development** bypass only. Production admins use authenticated admin/API operations; never enable bypass on an exposed instance. Repeated setup retains entries/custom compatible fields and existing environment keys, but the script updates its CMS connection values; review workspace selection before running it.

Create a webhook in Settings for `http://example-site:5174/api/moss-events` in Compose (or the public HTTPS receiver). For the internal address, add `http://example-site:5174` to root `MOSS_WEBHOOK_ORIGINS` and recreate the app **before** registering the endpoint. Put the one-time secret and workspace ID into the website environment and recreate the website. Disable/recreate the endpoint to rotate the secret. Keep the delivery token scoped to `siteProfile`, `sitePage`, `siteSlide`, `sitePost`, `siteProject`; keep credentials out of `VITE_` variables. Environment changes require container recreation.

Public caching lasts five seconds. A verified webhook clears it and signals open browsers over SSE; browsers also poll every ten seconds and on visibility changes. Stale public data may be served during an outage for at most ten minutes. Preview authorization fails closed. Multiple website processes need one callback per instance or shared invalidation infrastructure; the current cache/session/SSE state is in memory. See [webhook protocol and retries](webhooks.md).

For local media retain the `moss_assets` volume. For S3 retain private bucket objects, SDK credentials/region and any custom endpoint; enable versioning and separate object backups. Original objects and generated `.WIDTH.webp` variants form one backup set. Existing asset records retain their storage backend when configuration changes. See [OAuth registration](oauth-setup.md) for callbacks and explicit account linking; credentials and real exchanges are owner-specific checks.

## Diagnose publication or freshness

| Symptom | Check / action |
| --- | --- |
| CMS unavailable | `docker compose ps`, `docker compose logs --tail 100 app db`; `/health` checks process, `/ready` checks database |
| Save rejected/conflicted | Preserve form values, inspect error code/request ID, compare the server revision; use receipt reconciliation for a lost response |
| Overdue schedule | Confirm app readiness and UTC due time in Publications; scheduler checks every five seconds and on restart |
| Failed capture | Inspect structured code/message in Publications, repair reference/schema/slug issue, retry the retained capture or explicitly replace it |
| Publish committed but website old | Inspect Settings delivery history, endpoint allowlist, matching secret/workspace, website delivery token scope/expiry, and website logs; then test polling/visibility refresh |
| Webhook disabled/failing | Publication remains committed; worker checks approximately every second, retries up to six attempts, claims recover after two minutes; rotate invalid credentials and recreate services |
| Preview denied | Check grant expiry/revocation, issuer editor membership, token workspace/type scope and exact preview origins; regenerate after saving current revision |
| Broken images | Check asset backend, original/variant presence, signed URL expiry and token scope; older assets need reupload for variants |
| Slow request | Correlate `X-Request-ID`, GraphQL `extensions.requestId`, `Server-Timing` and structured duration logs; admin `/metrics` checks aggregate API state |

Logs intentionally omit submitted bodies, query strings, secrets and GraphQL query text. Protect application/proxy logs and database dumps. API shutdown waits for active worker work before disposing database connections. Normal publication transactions never wait for network callbacks.

## Backup with writers stopped

Record the source commit, API and website image IDs/tags, migration revision, PostgreSQL major version, configuration and storage backend with each backup. Keep the matching `.env` in encrypted private storage. Tag/archive images before rebuilding, for example `docker image tag "$(docker compose images -q app)" mosscms:backup-TIMESTAMP`; also retain the website image if used. A source checkout alone is weaker recovery evidence than a retained image.

Stop the app to pause editors, scheduler and outbox. Stop the website too if used, so visitors cannot consume a mixed recovery state. Keep the database running:

```sh
docker compose stop app
python3 scripts/backup.py
```

The backup tool uses a temporary container for the media archive and bypasses application startup, so the app may remain stopped. It creates restrictive timestamped `.dump` and `.media.tar.gz` files under `backups/`. Restart with `docker compose up -d --no-build app` when backup completes; recreate/start the website if it was stopped. `--database-only` omits media and is appropriate only when you have a separate matching media backup. Copy backups off-host and validate recovery regularly. S3 objects require their own backup/versioning procedure.

## Restore a matched backup/image pair

Use a separate empty database and a **new** media volume. Keep the original database/media untouched until checks pass. For rollback use the old application image and its pre-upgrade database/media/configuration together. Do not run `alembic downgrade` or point an old image at the upgraded database: independent live/working/scheduled snapshots cannot be represented safely in older schemas.

1. Stop the app and website. Keep the Compose database running. Create an empty recovery database and restore the chosen dump:

   ```sh
   docker compose exec db sh -c 'createdb -U "$POSTGRES_USER" mosscms_recovery'
   python3 scripts/restore.py backups/TIMESTAMP.dump --target mosscms_recovery --confirm-target mosscms_recovery
   ```

2. Create `recovery.compose.yaml` selecting the matching retained image and a new assets volume. `!override` requires Docker Compose 2.24.4 or newer:

   ```yaml
   services:
     app:
       image: mosscms:backup-TIMESTAMP
       volumes: !override
         - recovered_assets:/data
   volumes:
     recovered_assets:
   ```

   If the website is used, also set its matching retained `example-site.image` in this override. Keep PostgreSQL at the original major version.

3. Select the override and restore media **before starting the app**:

   ```sh
   export COMPOSE_FILE=compose.yaml:recovery.compose.yaml
   python3 scripts/restore_media.py backups/TIMESTAMP.media.tar.gz --confirm-empty-volume
   ```

   The restore starts a temporary Python container without running migrations. It rejects populated volumes, links and invalid archive paths. If a restore is interrupted, use another new empty volume; do not overwrite a partial one. S3 recovery must restore the matching object versions/variants separately.

4. Set root `.env` `POSTGRES_DB=mosscms_recovery`, preserving the matching credentials/secrets and storage configuration. Start the selected retained image with `docker compose up -d --no-deps --no-build app`. `--no-deps` keeps the running database service untouched; `--no-build` prevents replacing the retained image. Wait for `/ready`, verify sign-in, workspace/type/entry counts, known IDs/slugs/history, representative public/private delivery and original/variant media. Start the matching website image and check public paths, metadata/feeds, preview and publication propagation before reopening access.

The restore script refuses non-empty databases and uses a single restore transaction. Retain original volumes and the recovery override while using them; subsequent commands must select the same Compose files. Never use `docker compose down -v` on an instance whose data you intend to keep.

## Forward upgrade

Rehearse on a separately restored database/media pair first. Save the current image/configuration, stop writers, back up, then build the new source and start the new image. Forward migrations run before serving; advisory locks serialize PostgreSQL migrations. Verify readiness and the same content/access checks above, plus captured schedules and webhook delivery, before exposing it. Upgrades can keep the current data volumes; do not delete them. Major PostgreSQL upgrades require a separate `pg_upgrade` or dump/restore procedure.

The 8 October acceptance run upgraded schema `0001` to `0008` on a separate 1,004-entry restore. The stopped-app backup/restore path was separately exercised with an isolated Compose database, new media volume, retained image and original/variant fixtures; the restored app became ready and a second media restore correctly refused the populated volume. These are synthetic local rehearsals. External provider/bucket/TLS checks, full Compose load measurements, browser/assistive-technology review and public deployment remain owner-specific work; see the evidence report for exact limits.

### Migration 0009: locales and published website URL history

Migration `0009` adds workspace authoring locale settings with `en` as the default and sole suggestion for existing workspaces. It preserves stored translation maps and delivery locale behavior. It also adds reservations for known published website paths. Deploy the API and `example-site` together: the website loader now queries `websiteRedirects` and `websiteReservedPaths`, which older APIs do not provide. Keep both stopped during the matched upgrade and verify current routes, historical redirects and publication propagation before reopening access.

A website path recorded during publication stays owned by its original entry. Publishing A → B → C redirects A and B directly to the current live C with HTTP 308; conflicting canonical or recorded paths are rejected. Draft saves and scheduling alone create no public paths or redirects. A scheduled capture records its path only when publication succeeds. Unpublish and trash remove public destinations, while reservations remain; the original entry can recover valid mappings when republished. Unavailable reserved paths return the normal public unavailable response rather than another entry's legacy alias. Sitemap, RSS and canonical metadata retain current live paths only.

The upgrade starts with no reconstructed history. On a later rename it records the entry's known currently published path, but it cannot recover URLs changed before path recording was introduced. Include the new reservation table in matched database backups and preserve it during recovery.

The SQLite forward upgrade and concurrent publication checks passed. A synthetic **PostgreSQL 17.11** rehearsal also passed: populated `0008` → `0009` preservation, concurrent publication rollback, scheduler locking and outbox claims (22 focused tests, no skips). See [editing acceptance evidence](editor-acceptance-2026-10-11.md) and `api/tests/test_postgres_product_migration.py` for scope and reproduction. The disposable container was removed afterward. Rehearse again against a separately restored production-like PostgreSQL database/media pair before rollout; this synthetic test does not establish production readiness.
