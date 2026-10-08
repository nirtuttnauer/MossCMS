# MossCMS — Proposed implementation tasks

Prepared 7 October 2026. These are proposed improvements for owner review, not approved execution.

PRD: [Product requirements](../PRD.md). Aftur is the task status source of truth; this is a snapshot of the initial plan.

Aftur workspace: `/Users/nirtuttnauer/Documents/Code/MossCMS/ProjectMemory/MossCMS`. Imported PRD: `PRD-e46f6b17`.

Existing delivered functionality is documented in the PRD baseline and is not recreated here.
Priorities: P0 publishing integrity; P1 authoring/release; P2 extensions; P3 optional schema tools.
Priorities and milestones are recorded in task descriptions because the current agent proposal API has no dedicated priority or milestone field.
Acceptance criteria were read back after import. Where the Aftur importer omitted the native field, the criteria were saved and verified as attributed task notes (available through task discussion and agent context).

## Task index

| Plan ID | Aftur ID | Priority | Milestone | Task | Depends on |
| --- | --- | --- | --- | --- | --- |
| MC-01 | TASK-1 | P0 | M1 | Define the publication and scheduling state contract | — |
| MC-02 | TASK-2 | P0 | M1 | Migrate complete live and scheduled snapshots | MC-01 |
| MC-03 | TASK-3 | P0 | M1 | Separate draft saves from live GraphQL delivery | MC-02 |
| MC-04 | TASK-4 | P0 | M1 | Publish the captured scheduled revision safely | MC-02, MC-03 |
| MC-05 | TASK-5 | P0 | M1 | Add explicit unpublish and schedule-cancel actions | MC-03, MC-04 |
| MC-06 | TASK-6 | P0 | M1 | Show live, draft and scheduled state in the admin | MC-03, MC-04, MC-05 |
| MC-07 | TASK-7 | P1 | M2 | Protect unsaved entry and schema edits | — |
| MC-08 | TASK-8 | P1 | M2 | Provide a conflict-safe draft autosave contract | MC-03, MC-04 |
| MC-09 | TASK-9 | P1 | M2 | Add debounced entry autosave and recovery feedback | MC-06, MC-07, MC-08 |
| MC-10 | TASK-10 | P1 | M2 | Add Markdown authoring controls and preview | — |
| MC-11 | TASK-11 | P1 | M2 | Render Markdown consistently on example.com | MC-10 |
| MC-12 | TASK-12 | P1 | M2 | Issue scoped expiring preview grants | MC-03 |
| MC-13 | TASK-13 | P1 | M2 | Add secure website preview sessions | MC-12 |
| MC-14 | TASK-14 | P1 | M2 | Open saved website previews from the editor | MC-09, MC-13 |
| MC-15 | TASK-15 | P2 | M3 | Define covers and project gallery fields | — |
| MC-16 | TASK-16 | P2 | M3 | Generate bounded image variants for local and S3 assets | MC-15 |
| MC-17 | TASK-17 | P2 | M3 | Improve image picking and gallery authoring | MC-15, MC-16 |
| MC-18 | TASK-18 | P2 | M3 | Display blog covers and project galleries | MC-16, MC-17 |
| MC-19 | TASK-19 | P2 | M3 | Replace hash routes with stable website paths | MC-03 |
| MC-20 | TASK-20 | P2 | M3 | Serve per-page metadata in initial HTML | MC-18, MC-19 |
| MC-21 | TASK-21 | P2 | M3 | Add published-only sitemap and blog RSS | MC-19, MC-20 |
| MC-22 | TASK-22 | P1 | M4 | Persist structured publication failures | MC-04, MC-05 |
| MC-23 | TASK-23 | P1 | M4 | Build the upcoming and failed publication queue | MC-06, MC-22 |
| MC-24 | TASK-24 | P2 | M4 | Record publication events in a transactional outbox | MC-03, MC-04, MC-05 |
| MC-25 | TASK-25 | P2 | M4 | Deliver signed webhooks with bounded retries | MC-24 |
| MC-26 | TASK-26 | P2 | M4 | Refresh example.com from publication events | MC-25 |
| MC-27 | TASK-27 | P1 | M4 | Reconcile uncertain saves and expose request timing | MC-06, MC-08, MC-26 |
| MC-28 | TASK-28 | P2 | M5 | Correct schema delivery preview and make form preview interactive | — |
| MC-29 | TASK-29 | P2 | M5 | Suggest schema migrations from explicit field diffs | MC-28 |
| MC-30 | TASK-30 | P2 | M5 | Improve enum editing and reference confidence | — |
| MC-31 | TASK-31 | P3 | M5 | Add schema outline, accessible reordering and version comparison | MC-28 |
| MC-32 | TASK-32 | P3 | M5 | Add type templates and safe duplication | MC-30 |
| MC-33 | TASK-33 | P1 | M6 | Record end-to-end release acceptance evidence | MC-09, MC-11, MC-14, MC-18, MC-21, MC-23, MC-27, MC-29, MC-30 |
| MC-34 | TASK-34 | P1 | M6 | Document deployment, recovery and new publishing workflows | MC-33 |

