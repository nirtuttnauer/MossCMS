# MossCMS and Moss Example — Product requirements

Version: 1.0 baseline · Date: 7 October 2026 · Execution update: 8 October 2026

## Execution update

The owner approved all 34 derived tasks, including optional P3 work, and requested sequential implementation on feature branches from `main`. MC-01–MC-34 are implemented and integrated into local `main`; retained branches are listed in [the implementation ledger](planning/IMPLEMENTATION.md).

The baseline/gaps and proposed wording below preserve the 7 October planning record. They are historical, not descriptions of today's defects or unapproved work. [Release evidence](release-acceptance-2026-10-08.md) records actual checks and unverified production/browser/provider conditions. [Editor workflows](editor-workflows.md) and [deployment/recovery](deployment-recovery.md) describe shipped behavior. No public deployment or hosting change was performed.

## 1. Product definition

MossCMS is a self-hosted, GraphQL-first content service for developers who want to define structured data once and consume it from several frontends. It provides a browser admin for data modeling, authoring, publishing, assets, and team management. The reference consumer is Moss Example, a example website with projects, a blog, an About me page, and a rotating component showcase.

The owner controls the application, database, media, and delivery credentials. The CMS remains useful independently of Moss Example.

## 2. Sources and authority

This PRD was drafted at the owner's request from this conversation and the repository as inspected on 7 October 2026. It was initially a draft; implementation authorization subsequently came from the owner's explicit chat approval described above.

- **Owner requirements:** Docker with a multistage build; Python managed by uv; Vite/React with shadcn-style admin components; GraphQL content delivery; team management; OAuth; a temporary development auth bypass; scheduled posts; content groups such as projects and blog posts; and the CMS-managed Moss Example website described below.
- **Observed baseline:** capabilities found in the current source. Existing features are retained rather than recreated as new tasks.
- **Proposed next release:** improvements suggested by the agent, now captured for review. Their presence here does not authorize implementation or establish a release date.

Sources: root `README.md`, `TODO.md`, `TYPE_IMPROVEMENTS.md`, `example-site/README.md`, and the API, admin, website, setup, and deployment source. Historical verification statements in existing documents were not rerun for this planning work. `TYPE_IMPROVEMENTS.md` is partly stale: a delivery-shape preview now exists, but its accuracy and UX still need review.

## 3. Users and jobs

| User | Main job |
| --- | --- |
| Instance owner / administrator | Deploy the service, manage workspaces and teams, define schemas, issue delivery tokens, and recover data. |
| Content editor | Create projects and posts, attach media, preview changes, and publish now or later. |
| Reader | Inspect editorial content without changing it. |
| Frontend developer | Query published structured data through a stable, scoped GraphQL API. |
| Website visitor | Browse Moss Example projects and posts and explore an accessible animated homepage. |

## 4. Goals and boundaries

### Goals

1. Make self-hosted content management practical with one documented Docker deployment.
2. Make content reusable across independent frontend applications.
3. Make publishing predictable: drafts, live content, scheduled changes, and failures are distinguishable.
4. Make Moss Example content and existing visual components configurable from MossCMS.
5. Preserve existing entries, IDs, history, workspace isolation, and API access boundaries during upgrades.

### Outside this release

- A visual page designer or live graphical frontend editor.
- Arbitrary React/JavaScript uploaded through the CMS; new animation component kinds require code.
- Real-time collaborative document editing, payments, a plugin marketplace, or a hosted SaaS offering.
- Automatic DNS changes or public deployment of Moss Example.
- Additional OAuth providers, custom per-field team roles, or email delivery beyond the current manually shared invitations and recovery links.

## 5. Historical baseline — 7 October 2026

These are observed capabilities, not a certification of production readiness.

