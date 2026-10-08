# Release acceptance — 8 October 2026

MC-33 records execution after the owner approved all 34 tasks in this chat. Aftur's unfinished approval/dependency workflow still shows the initial proposed statuses; MCP attempts and branch/commit artifacts record actual implementation. This is local acceptance evidence, not a public deployment certification.

## Fixture and method

- Disposable PostgreSQL 17 Alpine container, loopback port 55433, no production volumes or data. A schema `0001` fixture contained 1,004 entries, one workspace, one type and one historical revision; states included live, scheduled, draft and trash.
- `pg_dump -Fc` and `pg_restore --single-transaction` copied it into a separate empty database. Upgrade to `0008` preserved every ID, slug, working JSON, status, version and historical revision. Only the previously live entry received a live snapshot; the pending schedule captured revision 7. Migration took 0.1307 seconds in the measurement run.
- Host reported `arm64 macOS-27.0.1-arm64-arm-64bit-Mach-O`; exact CPU model/RAM were unavailable. API: Python 3.14.7/uvicorn on the host. Website: production Vite output served by Node 24.19 on the host. PostgreSQL ran in Docker. One HTTP author, sequential requests, no background load generator.
- The walkthrough used real setup/authentication, scoped delivery, website HTTP requests, an actual signed local webhook and local image storage. API and website ran on isolated ports 18033/15133. Measurements are content availability over HTTP, not browser paint time or a full Compose performance benchmark.

## Observed results

Raw observations: [release-acceptance-results.json](release-acceptance-results.json). Percentiles use nearest rank; small samples limit generalization.

| Check | Result | PRD target / qualification |
| --- | --- | --- |
| Publish/save latency, 12 sequential saves | p95 0.0644 s | <= 2 s; local host API, not full Compose load |
| Warm-cache website freshness, same 12 publications | p95 1.0746 s; range 0.6206–1.0746 s | <= 3 s with healthy event propagation |
| Captured schedule with a newer draft | published 0.4444 s after due time | Original capture published; newer working slug retained |
| Ten-entry same-due schedule batch | p95 2.9782 s after due time | <= 10 s; one worker phase, not ten independent phase samples |
| Webhook disabled; ten-second polling simulated twice | 10.0624 / 10.0556 s | <= 15 s; HTTP polling simulation |
| Restore and forward upgrade | all 1,004 entries and one history row preserved | Source database untouched |
| Draft of live content | old live title/slug remained available; new working slug returned 404 | No live-content loss |
| Preview | saved revision only; private field absent; public cache unchanged; revoked session returned 401 | HttpOnly session; revocation/isolation passed |
| Media | 800×400 local raster uploaded; cover/gallery ID retained; signed WebP variant returned correct MIME | Local HTTP delivery passed |
| Routes, metadata and feeds | initial page title/canonical, legacy 308, draft 404, published sitemap/RSS passed | Public projection only |

The scripted HTTP walkthrough is complemented by these completed checks:

- PostgreSQL: **47 passed**, including concurrent scheduler/outbox claimers, lock skipping, roles, cross-workspace boundaries, conflicts, immutable schedules, safe failed-capture retries, preview expiry/revocation, image variants and signed-webhook retry/security behavior.
- SQLite: **46 passed, one PostgreSQL-only concurrency test skipped**. Ruff lint/format and mypy passed.
- Admin: **33 tests passed**; both frontends passed TypeScript checks and production builds. Shared Markdown rendering/URL policy tests cover unsafe URLs, private asset projection and formatting consistency.
- Website: **seven server tests passed**, covering routes/404s, feeds, metadata escaping, event verification/deduplication and preview session behavior.
- Both locked npm graphs reported **zero audit vulnerabilities** at check time.
- Both production Docker images built successfully. API runtime imported under Python 3.12; website runtime imported its server modules under Node 22, including the shared route policy.

Release checks exposed and fixed a worker-shutdown race, overly slow webhook worker cadence, default GraphQL logging of submitted text, development preview issuer handling and missing shared website runtime files. Production Docker contexts now exclude test-only cross-frontend imports and local tracker data. Dependency deprecation warnings remain (httpx integration and SQLite datetime adapters); the website build retains its large lazy Three.js chunk warning.

## Reproduce safely

Use only a disposable local PostgreSQL instance, a role permitted to create test databases, and unused ports. These scripts deliberately refuse non-loopback databases or names outside `moss_release_*`. Seed also refuses non-empty databases; the HTTP walkthrough requires the untouched 1,004-entry fixture with no accounts and writes synthetic content. Do not point either script at an existing instance.

1. Install locked API dev dependencies and website dependencies; build `personal-site`.
2. Create an empty `moss_release_legacy` database and set `MOSS_RELEASE_DATABASE_URL` to its SQLAlchemy PostgreSQL URL. Run `api/.venv/bin/python scripts/release_fixture.py seed` from the repository root.
3. Dump that database with `pg_dump -Fc`; restore into a **different empty** `moss_release_restored` database with `pg_restore --no-owner --no-acl --single-transaction`. Retain the original fixture for comparison.
4. Change `MOSS_RELEASE_DATABASE_URL` to the restored database. Run `api/.venv/bin/python scripts/release_fixture.py verify-upgrade`, then `api/.venv/bin/python scripts/release_http_acceptance.py`. Set `MOSS_RELEASE_NODE` if Node is not on PATH and `MOSS_RELEASE_RESULTS` to choose the JSON output path.
5. A repeat HTTP run needs a fresh restoration. Remove only the disposable databases/container and test media afterward.

The checked-in scripts were also run against a second independently restored fixture. Its upgrade preserved the same 1,004 entries/history and took 0.1402 seconds; this verifies the saved reproduction path rather than relying only on a temporary harness.

For ordinary checks, use the commands in the root README and `npm test` in `personal-site`. PostgreSQL tests require `MOSS_TEST_DATABASE_URL`; each test creates and removes its own database. Docker builds use the repository root as context for both images.

## Checks still requiring deployment evidence

No external OAuth exchange, real S3 bucket, public TLS/reverse proxy, public DNS or deployment was exercised. S3/provider business rules have automated coverage with mocks. A full Compose load benchmark, long-duration failure soak, browser paint measurements, visual browser walkthrough and assistive-technology review were not performed. The measured samples met their numerical targets under the stated local conditions; broader performance and visual/accessibility claims remain unverified.

Recovery must pair the database/media backup with its matching application image and configuration. See [the deployment and recovery guide](deployment-recovery.md) for the operator procedure and remaining owner-specific setup.

MC-34 additionally exercised the stopped-app backup tools in an isolated Compose project: a synthetic database record and original/variant files were backed up, restored into a separate empty database/new volume, and verified after starting the retained image. `/ready` passed; a repeated media restore refused the populated volume. The test project and its disposable volumes were removed afterward.