## MC-01 — Define the publication and scheduling state contract

Aftur: `TASK-1` · M1 · P0 · Requirements: FR01, FR02

Specify editable, published and scheduled snapshots; metadata, slug uniqueness, transition rules, GraphQL compatibility, and revision/schema migration behavior. Include a state-transition table and failure semantics before code changes.

**Acceptance criteria**

- Contract covers new entry, draft of live entry, publish, schedule, reschedule, cancel, restore, unpublish and trash.
- Publication includes data and route metadata; scheduled revision is immutable.
- Existing API callers have an explicit compatibility path and schema-change handling is documented.

**Relevant files:** `api/app/models.py`, `api/app/content.py`, `api/app/graphql.py`, `docs/PRD.md`

**Dependencies:** None

## MC-02 — Migrate complete live and scheduled snapshots

Aftur: `TASK-2` · M1 · P0 · Requirements: FR01, FR02

Add forward Alembic migration and model fields from MC-01, backfilling current published entries and existing pending schedules. Preserve entry IDs, revisions, and current live URLs.

**Acceptance criteria**

- Backfill preserves currently published values and routes without converting private drafts into publications.
- Existing schedules receive a captured snapshot/revision and UTC due time.
- Migration supports a separate restored database and documents recovery using the prior backup/image.

**Relevant files:** `api/app/models.py`, `api/migrations/versions`

**Dependencies:** MC-01

## MC-03 — Separate draft saves from live GraphQL delivery

Aftur: `TASK-3` · M1 · P0 · Requirements: FR01

Refactor save, restore, generic delivery, generated resolvers, references, title/search/sort and slug lookup to respect complete live snapshots. Keep version conflicts and workspace checks.

**Acceptance criteria**

- Draft edits and restores leave the previous public body, title, slug and references unchanged.
- Immediate publish atomically replaces the live snapshot; public and draft slug conflicts are rejected.
- Delivery scopes and recursive private-field projection remain enforced.

**Relevant files:** `api/app/content.py`, `api/app/graphql.py`

**Dependencies:** MC-02

## MC-04 — Publish the captured scheduled revision safely

Aftur: `TASK-4` · M1 · P0 · Requirements: FR02

Use the stored scheduled snapshot, revalidate it when due, and handle worker locks/restarts. Later draft saves must not modify it. Preserve the last live snapshot on validation failure.

**Acceptance criteria**

- Later edits cannot change the scheduled payload unless the editor explicitly replaces the schedule.
- Due/overdue work is applied once with concurrent-worker protection.
- Failure preserves live content and records entry, scheduled revision and actionable reason.

**Relevant files:** `api/app/content.py`, `api/app/main.py`

**Dependencies:** MC-02, MC-03

## MC-05 — Add explicit unpublish and schedule-cancel actions

Aftur: `TASK-5` · M1 · P0 · Requirements: FR01, FR02

Expose editorial operations for unpublish and cancellation using optimistic versions. Define trash and restore interactions through the state contract, with audit events.

**Acceptance criteria**

