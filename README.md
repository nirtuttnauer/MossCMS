<p align="center">
  <img src="web/public/brand/moss-symbol-v2.png" alt="MossCMS logo" width="160" />
</p>

# MossCMS

A self-hosted content service with a GraphQL API and a React admin. Define your data, publish entries, and consume them from any frontend. Python dependencies use **uv**; the admin uses **Vite, React, TypeScript, Tailwind, and Radix/shadcn-style components**. The multistage Docker image serves both from one origin, backed by PostgreSQL.

[MIT licensed](LICENSE). Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

[![Checks](https://github.com/nirtuttnauer/MossCMS/actions/workflows/checks.yml/badge.svg)](https://github.com/nirtuttnauer/MossCMS/actions/workflows/checks.yml)

![MossCMS content library and getting-started checklist](docs/acceptance-2026-10-11/first-use-three-ready.jpg)

Model content visually, write with Markdown, upload media, and publish immediately or on a schedule. Drafts stay separate from live content. Each workspace has its own schemas, team, and delivery tokens.

[Start locally](#start) · [First content walkthrough](#your-first-content) · [Run the example site](#example-website-frontend) · [Delivery API](#graphql-for-your-frontends) · [Production setup](#storage-and-production)

## Start

Install Docker with Compose and Python 3, then clone the repository:

```sh
git clone https://github.com/nirtuttnauer/MossCMS.git
cd MossCMS
```

```sh
python3 scripts/configure.py
docker compose up --build -d
```

Open [localhost:8001](http://localhost:8001). Create your first administrator using `MOSS_SETUP_TOKEN` from `.env`. Choose your own email and a password of at least 12 characters. Configuration is generated locally with random secrets; `.env` is excluded from builds and source control.

For an existing starter database, use `python3 scripts/configure.py --existing-db` before upgrading. This preserves its development password. The migration imports existing Articles and revisions into a workspace assigned to the first administrator, retaining the original table. Do not use starter database credentials in production.

There is no automatic seed. After setup, an optional repeatable seed command is:

```sh
docker compose exec app python -m app.cli seed --project YOUR_WORKSPACE_ID
```

## Your first content

1. **Choose a workspace.** Use the workspace menu in the sidebar. Administrators can create or rename workspaces in **Settings**.
2. **Define a content type.** Open **Content types** and create an `article` type. Add a required text field named `title` and a rich text field named `body`. Save the schema. The [field definition example](#define-data) shows nested objects, lists, locales, references, and assets.
3. **Write an entry.** Open **Content**, select your Article group, and choose **New entry**. Enter a slug such as `hello-world`, fill in the title, and write the body. **Save draft** keeps the entry private; the editor also autosaves changes.
4. **Add media.** Upload an image in **Assets**, then insert it through the Markdown editor's image picker or an asset field. Markdown stores durable asset IDs, so expiring download links are refreshed when content is read.
5. **Publish.** Choose **Publish now** to make the entry live. To publish later, use **Schedule publication** and select a date in your browser's timezone. Later draft edits preserve the live version and captured schedule. **Publications** shows the queue and failed publications.
6. **Connect a frontend.** In **Settings**, create a delivery token scoped to `article`. Copy it once, keep it on your server, and query published content:

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

**Administrators** manage schemas, membership, and tokens. **Editors** manage entries and media. **Readers** view editorial content including drafts. Every record and query is scoped to workspace membership. At least one administrator must remain. Invitations are shared manually; no email service is required.

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

Content is grouped by its schema type in the Content library. Each group shows its entry count and opens a filtered list; **New entry** uses the selected type. Create additional types in **Content types** to organize other collections. The example website includes separate Projects, Blog posts, Website page, Homepage slide, and Website profile groups.

Entries have independent working, live and scheduled versions. **Save draft** and autosave preserve existing live content and captured schedules. **Publish now** replaces the complete live snapshot. **Schedule / Replace schedule** freezes the selected revision and UTC due time; later draft edits do not alter it. Use explicit **Cancel schedule** or **Unpublish** actions. The scheduler checks about every five seconds and on startup. Failed captures preserve live content and appear in **Publications**, where editors can retry the captured revision, replace it or discard it. Dates display the browser timezone. See [editor workflows](docs/editor-workflows.md) for autosave recovery, Markdown, media, saved website previews and schema tools, and [the publication contract](docs/publication-contract.md) for API transition semantics.

Administrators can use the editorial `moveEntry(id, typeKey, version)` mutation to move compatible entries between schema types. It validates both editable and published data against the target schema and retains the entry ID, schedule, status, revision history and audit trail. Slug conflicts or incompatible data reject the move. The website setup script uses this to upgrade older projects and posts stored as Website pages.

## GraphQL for your frontends

Create a delivery token in Settings. Tokens expire and can be scoped to selected content types. Keep privileged tokens in your frontend server's environment. A token embedded in a browser is accessible to its users and should expose only content you intend them to read.

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

`first` is capped at 100. Sorts are `updated_desc`, `updated_asc`, `title_asc`, `title_desc`. Delivery title search/sort uses public slugs to avoid private title exposure. Queries are limited to depth 12, 200 expanded fields, and 30,000 characters. Delivery responses use authenticated private caching with ETags and support `If-None-Match`; signed media URLs expire after 15 minutes. Errors include machine-readable `extensions.code`.

**POST `/graphql`** is editorial: authenticated session, `X-Moss-Project` workspace ID, and `X-Moss-CSRF` for mutations. `/auth/me` returns membership and CSRF information. Drafts and historical revisions are available according to role; delivery tokens cannot authenticate to this endpoint. `GET /graphql` opens the admin API explorer.

## Storage and production

Local files persist in the `moss_assets` volume. For S3-compatible storage configure `MOSS_S3_BUCKET`, optional `MOSS_S3_ENDPOINT`, AWS credentials, and region. Keep the bucket private. Download links are signed; S3 URLs use the SDK's presigning. Existing asset records retain their storage backend, so preserve local files when switching to S3.

For a fresh production instance:

```sh
python3 scripts/configure.py --production --public-url https://cms.example.com
docker compose up --build -d
```

Terminate TLS at a reverse proxy and proxy to the default `127.0.0.1:8001` binding. Set `MOSS_PUBLIC_URL` to the canonical HTTPS origin and `MOSS_ORIGINS` to an explicit comma-separated list of trusted HTTPS browser origins. Avoid wildcard CORS. PostgreSQL has no published host port. The app runs without root, with a read-only root filesystem and separate writable media/temp volumes. Production rejects missing secrets, SQLite, default PostgreSQL passwords, and HTTP origins.

For an existing database, changing `.env` alone does not rotate its password: change the PostgreSQL role password through an operator connection and update `.env` together. Preserve secret values for upgrades. Changing `MOSS_SECRET_KEY` invalidates pending OAuth state and signed media links. Protect database backups because they include account/session data.

Health: `/health` is process health, `/ready` checks the database, Docker checks `/ready`. `/metrics` requires an administrator session/project. Logs include request IDs and request timing; query strings containing invitation or OAuth tokens are omitted. Shutdown waits for scheduler/webhook work and closes database connections. Configure signed publication callbacks and website cache invalidation using [deployment guidance](docs/deployment-recovery.md) and [the webhook protocol](docs/webhooks.md). Unknown static paths return 404 and `/` supports HEAD.

## Backup, restore, and upgrades

```sh
docker compose stop app
python3 scripts/backup.py
docker compose up -d --no-build app
```

Creates timestamped PostgreSQL custom-format dumps and local media archives under `backups/`, with restrictive permissions. Stopping the app pauses editorial writes, scheduling and webhook workers. Media backup uses a temporary container without application startup; stop the website too if it is in use. For S3, separately enable object versioning and back up the bucket; the local archive does not contain S3 objects.

Restore into an **existing empty database** on the Compose database service:

```sh
docker compose exec db sh -c 'createdb -U "$POSTGRES_USER" mosscms_recovery'
python3 scripts/restore.py backups/TIMESTAMP.dump --target mosscms_recovery --confirm-target mosscms_recovery
```

The restore tool refuses non-empty databases and restores transactionally. Restore local assets into a **new empty** `/data` volume using `python3 scripts/restore_media.py backups/TIMESTAMP.media.tar.gz --confirm-empty-volume` before application startup. It validates archive paths and rejects links and existing files. Select the matching retained image and recovered database/media through [the recovery guide](docs/deployment-recovery.md#restore-a-matched-backupimage-pair). Keep the original database/volume until recovery is confirmed; preserve matching private configuration and storage settings.

Upgrade procedure: save a working source/image version, stop writers and back up database/media, update dependencies/source, build the image, and run `docker compose up -d --build`. Alembic migrations run before serving; PostgreSQL advisory locks serialize concurrent migration attempts. Confirm `/ready`, sign-in, content counts, and delivery access. Rollback restores the previous database/media backup together with the matching application image/configuration; do not downgrade the schema alone. Never delete the data volume during an upgrade. Legacy data and the independent-snapshot migration are covered by tests and a restored-database rehearsal.

Node/Python image digests and Python/npm lockfiles pin builds. To update, deliberately change image digests and dependency ranges, regenerate both locks, run the checks below, review advisories, and rehearse the upgrade on a restored database. PostgreSQL remains pinned to major 17; update its image within that major deliberately. A major PostgreSQL upgrade requires `pg_upgrade` or dump/restore into a new volume.

## Code layout

- `api/app/schema.py`: field definitions, value validation, private-field filtering, and referenced asset IDs. `content.py` handles workspace-scoped queries, revisions, schema migrations, and publication transitions; `graphql.py` exposes them through editorial and delivery schemas.
- `api/app/query_limits.py`: GraphQL depth, selection count, and fragment traversal checks. `main.py` applies them before executing editorial or delivery requests.
- `api/app/accounts.py` and `security.py`: accounts, workspace permissions, sessions, and tokens. Database models live in `models.py`; database migrations live in `api/migrations/`.
- `api/app/media_links.py`: original/variant media signing and expiry policy. `storage.py` handles upload/download operations; `images.py` handles bounded image decoding and variants.
- `web/src/pages/` and `web/src/components/`: admin screens and form controls. `web/src/lib/` contains API requests, schema helpers, shared locale/entry validation, and autosave recovery.
- `web/src/pages/Content.tsx` owns the content library; `EntryEditor.tsx` is shared by the content and publication screens. `web/src/lib/revisions.ts` builds field differences for the revision comparison component.
- `example-site/src/`: public website components. `example-site/server/`: delivery loading, cache, preview sessions, publication events, routes, and metadata.
- `shared/`: Markdown rendering policy and website routes shared across consumers. `scripts/`: operator configuration, backup/restore, and release acceptance tools.

API tests live in `api/tests/`; admin and website server tests sit beside the code they exercise. Keep schema validation and public-data filtering shared between editorial saves, scheduled publication, delivery, and preview.

The [maintainability review](docs/maintainability-review.md) records refactors, retained boundaries, checks, and untested integrations. Operator and release-script safeguard tests also run with the API suite.

## SEO audit

Use **SEO audit** to review draft and live records separately, inspect detected SEO field mappings, and follow prioritized findings into the editor. Checks are advisory and leave publishing available. Website rendering and indexing remain unverified. See [SEO audit rules and API](docs/seo-audit.md).

## Local development and checks

Generate `.env` first. In separate terminals:

```sh
cd api
uv sync --locked --group dev
uv run uvicorn app.main:app --reload
```

```sh
cd web
npm ci
npm run dev
```

Local API development defaults to SQLite; set `DATABASE_URL` to use PostgreSQL. Vite proxies API/auth/media endpoints to port 8001. Ensure `http://localhost:5173` is in development `MOSS_ORIGINS`.

```sh
cd api
uv run ruff check app tests migrations
uv run ruff format --check app tests migrations
uv run ruff check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run ruff format --check --config pyproject.toml ../scripts ../example-site/scripts/setup_moss.py
uv run mypy app
uv run pytest
```

The API suite defaults to SQLite. To run it against PostgreSQL (which exercises JSON path casts, `SKIP LOCKED`, and advisory locks that SQLite silently no-ops), point it at an admin connection; each test uses its own throwaway database and is cleaned up afterward:

```sh
MOSS_TEST_DATABASE_URL='postgresql+psycopg://USER:***@HOST:5432/DB' uv run pytest
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

For local development, temporarily set `MOSS_SKIP_AUTH=true` in the root `.env`, then run from the repository root:

```sh
docker compose up -d app
python3 example-site/scripts/setup_moss.py
docker compose --profile website up --build -d example-site
```

Open [localhost:5174](http://localhost:5174). Select **Example website** in the CMS workspace menu to edit its content. The setup script creates five content types, sample entries, and a scoped server-only delivery token in the ignored `example-site/.env`; rerunning it preserves edits.

Restore `MOSS_SKIP_AUTH=false` in the root `.env` and run `docker compose up -d app` when setup is complete. The delivery token continues working. For authenticated manual setup, local Vite development, deployment to your own domain, and signed publication events, follow the [example site guide](example-site/README.md).

## Product plan

The [PRD](docs/PRD.md) retains the 7 October baseline and records the approved release scope. The [task breakdown](docs/planning/TASKS.md) includes acceptance criteria and dependencies. The original task plan is tracked in the local Aftur project at `ProjectMemory/MossCMS`; open that folder in Aftur to review the PRD and plan. The owner approved all 34 tasks in this chat on 8 October 2026; they are now implemented sequentially on feature branches integrated into local `main`. [Execution ledger](docs/planning/IMPLEMENTATION.md) and [release evidence](docs/release-acceptance-2026-10-08.md) record the result. Aftur MCP attempts/artifacts record execution; its unfinished workflow statuses may still show proposed/dependency blocks. The original Markdown/JSON plan retains that historical status and is not current implementation evidence.