| ID | Capability | Current implementation / limit |
| --- | --- | --- |
| B01 | Deployment | Multistage Docker image, PostgreSQL, uv-managed API, Vite/React admin; optional separate website container. |
| B02 | Accounts and teams | Setup, password sign-in, operator recovery, GitHub/generic OIDC, invitations, admin/editor/reader roles, workspace membership. External OAuth configuration requires owner credentials. |
| B03 | Development bypass | `MOSS_SKIP_AUTH` is restricted to development; delivery token checks and mutation CSRF remain. |
| B04 | Data modeling | Ten field types, nested lists/objects, localization, private fields, versioned schemas and explicit migrations. Form and delivery-shape previews exist. |
| B05 | Authoring | Entries grouped by type, filters/search/pagination, optimistic versions, revisions/restore, recoverable trash, immediate and scheduled publication. |
| B06 | API and assets | Editorial and scoped published-only delivery GraphQL; query limits, ETags, local/S3 media and expiring download URLs. |
| B07 | Operations | Alembic migration, health/readiness, request IDs/timing, audit history, backup and restore tooling. |
| B08 | Moss Example | CMS-driven profile, pages, projects, posts and slides; dark `#11151B` sidebar, desktop 20/80 layout, responsive navigation and randomized liquid/Three.js/promotion/blog carousel with motion controls. |

### Observed gaps

- Saving a published entry as draft or scheduled clears its published data; delivery also filters by its single status. Drafting an update can therefore remove live content.
- Publication metadata such as slug shares the editable entry record; retaining only `published_data` would not fully isolate live and draft versions.
- Scheduled publication currently publishes the entry's current data. Autosave must not silently change what is queued for publication.
- Rich-text fields store strings in a textarea; the website renders simple paragraphs.
- Website draft previews and authoring autosave/unsaved-change guards are absent.
- Asset upload exists, but website project galleries and blog covers are not integrated.
- Website routing uses hashes and canonical metadata points to the homepage.
- CMS and website refresh lists/content every ten seconds. Schedule failures are recorded in audit history rather than surfaced as actionable publishing failures.
- Admin requests have timeouts, but a timed-out mutation can have committed. The earlier intermittent “Saving…” delay has no confirmed root cause.

## 6. Required baseline behavior

The following owner requirements must survive every planned improvement:

- Each workspace contains independent schemas, entries, members, assets, tokens and audit records.
- Administrators manage schemas, members and tokens; editors manage content/media; readers inspect content. The final administrator cannot be removed.
- Delivery credentials cannot mutate content, read drafts/history, or reveal private fields, including nested values. Credentials for Moss Example remain server-side.
- Content groups come from schema types. Projects and blog posts remain separate collections without hard-coding the CMS to those two types.
- Scheduled dates are stored in UTC and shown with an explicit authoring timezone. The server must be running to execute schedules; overdue schedules are handled after restart.
- Moss Example retains Home, expandable Projects, Blog and About me navigation. The removed name/caption/Explore block stays removed. Defaults retain the requested sidebar color and desktop proportions.
- Existing animation kinds remain configurable through CMS data. Random rotation avoids immediate repeats, supports manual navigation/pause, and respects reduced motion and hidden tabs.

## 7. Proposed next-release requirements

All FR items below preserve the initial proposed scope. See the execution update for implementation status.

### FR01 — Independent editable and published versions · P0

An entry has an editable working version and an optional complete public snapshot. The public snapshot includes data, slug, display metadata, publication timestamp and publication revision. Delivery uses only the public snapshot, including reference resolution, filtering, sorting, and generated GraphQL resolvers.

Saving a draft or restoring history leaves the live snapshot intact. **Publish now** atomically replaces it. **Unpublish** explicitly removes it and cancels any pending publication. Trashing also removes public availability. Editorial state separately communicates live, unpublished changes, and a pending schedule. Public slug uniqueness and editable slug uniqueness must both be enforced within a workspace/type.

Acceptance: editing a live post's title, body and slug changes none of its delivery responses until publication; restore does not unpublish; failed/conflicting writes cannot partially replace a public snapshot; migration preserves existing published entries and their URLs.

### FR02 — Immutable scheduled changes and actionable failures · P0

Scheduling captures the selected working revision and complete future public snapshot. Later drafting does not change that scheduled revision. Replacing a schedule is explicit. Cancelling a schedule preserves the current live snapshot; a never-published entry remains private.

Revalidate the captured revision against current schema/references when due. Failure preserves existing live content and records a visible, persistent explanation and recovery action. A schedule queue lists upcoming, overdue, and failed publications. Retries require an explicit editor action after resolving the cause.

Acceptance: a scheduled revision publishes once, including after restart or concurrent workers; later autosave cannot alter it; invalid publication retains the last live version; due time and failure reason are visible to authorized editors.

### FR03 — Safe authoring and autosave · P1