- Cancel keeps an existing live snapshot and removes only the pending schedule.
- Unpublish removes public availability and cancels a pending schedule without losing the draft/history.
- Readers, delivery tokens and stale versions cannot perform either action.

**Relevant files:** `api/app/content.py`, `api/app/graphql.py`

**Dependencies:** MC-03, MC-04

## MC-06 — Show live, draft and scheduled state in the admin

Aftur: `TASK-6` · M1 · P0 · Requirements: FR01, FR02, FR09

Update entry API types, overview counts, list badges and publishing controls to represent independent states. Show scheduled revision and warn when newer draft edits are not scheduled.

**Acceptance criteria**

- Editors distinguish live content, unpublished changes and pending publication without contradictory badges.
- Unpublish, cancel and replace-schedule are explicit actions with accurate success feedback.
- Timezone and current group/filter behavior remain usable; readers see no editing controls.

**Relevant files:** `web/src/pages/Content.tsx`, `web/src/lib/api.ts`, `web/src/pages/App.tsx`, `api/app/graphql.py`

**Dependencies:** MC-03, MC-04, MC-05

## MC-07 — Protect unsaved entry and schema edits

Aftur: `TASK-7` · M2 · P1 · Requirements: FR03

Add dirty tracking and guarded close, Escape, backdrop and navigation. Preserve form state after errors and use browser unload protection where supported.

**Acceptance criteria**

- Each modal exit and workspace navigation either saves, explicitly discards, or keeps dirty edits.
- No prompt appears for a clean form or successfully saved data.
- Confirmation remains keyboard accessible and focus returns to the editor on cancellation.

**Relevant files:** `web/src/pages/Content.tsx`, `web/src/pages/Types.tsx`, `web/src/components/ui/dialog.tsx`, `web/src/pages/App.tsx`

**Dependencies:** None

## MC-08 — Provide a conflict-safe draft autosave contract

Aftur: `TASK-8` · M2 · P1 · Requirements: FR03, FR09

Extend/reuse draft save to return authoritative entry/version and support a stable creation identifier or idempotency key. Keep publication/schedule writes separate.

**Acceptance criteria**

- Repeated autosave/reconciliation cannot create duplicate new entries.
- Version conflicts preserve newer server changes and return a structured code.
- Autosave leaves live and captured scheduled snapshots unchanged.

**Relevant files:** `api/app/content.py`, `api/app/graphql.py`, `web/src/lib/api.ts`

**Dependencies:** MC-03, MC-04

## MC-09 — Add debounced entry autosave and recovery feedback

Aftur: `TASK-9` · M2 · P1 · Requirements: FR03

Serialize debounced saves, keep acknowledged versions, and display saving/saved/offline/conflict states. Handle unfinished required fields, unmount, workspace switches and in-flight manual publish.

**Acceptance criteria**

- One entry gets serialized writes with no delayed cross-workspace mutations.
- Invalid/incomplete drafts remain locally visible with an explanation rather than being lost.
- Conflict/offline/error states keep editor values and provide an explicit recovery action.

**Relevant files:** `web/src/pages/Content.tsx`, `web/src/lib/api.ts`

**Dependencies:** MC-06, MC-07, MC-08

## MC-10 — Add Markdown authoring controls and preview

Aftur: `TASK-10` · M2 · P1 · Requirements: FR04

Upgrade string-based richText inputs with accessible formatting controls, code fences, safe links and a Markdown preview. Define asset-ID image syntax and keep localized richText working.

**Acceptance criteria**

- Headings, emphasis, lists, links, fenced code and images can be authored and previewed.
- Legacy plain strings round-trip without automatic destructive conversion.
- Raw HTML and unsafe links cannot execute; image references do not persist signed URLs.

**Relevant files:** `web/src/components/Fields.tsx`, `web/src/lib/fields.ts`, `web/package.json`

**Dependencies:** None

## MC-11 — Render Markdown consistently on example.com

Aftur: `TASK-11` · M2 · P1 · Requirements: FR04

Replace paragraph-only body rendering with a safe renderer matching MC-10, including code, typography and graceful asset-reference handling.

**Acceptance criteria**

