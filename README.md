<p align="center">
  <img src="web/public/brand/moss-symbol-v2.png" alt="MossCMS logo" width="160" />
</p>

# MossCMS

A self-hosted, GraphQL-first CMS for content-driven websites and small editorial teams. Model your content, edit it in a React admin, and deliver published entries to your own frontend.

One Docker image serves the API and admin from the same origin. Use PostgreSQL or the optional persistent SQLite mode; store media locally or in S3-compatible storage. Drafts, live content, and scheduled revisions remain separate so editing does not silently change what visitors see.

[MIT licensed](LICENSE). Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

[![Checks](https://github.com/nirtuttnauer/MossCMS/actions/workflows/checks.yml/badge.svg)](https://github.com/nirtuttnauer/MossCMS/actions/workflows/checks.yml)

![MossCMS content library and getting-started checklist](docs/acceptance-2026-10-11/first-use-three-ready.jpg)

*Actual admin screenshot from the checked-in first-use walkthrough, using sample content.*

| Build | Edit | Deliver |
| --- | --- | --- |
| Visual content schemas, nested fields, locales, and references | Markdown, media, autosave, and revision recovery | Schema-derived GraphQL and scoped delivery tokens |
| Separate workspaces with their own teams and schemas | Independent drafts, live content, and scheduled revisions | Published content with private fields removed |
| Local or S3-compatible asset storage | Role-based access and advisory SEO checks | An example website with saved draft previews |

[Start locally](#start) · [CMS comparison](#cms-comparison) · [Architecture](#how-it-fits-together) · [First content](#your-first-content) · [Delivery API](#graphql-for-your-frontends) · [Development](#local-development-and-checks) · [Status](#status-and-scope)

## Status and scope

MossCMS is an early-stage project with implemented editorial and delivery workflows. The feature descriptions below refer to the current `main` code. Tests and checked-in acceptance reports describe specific verified paths; they do not establish that every deployment, OAuth provider, or storage backend is qualified.

The local suite recorded at `d50e2788485e4ef0c65598c4c2f2bd7536e1ed96` is [MOSS-024](reviews/MOSS-024/README.md) (29 October 2026): PostgreSQL 403 passed and 0 skipped, SQLite 399 passed with 4 deselected and 0 skipped, admin 317 passed, example-site server 46 passed and 0 skipped. [TODO.md](TODO.md) cites the same record.

The [query-performance](https://github.com/nirtuttnauer/MossCMS/pull/3), [delivery-client](https://github.com/nirtuttnauer/MossCMS/pull/4), [observability](https://github.com/nirtuttnauer/MossCMS/pull/5), [workspace-portability](https://github.com/nirtuttnauer/MossCMS/pull/6), and [editor-workflow](https://github.com/nirtuttnauer/MossCMS/pull/7) changes were integrated into `main` on 21 October 2026. Their workflow guides describe the implemented paths and remaining limits.

Self-hosting means owning HTTPS, access configuration, backups, upgrades, and recovery. Start with the [operator guide](docs/deployment-recovery.md) before exposing an instance beyond your development machine. SQLite is intended for one app instance; changing database backends does not migrate your data.

<details>
<summary>Browse the full README</summary>

- **Getting started:** [Start](#start), [architecture](#how-it-fits-together), [first content](#your-first-content), [example website](#example-website-frontend).
- **Choosing a CMS:** [Feature comparison](#cms-comparison), [pricing and limits](docs/cms-comparison.md#pricing-and-limits), [MossCMS limitations](docs/cms-comparison.md#current-mosscms-limitations), [competitive roadmap](docs/cms-comparison.md#competitive-roadmap).
- **Content and access:** [Admin and teams](#admin-and-teams), [OAuth](#oauth-sign-in), [data modeling](#define-data), [publishing](#draft-live-and-scheduled-content), [SEO audit](#seo-audit).
- **Integration:** [GraphQL](#graphql-for-your-frontends), [documentation guides](#documentation).
- **Operations:** [Storage and production](#storage-and-production), [backup, restore, and upgrades](#backup-restore-and-upgrades).
- **Contributing:** [Code layout](#code-layout), [development and checks](#local-development-and-checks), [local sign-in bypass](#temporarily-skip-sign-in), [roadmap and evidence](#roadmap-and-evidence).

</details>

## CMS comparison

<a id="pricing-and-limits"></a>
<a id="current-mosscms-limitations"></a>
<a id="competitive-roadmap"></a>

The [dated CMS comparison](docs/cms-comparison.md) retains the full feature tables, hosting and license costs, quotas, MossCMS limitations and competitive roadmap. Competitor pricing and feature assumptions are dated 12 October 2026; check vendor links for current terms. The performance evidence below measures MossCMS on its stated local workloads, without claiming a matched competitor trial.

## Performance evidence

![MossCMS p95 latency at 50,000 entries, including compact indexes and request-local lookups](docs/benchmarks/performance-50000-2026-10-13.png)

These are separate **60-second local samples** with 20 delivery readers and three draft writers on shared Docker hardware. The 50k fixture spans three workspaces; its main workspace contains 40k entries, including 24k live entries. The latest sample records **189 ms list, 243 ms filter, 185 ms generated-query and 206 ms draft-save p95**, with no request errors. Database size fell from **440 MiB to 288 MiB** compared with the ordering build; unsupported projection rows were removed and hashes compacted.

The 50k graph records an earlier compact-index build. The latest substring-search build is measured separately below.

![MossCMS sustained 100,000-entry p95 comparison, 30 minutes with 20 readers and 3 writers](docs/benchmarks/performance-100000-sustained-2026-10-14.png)

The latest **30-minute 100k run** completed **260,209 requests with zero errors**. p95: **197 ms search miss, 225 ms list, 248 ms filter, 236 ms generated query and 291 ms draft save**. Search-miss p95 fell **51%** from 407 ms with PostgreSQL trigram indexes. The timed searches target unpublished slugs; positive and broad searches are checked separately outside load. Its main workspace has 80k entries and 48k live entries. Matched recovery, publication, restart and isolation checks passed. Database size was **591 MiB**, including **18.1 MiB** of search indexes. The graph compares four 30-minute runs.

See the [substring-search report](docs/benchmarks/RESULTS-SUBSTRING-SEARCH-2026-10-14.md), [100k filtering report](docs/benchmarks/RESULTS-FILTERING-2026-10-13.md), [mixed-load report](docs/benchmarks/RESULTS-MIXED-LOAD-2026-10-13.md), [baseline](docs/benchmarks/RESULTS-2026-10-12.md), [filtering](docs/benchmarks/RESULTS-AUTOMATIC-INDEXING-2026-10-12.md) and [ordering report](docs/benchmarks/RESULTS-SCALAR-ORDERING-2026-10-12.md) for source manifests, storage/recovery checks and limits. The [performance and scaling plan](docs/planning/PERFORMANCE-SCALING-2026-10-12.md) explains query, replica and sharding priorities. [Regenerate the graphs](scripts/plot_benchmarks.py).

The samples are self-benchmarks, not competitor trials or production guarantees. OpenTelemetry was disabled; instrumentation overhead is not measured here.

## Start

You need **Docker with Compose** and **Python 3**. Node.js and a local Python dependency environment are only needed for [development outside Docker](#local-development-and-checks).

Clone, generate configuration, and start:

```sh
git clone https://github.com/nirtuttnauer/MossCMS.git
cd MossCMS
python3 scripts/start.py
```

The command checks Docker, creates private configuration, waits for readiness, and prints the URL and a private setup token for the local operator. Open [localhost:8001](http://localhost:8001), enter your name, workspace name, email, and a password of at least 12 characters. After setup, repeated startup keeps the existing account and does not print the token. Configuration is generated locally with random secrets; `.env` is excluded from builds and source control.

> **Keep your data:** PostgreSQL and local uploads live in named Docker volumes. Recreating containers retains them; `docker compose down -v` deletes them. [Back up before upgrading](#backup-restore-and-upgrades).

### Run with SQLite

Set the boolean `MOSS_USE_SQLITE=true` in `.env` to use SQLite without a separate database service. The configuration script can set it for you:

```sh
python3 scripts/configure.py --sqlite
docker compose up --build -d
```

SQLite stores the database at `/data/mosscms.db` in the persistent `moss_assets` volume, alongside local uploads. The flag overrides `DATABASE_URL` and PostgreSQL settings. Normal starts and upgrades need no additional flags. Compose replaces any existing Postgres container with a container that exits immediately, preserving its database volume. No Postgres process runs in SQLite mode.

For production, use `python3 scripts/configure.py --sqlite --production --public-url https://cms.example.com`. Use one app instance with SQLite; choose PostgreSQL for multiple app instances or heavy concurrent writes. Switching backends selects a separate database; it does not transfer existing content. See [SQLite backup and recovery](docs/deployment-recovery.md#sqlite-backup-and-recovery).

<details>
<summary>Existing starter database or optional sample content</summary>

To choose another local port, use `python3 scripts/start.py --port 8002`. Configuration aligns the public URL, trusted browser origins and host port. `--public-url http://localhost:8002` also aligns a local bind; production reverse-proxy origins remain independent.

For an existing starter database, use `python3 scripts/configure.py --existing-db` before upgrading. This preserves its development password. The migration imports existing Articles and revisions into a workspace assigned to the first administrator, retaining the original table. Do not use starter database credentials in production.

There is no automatic seed. After setup, an optional repeatable seed command is:

```sh
docker compose exec app python -m app.cli seed --project YOUR_WORKSPACE_ID
```

</details>

### Run a published Docker Hub image

The configured image repository is `nirtuttnauer/mosscms`. Registry publication depends on repository configuration; the source-build quickstart above does not require a published image. Images include the API and built admin, with the database mode selected by Compose. Once an image has been [published to Docker Hub](docs/docker.md#publish-to-docker-hub), run these commands from the cloned repository to start without building locally:

```sh
python3 scripts/configure.py
docker compose pull app db
docker compose up --no-build -d --wait app
```

Open [localhost:8001](http://localhost:8001) and use `MOSS_SETUP_TOKEN` from `.env` to create the first administrator. Database and uploaded files persist in the same named volumes as a local build.

Compose defaults to `nirtuttnauer/mosscms:latest`. Set `MOSS_IMAGE` in `.env` to an existing published tag or digest for a repeatable deployment. When registry publishing is configured, the workflow updates `latest` from `main` and creates version tags from matching Git tags. Git tags use a `vMAJOR.MINOR.PATCH` pattern; image tags omit the leading `v`. Its build targets are Linux AMD64 and ARM64. Use `MOSS_PORT` to change the host port; the container listens on 8001.

To build from your checkout, keep using `docker compose up --build -d`. To avoid replacing a locally cached release tag, use `MOSS_IMAGE=mosscms:local docker compose up --build -d`. The optional example website is built separately with `docker compose --profile website up --build -d example-site`.

See [Docker setup and publishing](docs/docker.md) for registry configuration and upgrade instructions.

## How it fits together

The admin uses the editorial API to manage a workspace. Your frontend reads its published content through the separate delivery API. The optional example website demonstrates keeping the delivery token on the frontend's server.

```mermaid
flowchart LR
    Admin["React admin"] -->|"Session and workspace"| Editorial
    Frontend["Your frontend server"] -->|"Scoped delivery token"| Delivery
    subgraph Moss["MossCMS · one Docker image / origin"]
        Editorial["Editorial GraphQL<br/>/graphql"] --> Content["Content, permissions<br/>and publication workers"]
        Delivery["Delivery GraphQL<br/>/delivery/graphql"] --> Content
    end
    Content --> Database[("PostgreSQL or SQLite<br/>content, accounts, revisions")]
    Content --> Media["Media storage<br/>local volume or private S3"]
```

**Stack:** FastAPI, Strawberry GraphQL, SQLAlchemy, and Alembic on Python; Vite, React, TypeScript, Tailwind, and Radix/shadcn-style components in the admin. Python dependencies use **uv**; Node dependencies use **npm**.

## Your first content

1. **Choose a workspace.** Use the workspace menu in the sidebar. Administrators can create or rename workspaces in **Settings**.
2. **Define a content type.** Open **Content types** and create an `article` type. Add a required text field named `title` and a rich text field named `body`. Save the schema. The [field definition example](#define-data) shows nested objects, lists, locales, references, and assets.
3. **Write an entry.** Open **Content**, select your Article group, and choose **New entry**. Enter a slug such as `hello-world`, fill in the title, and write the body. **Save draft** keeps the entry private; the editor also autosaves changes.
4. **Add media.** Upload an image in **Assets**, then insert it through the Markdown editor's image picker or an asset field. Markdown stores durable asset IDs, so expiring download links are refreshed when content is read.
5. **Publish.** Choose **Immediate publication**, then confirm with **Publish now** to make the entry live. To publish later, use **Schedule publication** and select a date in your browser's timezone. Later draft edits preserve the live version and captured schedule. **Publications** shows the queue and failed publications.
6. **Connect a frontend.** Use **Create token & verify delivery** in the getting-started guide to create a 90-day token scoped to `article`, or create a token in **Settings**. Copy it once, keep it on your server, and query published content:

```sh
export MOSS_DELIVERY_TOKEN='YOUR_DELIVERY_TOKEN'
curl http://localhost:8001/delivery/graphql \
  -H "Authorization: Bearer $MOSS_DELIVERY_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"query":"{ entries(typeKey: \"article\", first: 10) { nodes { id slug data } } }"}'
```

The getting-started checklist in **Content** guides you through defining a type, drafting an entry, publishing, and verifying a delivery query. For a complete frontend integration, use the [example website](example-site/README.md).

<p>
  <img src="docs/acceptance-2026-10-11/editor-mobile.jpg" alt="MossCMS mobile editor showing a live article with unpublished draft changes" width="280" />
</p>

The editor works on mobile, keeps draft and live states visible, and guards unsaved changes. See [editor workflows](docs/editor-workflows.md), [Markdown and images](docs/markdown.md), and [publishing semantics](docs/publication-contract.md) for detailed guides.

## Temporarily skip sign-in

Set `MOSS_SKIP_AUTH=true` in `.env`, then run `docker compose up --build -d app`.
The admin opens as **Local developer** with administrator access to all workspaces.
This flag is accepted only with `MOSS_ENV=development`; the UI shows “Local development”.
Delivery tokens and mutation CSRF checks remain in place.

Set `MOSS_SKIP_AUTH=false` and recreate the app to restore normal sign-in.
The local development identity has no usable password or session, and it does not count as the first administrator.
Existing content is retained. If you have not created a real administrator yet, the setup screen returns when the flag is disabled.

## Admin and teams

- Overview: live counts and service health.
- Content types: create field schemas, inspect history, and explicitly migrate existing data.
- Content: create/edit entries, drafts, publish/schedule, cursor pagination, filters, recoverable trash, and revision preview/restore.
- Assets: upload local or S3 media and obtain expiring download links.
- Team: invite by email, copy/revoke invitation links, change roles, remove access. Invitations expire after seven days.
- Settings: create/rename workspaces, connect OAuth accounts, create/revoke delivery tokens, and inspect audit history.
- API explorer: query the selected workspace or use a delivery token.

| Role | Access within a workspace |
| --- | --- |
| Administrator | Manage schemas, membership, tokens, entries, and media |
| Editor | Manage entries and media; publish and schedule content |
| Reader | View editorial content, including drafts; cannot edit or publish |

Every record and query is scoped to workspace membership. At least one administrator must remain. Invitations are shared manually; no email service is required.

Password recovery is available to the server operator:

```sh
docker compose exec app python -m app.cli reset-password --email person@example.com
```

Share the resulting one-time recovery link privately with that account owner. It expires after one day and successful recovery revokes existing sessions.

## OAuth sign-in

See [the provider setup guide](docs/oauth-setup.md) for GitHub, Google, and generic OIDC registration with exact local callback URLs.

Configure either or both providers in `.env`, then recreate the app with `docker compose up -d`.

| Provider | Variables | Registered callback URL |
| --- | --- | --- |
| GitHub OAuth app | `MOSS_GITHUB_CLIENT_ID`, `MOSS_GITHUB_CLIENT_SECRET` | `MOSS_PUBLIC_URL/auth/oauth/github/callback` |
| OpenID Connect provider | `MOSS_OIDC_DISCOVERY_URL`, `MOSS_OIDC_CLIENT_ID`, `MOSS_OIDC_CLIENT_SECRET`, optional `MOSS_OIDC_NAME` | `MOSS_PUBLIC_URL/auth/oauth/oidc/callback` |

Use the provider's discovery document URL and enable `openid email profile` scopes. OIDC must return a verified email. GitHub sign-in also requires a verified email. Provider buttons appear when configuration is present.

Create the first account locally. Existing users connect their provider in **Settings** while signed in. New users follow a matching email invitation and choose their provider. Matching emails never silently link existing accounts. OAuth state is validated; OIDC additionally validates ID-token signature, issuer, audience, nonce, and uses PKCE. Provider credentials and real provider callbacks must be configured on your own instance.

## Define data

Create a type with key `article` and a field definition such as:

```json
[
  {"name":"title","type":"text","required":true},
  {"name":"body","type":"richText","localized":true},
  {"name":"category","type":"enum","options":["news","guide"]},
  {"name":"tags","type":"list","item":{"type":"text"}},
  {"name":"seo","type":"object","fields":[{"name":"description","type":"text"}]},
  {"name":"related","type":"reference","target":"article"},
  {"name":"cover","type":"asset"},
  {"name":"internalNotes","type":"text","private":true}
]
```

Supported types: text, richText (Markdown stored as a string), number, boolean, date (`YYYY-MM-DD`), enum, object, list, reference, asset. Localized fields contain locale maps, for example `{"en":"Hello","he":"שלום"}`. References and assets store IDs belonging to the same workspace. Private fields are removed from delivery schemas and values, including nested objects/lists. Slugs are normalized and unique within a content type.

Schema updates validate every stored entry and published snapshot in one transaction. For incompatible changes, provide an explicit migration, for example `{"rename":{"oldName":"newName"},"defaults":{"requiredField":"value"},"drop":["obsolete"]}`. Schema and entry changes retain revisions. Entry updates require the current `version` to prevent overwriting concurrent edits. Restoring a revision creates a new draft and validates it against the current schema.

Workspace administrators can use **Import & export** in the sidebar or Settings to download archives, upload into an empty workspace, edit ordered rename/default/drop/conversion steps, customize destination schemas visually, and review a dry run before confirming import. The server requires a matching signed validation of the archive/pipeline, destination, and administrator. The same format is available through `python -m app.cli export` and `python -m app.cli import`; `--pipeline` selects transforms and `--apply` commits drafts. Archives include actual media bytes and checksums, consistently remap references, and preserve source publication states/history as provenance. Private fields are omitted unless explicitly selected. See [UI instructions, commands, pipeline examples, and limits](docs/portable-content-format.md).

Content is grouped by its schema type in the Content library. Each group shows its entry count and opens a filtered list; **New entry** uses the selected type. Create additional types in **Content types** to organize other collections. The example website includes separate Projects, Blog posts, Website page, Homepage slide, and Website profile groups.

Administrators can use the editorial `moveEntry(id, typeKey, version)` mutation to move compatible entries between schema types. It validates both editable and published data against the target schema and retains the entry ID, schedule, status, revision history and audit trail. Slug conflicts or incompatible data reject the move. The website setup script uses this to upgrade older projects and posts stored as Website pages.

## Draft, live, and scheduled content

An entry can have all three versions at once. Saving a draft changes the working copy; publishing or scheduling captures a specific revision.

```mermaid
flowchart LR
    Draft["Working draft"] -->|"Save / autosave"| Draft
    Draft -->|"Publish now"| Live["Live snapshot"]
    Draft -->|"Schedule / replace schedule"| Scheduled["Captured scheduled revision"]
    Scheduled -->|"Due and valid"| Live
    Scheduled -->|"Validation or URL conflict"| Failed["Failed capture<br/>previous live content preserved"]
    Failed -->|"Repair and retry capture"| Scheduled
    Live -->|"Public fields only"| Delivery["Delivery API"]
```

| Action | Live content | Captured schedule |
| --- | --- | --- |
| Save draft / autosave | Preserved | Preserved |
| Publish now | Replaced with the selected working revision | Cleared |
| Schedule / replace schedule | Preserved | Captures the selected revision and UTC due time |
| Cancel schedule | Preserved | Cleared |
| Unpublish | Removed; working draft and history retained | Cleared |

Later edits do not change a captured schedule. The scheduler checks about every five seconds and on startup; the CMS must stay running. Dates display in your browser's timezone. Failed captures appear in **Publications**, where editors can retry the captured revision, replace it, or discard it. [Editor workflows](docs/editor-workflows.md) covers recovery and previews; the [publication contract](docs/publication-contract.md) defines every transition.

## GraphQL for your frontends

Create a delivery token in Settings. Tokens expire and can be scoped to selected content types. Keep privileged tokens in your frontend server's environment. A token embedded in a browser is accessible to its users and should expose only content you intend them to read.

| Endpoint | Authentication | Content and operations |
| --- | --- | --- |
| `POST /delivery/graphql` | Bearer delivery token | Published content in token scope; public fields; queries only |
| `POST /graphql` | Session, `X-Moss-Project`; `X-Moss-CSRF` for mutations | Workspace content, drafts, and revisions according to role; queries and mutations |

The example website uses this request flow (the diagram omits its cache and preview handling):

```mermaid
sequenceDiagram
    participant Visitor as Website visitor
    participant Site as Frontend server
    participant CMS as MossCMS delivery API
    Visitor->>Site: Request website content
    Site->>CMS: POST /delivery/graphql + Bearer token
    Note over CMS: Enforce token scope, read live snapshots,<br/>remove private fields
    CMS-->>Site: Published content + signed media URLs
    Site-->>Visitor: Public website content
    Note over Site: Delivery token stays on the server
```

**POST `/delivery/graphql`** with `Authorization: Bearer YOUR_TOKEN` reads published content only and has no mutations. Type `article` generates `allCmsArticle` with schema-derived fields:

```graphql
query {
  allCmsArticle(first: 20) {
    id
    slug
    title
    body(locale: "en")
    category
    cover { id name url }
    related { id entry { slug data } }
  }
}
```

Use the generic connection for pagination, sorting, search, and exact scalar field filters:

```graphql
query Articles($after: String) {
  entries(typeKey: "article", first: 20, after: $after,
          sort: "title_asc", filters: {category: "news"}) {
    nodes { id slug data }
    total
    endCursor
    hasNextPage
  }
}
```

`first` is capped at 100. Legacy sorts are `updated_desc`, `updated_asc`, `title_asc`, `title_desc`. To sort a scalar schema field, supply a content type and `orderBy: {field: "price", direction: ASC}` (or `DESC`) instead of `sort`. Null/missing values appear last; IDs break ties. The editor offers these field sorts after choosing a content type. Omit `total` to avoid counting the entire result set. Delivery title search/sort uses public slugs to avoid private title exposure. Queries are limited to depth 12, 200 expanded fields, and 30,000 characters. Delivery responses use authenticated private caching with ETags and support `If-None-Match`; signed media URLs expire after 15 minutes. Errors include machine-readable `extensions.code`.

Exact filters on top-level, non-localized scalar fields use [automatically maintained indexes](docs/automatic-indexing.md), with separate draft and live values. Migrations 0011–0013 backfill filtering/ordering values and compact supported scalar projections; no per-field index configuration is needed. Null/missing comparisons and cross-type coercions retain the original query path. Indexing adds storage and write work; substring search, nested/localized fields and multi-field ordering remain outside this scope.

**POST `/graphql`** is editorial: authenticated session, `X-Moss-Project` workspace ID, and `X-Moss-CSRF` for mutations. `/auth/me` returns membership and CSRF information. Drafts and historical revisions are available according to role; delivery tokens cannot authenticate to this endpoint. `GET /graphql` opens the admin API explorer.

## Storage and production

Local files persist in the `moss_assets` volume. For S3-compatible storage configure `MOSS_S3_BUCKET`, optional `MOSS_S3_ENDPOINT`, AWS credentials, and region. Keep the bucket private. Download links are signed; S3 URLs use the SDK's presigning. Existing asset records retain their storage backend, so preserve local files when switching to S3.

For a fresh production instance:

```sh
python3 scripts/configure.py --production --public-url https://cms.example.com
docker compose up --build -d
```

Terminate TLS at a reverse proxy and proxy to the default `127.0.0.1:8001` binding. Set `MOSS_PUBLIC_URL` to the canonical HTTPS origin and `MOSS_ORIGINS` to an explicit comma-separated list of trusted HTTPS browser origins. Avoid wildcard CORS. PostgreSQL has no published host port. The app runs without root, with a read-only root filesystem and separate writable media/temp volumes. Production rejects missing secrets, SQLite without `MOSS_USE_SQLITE=true`, default PostgreSQL passwords, and HTTP origins.

For an existing database, changing `.env` alone does not rotate its password: change the PostgreSQL role password through an operator connection and update `.env` together. Preserve secret values for upgrades. Changing `MOSS_SECRET_KEY` invalidates pending OAuth state and signed media links. Protect database backups because they include account/session data.

Health: `/health` is process health, `/ready` checks the database, Docker checks `/ready`. `/metrics` requires an administrator session/project. Logs include request IDs and request timing; query strings containing invitation or OAuth tokens are omitted. Shutdown waits for scheduler/webhook work and closes database connections. Configure signed publication callbacks and website cache invalidation using [deployment guidance](docs/deployment-recovery.md) and [the webhook protocol](docs/webhooks.md). Unknown static paths return 404 and `/` supports HEAD.

Optional [OpenTelemetry](docs/observability.md) exports HTTP/GraphQL/SQL/worker traces and latency histograms through OTLP HTTP. It includes GraphQL errors returned with HTTP 200 and log/trace correlation, without content, query variables, SQL text or bind values. Enable it with `MOSS_OTEL_ENABLED=true` and `OTEL_EXPORTER_OTLP_ENDPOINT`, or use the local [Collector overlay](compose.observability.yaml). The guide includes p95, error-rate and SQL-per-request queries; telemetry is disabled by default.

## Backup, restore, and upgrades

```sh
docker compose stop app
python3 scripts/backup.py
docker compose up -d --no-build app
```

Creates timestamped PostgreSQL custom-format dumps and local media archives under `backups/`, with restrictive permissions. Stopping the app pauses editorial writes, scheduling and webhook workers. Media backup uses a temporary container without application startup; stop the website too if it is in use. For S3, separately enable object versioning and back up the bucket; the local archive does not contain S3 objects.

For SQLite, use the [SQLite backup and recovery procedure](docs/deployment-recovery.md#sqlite-backup-and-recovery) instead of the PostgreSQL dump tools. The database and local media form one archive of `/data`.

Restore into an **existing empty database** on the Compose database service:

```sh
docker compose exec db sh -c 'createdb -U "$POSTGRES_USER" mosscms_recovery'
python3 scripts/restore.py backups/TIMESTAMP.dump --target mosscms_recovery --confirm-target mosscms_recovery
```

The restore tool refuses non-empty databases and restores transactionally. Restore local assets into a **new empty** `/data` volume using `python3 scripts/restore_media.py backups/TIMESTAMP.media.tar.gz --confirm-empty-volume` before application startup. It validates archive paths and rejects links and existing files. Select the matching retained image and recovered database/media through [the recovery guide](docs/deployment-recovery.md#restore-a-matched-backupimage-pair). Keep the original database/volume until recovery is confirmed; preserve matching private configuration and storage settings.

Upgrade procedure: save a working source/image version, stop writers and back up database/media, update dependencies/source, build the image, and run `docker compose up -d --build`. Alembic migrations run before serving; PostgreSQL advisory locks serialize concurrent migration attempts. Confirm `/ready`, sign-in, content counts, and delivery access. Rollback restores the previous database/media backup together with the matching application image/configuration; do not downgrade the schema alone. Never delete the data volume during an upgrade. Legacy data and the independent-snapshot migration are covered by tests and a restored-database rehearsal.

Node/Python image digests and Python/npm lockfiles pin builds. To update, deliberately change image digests and dependency ranges, regenerate both locks, run the checks below, review advisories, and rehearse the upgrade on a restored database. PostgreSQL remains pinned to major 17; update its image within that major deliberately. A major PostgreSQL upgrade requires `pg_upgrade` or dump/restore into a new volume.

## Code layout

| Area | Start here | Responsibility |
| --- | --- | --- |
| Content model | [schema.py](api/app/schema.py), [content.py](api/app/content.py), [graphql.py](api/app/graphql.py) | Field validation, private-field filtering, workspace queries, revisions, migrations, and publication transitions |
| HTTP and query limits | [main.py](api/app/main.py), [query_limits.py](api/app/query_limits.py) | Request handling, GraphQL depth, selection count, and fragment traversal |
| Accounts and persistence | [accounts.py](api/app/accounts.py), [security.py](api/app/security.py), [models.py](api/app/models.py), [migrations/](api/migrations/) | Permissions, sessions, tokens, database models, and Alembic migrations |
| Media | [media_links.py](api/app/media_links.py), [storage.py](api/app/storage.py), [images.py](api/app/images.py) | Signed original/variant links, upload/download operations, bounded decoding, and image variants |
| Admin | [pages/](web/src/pages/), [components/](web/src/components/), [lib/](web/src/lib/) | Screens, controls, API requests, locale/entry validation, and autosave recovery |
| Editor and revisions | [Content.tsx](web/src/pages/Content.tsx), [EntryEditor.tsx](web/src/pages/EntryEditor.tsx), [revisions.ts](web/src/lib/revisions.ts) | Content library, shared entry editor, and revision comparison |
| Example website | [src/](example-site/src/), [server/](example-site/server/) | Public components, delivery loading, cache, previews, publication events, routes, and metadata |
| Shared and operator tools | [shared/](shared/), [scripts/](scripts/) | Markdown policy, website routes, configuration, backup/restore, and release acceptance |

API tests live in `api/tests/`; admin and website server tests sit beside the code they exercise. Keep schema validation and public-data filtering shared between editorial saves, scheduled publication, delivery, and preview.

The [maintainability review](docs/maintainability-review.md) records refactors, retained boundaries, checks, and untested integrations. Operator and release-script safeguard tests also run with the API suite.

## SEO audit

Use **SEO audit** to review draft and live records separately, inspect detected SEO field mappings, and follow prioritized findings into the editor. Checks are advisory and leave publishing available. Website rendering and indexing remain unverified. See [SEO audit rules and API](docs/seo-audit.md).

## Local development and checks

Install **Python 3.12+ with uv** and **Node.js 22.12+ with npm**. The Node minimum follows Vite's checked-in engine requirement. Generate `.env` with `python3 scripts/configure.py` first. In separate terminals, starting from the repository root:

```sh
cd api
uv sync --locked --group dev
uv run uvicorn app.main:app --reload --port 8001
```

```sh
cd web
npm ci
npm run dev
```

Open the admin at [localhost:5173](http://localhost:5173). Local API development defaults to SQLite; set `DATABASE_URL` to use PostgreSQL. Vite proxies API/auth/media endpoints to port 8001. Ensure `http://localhost:5173` is in development `MOSS_ORIGINS`. For a different API port, pass that port to Uvicorn and set `VITE_BACKEND_URL=http://localhost:YOUR_PORT` before `npm run dev`.

```sh
cd api
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run ruff check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run ruff format --check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run mypy app
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=sqlite uv run pytest -m "not postgres"
```

The API suite uses isolated temporary databases. `MOSS_USE_SQLITE=false` keeps the application’s local `.env` backend selection from overriding those test databases; SQLite-specific tests enable their own configuration. A skip or xfail at runtime fails the run; there is no allowed-skip list. PostgreSQL-only tests carry the `postgres` marker and are excluded from the SQLite run before collection with `-m "not postgres"`. Docker Compose tests carry the `compose` marker and run in both required runs. The deselected test ids are committed in [api/tests/required_runs.json](api/tests/required_runs.json) and checked against each run. To run the PostgreSQL required run (JSON path casts, `SKIP LOCKED`, and advisory locks), point it at an admin connection; each test uses its own throwaway database and is cleaned up afterward. Install Docker Compose first so the compose tests execute:

```sh
MOSS_USE_SQLITE=false MOSS_REQUIRED_RUN=postgres MOSS_TEST_DATABASE_URL='postgresql+psycopg://USER:***@HOST:5432/DB' uv run pytest
uv run python tests/verify_required_runs.py
```

```sh
cd web
npm run check
npm test
npm run build
npm audit --audit-level=high
```

```sh
cd example-site
npm run check
npm test
npm run build
npm audit --audit-level=high
```

CI runs the same checks. Tests cover authorization and workspace boundaries, token scopes/drafts/private fields, team roles, recovery, schema changes, revisions, scheduling, assets, generated GraphQL types, legacy migration, and core frontend interactions. External OAuth and S3 services require your credentials; unit coverage does not establish that a particular provider or bucket is configured correctly.

## Example website frontend

[example-site/](example-site/README.md) is a standalone Vite + React frontend with generic starter content. It demonstrates projects, blog posts, editable pages, Markdown, media, draft previews, and a configurable home showcase. A Node server keeps the delivery token private and reads published content through `/delivery/graphql`.

With the CMS running and normal sign-in enabled, run from the repository root. The setup command prompts for your administrator email and password:

```sh
python3 example-site/scripts/setup_moss.py
docker compose --profile website up --build -d example-site
```

Open [localhost:5174](http://localhost:5174). Select **Example website** in the CMS workspace menu to edit its content. The setup script creates five content types, sample entries, and a scoped server-only delivery token in the ignored `example-site/.env`; rerunning it preserves edits.

The workspace belongs to the administrator who ran setup; no authentication bypass is needed. For local Vite development, deployment to your own domain, and signed publication events, follow the [example site guide](example-site/README.md).

If an older bypass setup left the workspace without members, recover only that workspace with `docker compose exec app python -m app.cli claim-workspace --project WORKSPACE_ID --email ADMIN_EMAIL`. The operator command refuses any workspace that already has members.

## Documentation

| If you want to… | Read |
| --- | --- |
| Run or publish a Docker image | [Docker setup and publishing](docs/docker.md) |
| Operate, upgrade, or recover an instance | [Deployment and recovery](docs/deployment-recovery.md) |
| Understand autosave, conflicts, revisions, or draft previews | [Editor workflows](docs/editor-workflows.md) |
| Understand publishing and scheduling guarantees | [Publication contract](docs/publication-contract.md) |
| Work with Markdown, images, or storage limits | [Markdown](docs/markdown.md), [images](docs/images.md) |
| Configure provider sign-in or publication callbacks | [OAuth setup](docs/oauth-setup.md), [webhook protocol](docs/webhooks.md) |
| Build a frontend or inspect SEO findings | [Example website](example-site/README.md), [SEO audit](docs/seo-audit.md) |
| Stream delivery content or evaluate capacity and cost | [Typed delivery client](docs/delivery-client.md), [benchmark guide](docs/benchmarks/README.md), [measured results](docs/benchmarks/RESULTS-2026-10-12.md) |
| Understand automatic exact-filter indexing and repairs | [Automatic indexing](docs/automatic-indexing.md) |
| Measure latency, GraphQL failures and database bottlenecks | [OpenTelemetry setup and performance queries](docs/observability.md) |
| Contribute or understand implementation boundaries | [Contributing](CONTRIBUTING.md), [maintainability review](docs/maintainability-review.md) |

<a id="product-plan"></a>

## Roadmap and evidence

[Competitive roadmap](docs/planning/COMPETITIVE-ROADMAP-2026-10-12.md) · [Implementation follow-ups](docs/planning/COMPETITIVE-IMPLEMENTATION-2026-10-12.md) · [Scaling plan](docs/planning/PERFORMANCE-SCALING-2026-10-12.md)

[Open issues](https://github.com/nirtuttnauer/MossCMS/issues) and [pull requests](https://github.com/nirtuttnauer/MossCMS/pulls) track ongoing work. The [PRD](docs/PRD.md) and [task breakdown](docs/planning/TASKS.md) preserve product intent; the [implementation ledger](docs/planning/IMPLEMENTATION.md) and [release evidence](docs/release-acceptance-2026-10-08.md) are historical checkpoints. Use the current code, tests, and workflow guides to determine what a particular checkout supports.

<details>
<summary>Planning history</summary>

The [PRD](docs/PRD.md) retains the 7 October baseline and records the approved release scope. The [task breakdown](docs/planning/TASKS.md) includes acceptance criteria and dependencies. All 34 baseline tasks were approved on 8 October 2026 and implemented sequentially on feature branches integrated into local `main`. The [implementation ledger](docs/planning/IMPLEMENTATION.md) and [release evidence](docs/release-acceptance-2026-10-08.md) record the result. The original Markdown/JSON plan preserves the historical proposal snapshot; consult the implementation and acceptance documents for delivered behavior.

</details>