Warn before discarding unsaved entry/schema changes. Add debounced entry draft autosave with saved/saving/offline/error/conflict indicators. Autosave never publishes, modifies the live snapshot, or replaces a scheduled snapshot. It uses the latest acknowledged version, serializes saves, avoids repeat blank-entry creation, and preserves local edits on conflict/error.

Acceptance: closing, navigation and refresh protect unsaved changes; readers cannot autosave; changing workspace cannot send a delayed write to the old/new wrong workspace; the user can compare or reload after a concurrent-edit conflict.

### FR04 — Blog authoring and formatted rendering · P1

Proposed first implementation: Markdown stored in the existing string-based rich-text fields, with formatting controls and a preview. Support headings, emphasis, lists, links, fenced code and asset-backed images. Keep legacy plain text readable and GraphQL string fields compatible. Raw HTML and unsafe URL schemes must not execute. A portable block-document format is deferred.

Acceptance: the same supported formatting renders consistently in CMS preview and Moss Example; plain existing bodies retain their meaning; image references resolve without storing expiring signed URLs as durable source content.

### FR05 — Preview on the actual website · P1

An authorized editor can preview a saved working revision on Moss Example without publishing. Use an expiring, workspace/entry/revision-scoped preview grant redeemed by the website server. Show a persistent preview indicator and an exit action. A preview does not expand ordinary delivery-token permissions or expose private fields to site components.

Acceptance: expired/revoked/out-of-scope grants fail; preview responses are non-cacheable and non-indexable; preview credentials are removed from the visible URL after redemption and excluded from logs; published visitors continue to receive published data.

### FR06 — Website images · P2

Add optional blog/project covers and project gallery items using existing assets, with alt text and focal/crop settings. The media picker supports preview/search/pagination. Provide bounded image variants and responsive image rendering. Maintain durable asset IDs and refresh/resolve download URLs at read time.

Acceptance: old entries remain valid; local and S3 assets work; non-image files are rejected in image slots; broken/missing images have usable fallbacks; image dimensions prevent disruptive layout shifts.

### FR07 — Website routing and metadata · P2

Support actual `/blog/<slug>` and `/projects/<slug>` routes, direct navigation, refresh, back/forward and real 404 responses. Preserve existing hash links through a compatibility redirect/translation. Render page-specific canonical, title, description and social image metadata in the initial HTML. Add published-only sitemap and RSS endpoints using http://localhost:5174 as the configured production origin.

Acceptance: a direct HTTP request for a post receives its metadata and content route; unknown pages return 404; drafts/previews never appear in sitemap/RSS; legacy links resolve; changing a live slug has a documented redirect policy.

### FR08 — Publication propagation · P2

Record publication/unpublish/delete events transactionally in an outbox. Provide optional signed webhooks with bounded retries, delivery history, and deduplication IDs. The website consumes an authenticated invalidation signal and serves an appropriate current-content cache. Long-lived open pages can receive a lightweight update event; retain polling as a recovery path.

Acceptance: rolled-back writes create no delivery event; no external request blocks a publication transaction; webhook failure does not revert a publish; private draft data is absent from payloads; retries cannot cause duplicate side effects. Protect webhook destinations from internal-network access, apart from an explicit operator-configured allowlist for the local website.

### FR09 — Clear save and publication feedback · P1

Distinguish draft saved, publication committed, schedule saved, and frontend refresh pending/confirmed. Preserve structured GraphQL error codes and request IDs in admin error handling. On ambiguous timeout, reconcile by entry/version or an idempotency key rather than blindly repeating a mutation. Reuse existing timing logs/metrics to locate delay in API, database, scheduler or website fetch.

Acceptance: saving always settles into success/error/uncertain state; form values survive failures; a website update is never called confirmed without evidence; request timing does not log credentials or private bodies.

### FR10 — Schema-builder accuracy and migration help · P2

Make delivery-shape preview match the generated API for localized, list, enum, object, reference, asset and private fields. Keep the form preview interactive. Propose migration defaults/drops from an explicit before/after diff; require confirmation of renames and destructive drops. Improve inline enum editing and reference-target validation.

Acceptance: preview identifies what is excluded from delivery; a migration suggestion never runs automatically; unknown reference targets block saving; zero target entries is a warning; existing server validation remains authoritative.

### FR11 — Larger schema usability · P3 / optional

Add collapsible field groups/outline, keyboard-accessible reordering, schema version comparison, reusable starter templates and duplication with explicit new keys. These extend the unfinished content-type improvement backlog. Per-type icons, workspace default locales and arbitrary cross-group moves remain later candidates.