- Supported formatting matches the CMS preview and preserves plain-text posts.
- Unsafe HTML/URL input remains inert in website output.
- Long code, links and content remain readable on mobile; missing images have a fallback.

**Relevant files:** `personal-site/src/App.tsx`, `personal-site/src/style.css`, `personal-site/server/moss.mjs`, `personal-site/package.json`

**Dependencies:** MC-10

## MC-12 — Issue scoped expiring preview grants

Aftur: `TASK-12` · M2 · P1 · Requirements: FR05

Add authenticated editor operations to create/revoke a 15-minute grant for a saved revision. Implement server redemption with precise workspace/entry/revision scope and public-field projection.

**Acceptance criteria**

- Readers and delivery tokens cannot issue grants; expired/revoked/wrong-scope grants fail.
- Preview access is bound to a saved revision and does not widen delivery-token scope.
- Responses are non-cacheable, secrets are excluded from logs, and private fields remain excluded.

**Relevant files:** `api/app/models.py`, `api/app/graphql.py`, `api/app/security.py`, `api/app/main.py`, `api/migrations/versions`

**Dependencies:** MC-03

## MC-13 — Add secure website preview sessions

Aftur: `TASK-13` · M2 · P1 · Requirements: FR05

Redeem grants server-side into a short-lived preview session, remove credentials from URLs, and render scoped draft data with an exit control. Reuse the ordinary website components.

**Acceptance criteria**

- Preview shows the intended saved revision and a persistent Preview banner.
- Session expiry/revocation exits safely; published requests are unaffected.
- Preview has no-store and noindex responses, avoids credential logging and grants no general CMS access.

**Relevant files:** `personal-site/server/index.mjs`, `personal-site/server/moss.mjs`, `personal-site/src/App.tsx`

**Dependencies:** MC-12

## MC-14 — Open saved website previews from the editor

Aftur: `TASK-14` · M2 · P1 · Requirements: FR05

Configure an allowed website preview origin and add Preview for supported website types. Save explicitly when needed and show which revision is being previewed.

**Acceptance criteria**

- Preview opens the real project/post/slide using the chosen saved revision.
- Missing preview configuration has a useful message; unsupported types do not offer a broken action.
- Preview never implicitly publishes and opening it preserves current authoring state.

**Relevant files:** `web/src/pages/Content.tsx`, `web/src/pages/Settings.tsx`, `web/src/lib/api.ts`

**Dependencies:** MC-09, MC-13

## MC-15 — Define covers and project gallery fields

Aftur: `TASK-15` · M3 · P2 · Requirements: FR06

Extend the repeatable website setup schema with optional cover/gallery asset IDs, alt text and focal/crop metadata. Define image-format and decoded-pixel limits.

**Acceptance criteria**

- Existing entries remain valid and rerunning setup preserves edits and custom fields.
- Blog/project covers and ordered gallery items have a documented contract.
- Limits and behavior for missing/non-image assets are defined before processing.

**Relevant files:** `personal-site/scripts/setup_moss.py`, `personal-site/server/moss.mjs`

**Dependencies:** None

## MC-16 — Generate bounded image variants for local and S3 assets

Aftur: `TASK-16` · M3 · P2 · Requirements: FR06

Implement image dimensions and bounded variants, with signed delivery, persistent IDs and storage-backend support. Avoid running unlimited processing during frontend requests.

**Acceptance criteria**

- Oversized/unsupported input is rejected without excessive decode or memory use.
- Local and S3 variants retain workspace checks and expiring URL semantics.
- Dimensions, variant metadata, storage/recovery behavior and missing-file handling are documented.

**Relevant files:** `api/app/storage.py`, `api/app/main.py`, `api/app/graphql.py`, `api/app/models.py`, `api/pyproject.toml`

**Dependencies:** MC-15

## MC-17 — Improve image picking and gallery authoring

Aftur: `TASK-17` · M3 · P2 · Requirements: FR06

Add paginated searchable image selection with thumbnails, alt text and crop/focal controls using existing Assets and field components.

**Acceptance criteria**