Acceptance: nested schema constraints remain enforced, reordering changes order without losing data, and templates/duplication cannot overwrite an existing schema.

### FR12 — Release and operator guidance · P1 / release gate

Document new publication state, schedules, Markdown, preview, cache invalidation, migration/recovery and provider configuration. Rehearse the main editor/reader/admin/visitor flows and an upgrade using a separate restored database before public release. Record actual evidence and remaining limitations.

Acceptance: no fabricated pass claims; no production data overwrite during rehearsal; production auth bypass is rejected; an operator can identify a failed schedule or slow request and follow a documented recovery path.

## 8. Architecture and compatibility constraints

- Retain Python/FastAPI/Strawberry/SQLAlchemy, uv and PostgreSQL; use forward Alembic migrations rather than editing the existing migration in place.
- Retain Vite/React/TypeScript admin and example-site projects and multistage Docker builds.
- Keep the editorial API and delivery API separate; extend existing GraphQL operations compatibly where possible. Document any intentional breaking change before implementation.
- Start with the current application scheduler/outbox worker lifecycle. A separate queue service is a later scaling decision, not an assumed new dependency.
- Existing website setup upgrades are idempotent and preserve owner-edited content, entry IDs, history and compatible custom schema fields.
- Keep public snapshots, schedules and schema migrations in consistent transactions. Define migration handling for historical revisions before changing snapshot format.

## 9. Quality and proposed success measures

These are release targets, not measured current performance.

| Area | Target / method |
| --- | --- |
| Content integrity | No live-content loss from draft saves, restore, failed schedules or conflicting edits in the documented acceptance scenarios. |
| Save latency | p95 <= 2 seconds for ordinary entry saves on a documented local Compose fixture; record dataset, hardware and load. No indefinite UI spinner. |
| Scheduled publish | p95 <= 10 seconds after due time while the app is healthy, excluding explicit validation failures. |
| Website freshness | p95 <= 3 seconds after committed publication when event propagation is healthy; fallback within 15 seconds with working polling. |
| Accessibility | Core flows keyboard operable; labeled controls, focus management, readable feedback, and reduced-motion behavior. |
| Isolation | No draft/private-field exposure through delivery, preview misuse, feeds, metadata or event payloads. |
| Upgrade safety | Restored-database rehearsal preserves published entry IDs/counts, URLs and revisions; document rollback backup/image pair. |

## 10. Delivery sequence

| Milestone | Outcome | Gate |
| --- | --- | --- |
| M1 — Publishing integrity | Independent live snapshots, immutable schedules, explicit unpublish and accurate state UI. | Draft edits cannot change live output. |
| M2 — Authoring and preview | Unsaved-change protection, autosave, Markdown, secure website preview. | Autosave cannot publish or alter queued revisions. |
| M3 — Website content and discoverability | Covers/galleries, stable page URLs, initial metadata, feeds. | Existing links and content continue to work. |
| M4 — Publication feedback and propagation | Failed-publication queue, outbox/webhooks, website updates, reconciled save feedback. | Failures are actionable and publication is independent of network callbacks. |
| M5 — Schema usability | Accurate previews and migration help; optional larger-schema tools. | Schema validation and migration review remain intact. |
| M6 — Release readiness | Acceptance evidence and operator/upgrade documentation. | Owner review before public deployment. |

The detailed proposed tasks and dependency graph are in [the task plan](planning/TASKS.md). No release date or elapsed-time estimate is committed.

## 11. Initial decisions and recorded implementation

| Initial decision | Implemented outcome / remaining choice |
| --- | --- |
| First rich-text format | Markdown strings with shared safe rendering; block documents remain separate scope |
| Preview lifetime and audience | 15-minute saved-revision grants, editor/admin issuance, revocable; initial URL is a secret bearer capability and should not be shared |
| Scheduling | Immutable selected revision; replace explicitly to include later edits |
| Raster processing | JPEG/PNG/WebP, 20 million pixels, 10,000 per dimension, 20 MiB upload bound; animated inputs rejected; bounded WebP variants |
| Hosting and redirects | Hosting/TLS/DNS remains owner setup. Legacy hashes translate and unique current aliases redirect; changing a published slug has no historical redirect retention |
| Optional P3 | MC-31/MC-32 were included in the owner's approval and implemented; other backlog ideas remain separate |