- Editor can find assets beyond the first 100 without loading the full library.
- Image slots reject incompatible file types and save IDs rather than expiring URLs.
- Gallery order, alt text and crop values survive save/reopen and are keyboard accessible.

**Relevant files:** `web/src/components/Fields.tsx`, `web/src/pages/Assets.tsx`, `web/src/lib/api.ts`, `api/app/graphql.py`

**Dependencies:** MC-15, MC-16

## MC-18 — Display blog covers and project galleries

Aftur: `TASK-18` · M3 · P2 · Requirements: FR06

Resolve asset fields in the website adapter and render responsive cover/gallery images with dimensions, alt text and selected crops.

**Acceptance criteria**

- Blog and project pages show configured media without changing existing text-only entries.
- Signed URL expiry is handled through fresh reads; broken assets do not break pages.
- Responsive images reserve space and obey crop settings and alt text.

**Relevant files:** `personal-site/server/moss.mjs`, `personal-site/src/App.tsx`, `personal-site/src/style.css`

**Dependencies:** MC-16, MC-17

## MC-19 — Replace hash routes with stable website paths

Aftur: `TASK-19` · M3 · P2 · Requirements: FR07

Implement /blog and /projects detail routes with browser navigation, server deep-link handling and real 404 status. Translate existing hash URLs and define slug redirect retention.

**Acceptance criteria**

- Direct visit, refresh and browser back/forward work for published pages.
- Existing unique simple hashes and namespaced hashes resolve to their matching page.
- Unknown routes return 404; draft-only/new slugs do not leak into public routing.

**Relevant files:** `personal-site/src/App.tsx`, `personal-site/src/components/Showcase.tsx`, `personal-site/server/index.mjs`

**Dependencies:** MC-03

## MC-20 — Serve per-page metadata in initial HTML

Aftur: `TASK-20` · M3 · P2 · Requirements: FR07

Generate page title, description, canonical and social image metadata from the public snapshot before responding, safely escaping CMS values. Include the preview noindex path.

**Acceptance criteria**

- Initial HTTP HTML for each published page includes its own canonical/title/description.
- Canonical URLs use configured example.com origin and never request Host or preview credentials.
- HTML escaping prevents metadata injection; expired asset URLs are not permanent social-image references.

**Relevant files:** `personal-site/server/index.mjs`, `personal-site/server/moss.mjs`, `personal-site/src/App.tsx`, `personal-site/index.html`

**Dependencies:** MC-18, MC-19

## MC-21 — Add published-only sitemap and blog RSS

Aftur: `TASK-21` · M3 · P2 · Requirements: FR07

Serve sitemap.xml and blog RSS with canonical routes, publication dates and safe XML escaping; exclude drafts, previews, trashed and unpublished entries.

**Acceptance criteria**

- Feeds include only current public snapshots and absolute canonical URLs.
- Publication dates reflect publication rather than an unrelated draft save.
- Unknown/private content and unsafe XML cannot enter feed output.

**Relevant files:** `personal-site/server/index.mjs`, `personal-site/server/moss.mjs`

**Dependencies:** MC-19, MC-20

## MC-22 — Persist structured publication failures

Aftur: `TASK-22` · M4 · P1 · Requirements: FR02

Expose schedule failure state and reason through editorial queries with failure timestamp and captured revision. Add permission-checked retry/resolve semantics.

**Acceptance criteria**

- Validation failures remain visible independently of the limited audit list.
- A failed schedule never removes the last public snapshot.
- Retry is explicit, version-checked and revalidates content; delivery reveals no failure internals.

**Relevant files:** `api/app/content.py`, `api/app/graphql.py`, `api/app/models.py`, `api/migrations/versions`

**Dependencies:** MC-04, MC-05

## MC-23 — Build the upcoming and failed publication queue

Aftur: `TASK-23` · M4 · P1 · Requirements: FR02, FR09

Add a dedicated list/calendar-style queue using server pagination and scheduled/overdue/failed filters. Include timezone, revision, error detail and edit/reschedule actions.

**Acceptance criteria**

- Editors can locate upcoming, overdue and failed publications without searching audit JSON.
- Failure explanation links to a concrete recovery action; timezone is always stated.
- Queue refresh does not overwrite an open editor and readers cannot mutate schedules.

**Relevant files:** `web/src/pages/Content.tsx`, `web/src/lib/api.ts`, `api/app/graphql.py`

**Dependencies:** MC-06, MC-22

## MC-24 — Record publication events in a transactional outbox

Aftur: `TASK-24` · M4 · P2 · Requirements: FR08

Add an outbox model/migration and worker claiming/recovery for publication, unpublish and trash events. Exclude draft saves and private payload fields.

**Acceptance criteria**

- Event and publication commit together; rollback emits nothing.
- Events have stable IDs, workspace/type/entry/publication revision and bounded retention.
- Worker restart/duplicate claims are safe and network requests stay outside write transactions.

**Relevant files:** `api/app/models.py`, `api/app/content.py`, `api/app/main.py`, `api/migrations/versions`

**Dependencies:** MC-03, MC-04, MC-05

## MC-25 — Deliver signed webhooks with bounded retries

Aftur: `TASK-25` · M4 · P2 · Requirements: FR08

Add administrator-managed webhook endpoints/secrets, signed events, retry backoff and delivery history. Validate destinations and use an explicit operator allowlist for local website callbacks.

**Acceptance criteria**

- Receivers can verify timestamp/signature and deduplicate by event ID.
- Redirects, private-network destinations and DNS changes cannot bypass destination policy.
- Failures/retries are visible and bounded; secrets are not returned after creation or logged.

**Relevant files:** `api/app/main.py`, `api/app/security.py`, `api/app/models.py`, `api/app/config.py`, `web/src/pages/Settings.tsx`

**Dependencies:** MC-24

## MC-26 — Refresh example.com from publication events

Aftur: `TASK-26` · M4 · P2 · Requirements: FR08

Add an authenticated invalidation endpoint, current-content cache and lightweight browser update signal. Retain polling recovery and account for signed media URL lifetimes.

**Acceptance criteria**

- Verified events update visible website content without an immediate manual reload.
- Duplicate/out-of-order events do not regress content; failed fetch preserves last valid cache.
- Fallback polling remains functional; cache/preview isolation and URL-expiry limits are explicit.

**Relevant files:** `personal-site/server/index.mjs`, `personal-site/server/moss.mjs`, `personal-site/src/App.tsx`, `compose.yaml`

**Dependencies:** MC-25

## MC-27 — Reconcile uncertain saves and expose request timing

Aftur: `TASK-27` · M4 · P1 · Requirements: FR09

Preserve GraphQL error codes/request IDs, reconcile committed mutations after timeouts, and show accurate publish versus website-update states. Reuse current timing logs/metrics to diagnose latency.

**Acceptance criteria**

- Timed-out saves are reconciled without duplicate entries or automatic blind publish retries.
- Saving reaches a visible success/error/uncertain state and retains editable values.
- Website update is marked confirmed only with acknowledgement/version evidence; logs omit secrets/body data.

**Relevant files:** `web/src/lib/api.ts`, `web/src/pages/Content.tsx`, `api/app/main.py`, `api/app/graphql.py`

**Dependencies:** MC-06, MC-08, MC-26

## MC-28 — Correct schema delivery preview and make form preview interactive

Aftur: `TASK-28` · M5 · P2 · Requirements: FR10

Audit existing deliveryShape against backend-generated SDL; fix list/localized/private/reference/asset handling and show hidden-field summary. Wire form preview changes into previewData.

**Acceptance criteria**

- Preview agrees with actual generated API types and field signatures for all supported field kinds.
- Private nested fields are omitted and the hidden-field count is clear.
- Preview inputs accept changes without writing content, and reset only on meaningful shape changes.

**Relevant files:** `web/src/lib/fields.ts`, `web/src/pages/Types.tsx`, `api/app/graphql.py`

**Dependencies:** None

## MC-29 — Suggest schema migrations from explicit field diffs

Aftur: `TASK-29` · M5 · P2 · Requirements: FR10

Show before/after changes and propose defaults/drops; request explicit rename mapping. Preserve user-edited migration JSON and keep server all-entry validation.

**Acceptance criteria**

- Removed/new required/changed fields are identified before save.
- No rename or destructive drop is silently inferred or applied.
- Suggestions are editable and cannot overwrite a user migration without confirmation.

**Relevant files:** `web/src/pages/Types.tsx`, `web/src/lib/fields.ts`

**Dependencies:** MC-28

## MC-30 — Improve enum editing and reference confidence

Aftur: `TASK-30` · M5 · P2 · Requirements: FR10

Allow inline enum choice renames with duplicate/identifier validation; validate reference targets and show their entry counts, including empty targets. Explain title-driven slug behavior.

**Acceptance criteria**

- Invalid/duplicate enum edits are explained inline and blocked from save.
- Unknown reference target is an error; zero entries is a warning; permitted self-reference behavior is explicit.
- Counts are workspace-scoped and no valid existing schema is silently rewritten.

**Relevant files:** `web/src/components/FieldBuilder.tsx`, `web/src/lib/fields.ts`, `api/app/content.py`, `api/app/graphql.py`

**Dependencies:** None

## MC-31 — Add schema outline, accessible reordering and version comparison

Aftur: `TASK-31` · M5 · P3 · Requirements: FR11

Optional scope: collapsible nested cards/outline, keyboard-supported ordering and read-only schema history diff. Retain current arrow controls as a usable fallback.

**Acceptance criteria**

- Collapse/jump/reorder work for nested schemas without losing field settings.
- Every reorder action is keyboard accessible and respects nesting limits.
- Version comparison displays additions/removals/changes and never restores implicitly.

**Relevant files:** `web/src/components/FieldBuilder.tsx`, `web/src/pages/Types.tsx`, `web/src/lib/fields.ts`

**Dependencies:** MC-28

## MC-32 — Add type templates and safe duplication

Aftur: `TASK-32` · M5 · P3 · Requirements: FR11

Optional scope: starter Article/Product/Person/Event templates and whole-type or field duplication. Require unique type/field keys and never copy entries implicitly.

**Acceptance criteria**

- Templates produce valid editable schemas under existing constraints.
- Duplicating a type requires a new key and does not overwrite its source or clone content.
- Field duplication catches same-level name conflicts before save.

**Relevant files:** `web/src/pages/Types.tsx`, `web/src/components/FieldBuilder.tsx`, `web/src/lib/fields.ts`

**Dependencies:** MC-30

## MC-33 — Record end-to-end release acceptance evidence

Aftur: `TASK-33` · M6 · P1 · Requirements: FR12

After the selected implementation scope is approved and complete, perform the PRD acceptance walkthrough on a separate restored database. Record actual results, fixture/load context, role boundaries and limitations; never manufacture pass claims.

**Acceptance criteria**

- Evidence covers draft/live/schedule transitions, preview isolation, formatting, media, legacy routes and failures.
- Latency/freshness targets are measured with documented conditions and unmet targets are recorded.
- Upgrade preserves IDs/counts/history; evidence lists any external OAuth/S3 checks not performed.

**Relevant files:** `docs/PRD.md`, `docs/planning/TASKS.md`, `api/app`, `web/src`, `personal-site/src`

**Dependencies:** MC-09, MC-11, MC-14, MC-18, MC-21, MC-23, MC-27, MC-29, MC-30

## MC-34 — Document deployment, recovery and new publishing workflows

Aftur: `TASK-34` · M6 · P1 · Requirements: FR12

Update operator/editor docs for the final approved behavior, environment options, previews, callbacks, Markdown, schedules, upgrade and rollback. Reconcile stale TODO/type-improvement entries after evidence is available.

**Acceptance criteria**

- An operator can configure the services, diagnose failures and restore a matching backup/image pair.
- Editor instructions explain live drafts, fixed scheduled revisions, cancel/unpublish and preview.
- Docs distinguish shipped features from optional P3 work and deployment/provider setup still required.

**Relevant files:** `README.md`, `personal-site/README.md`, `TODO.md`, `TYPE_IMPROVEMENTS.md`, `docs`

**Dependencies:** MC-33
