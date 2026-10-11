# Implementation ledger — 8 October 2026

All 34 tasks were read through the project-scoped Aftur MCP launcher and implemented sequentially. The owner approved them in this chat and requested feature branches from main, then clarified that Aftur is still work in progress. Each task has a retained branch and recorded MCP attempt plus branch/commit artifacts. The branches were fast-forwarded into local `main` in dependency order. No Git remote was configured, no pull requests were created and no public deployment was performed.

Aftur's original proposed/dependency statuses remain distinct from execution evidence. This ledger records implementation; it does not impersonate an Aftur human approval or rewrite local tracker data. `TASKS.md` and `tasks.json` retain the original planning scope/status with an execution annotation. The tracker lives locally under ignored `ProjectMemory/MossCMS`.

| Plan / Aftur task | Scope | Retained branch |
| --- | --- | --- |
| MC-01 / TASK-1 | Define the publication and scheduling state contract | `feature/mc-01-publication-contract` |
| MC-02 / TASK-2 | Migrate complete live and scheduled snapshots | `feature/mc-02-snapshot-migration` |
| MC-03 / TASK-3 | Separate draft saves from live GraphQL delivery | `feature/mc-03-independent-live-delivery` |
| MC-04 / TASK-4 | Publish the captured scheduled revision safely | `feature/mc-04-immutable-schedules` |
| MC-05 / TASK-5 | Add explicit unpublish and schedule-cancel actions | `feature/mc-05-publication-actions` |
| MC-06 / TASK-6 | Show live, draft and scheduled state in the admin | `feature/mc-06-editorial-state` |
| MC-07 / TASK-7 | Protect unsaved entry and schema edits | `feature/mc-07-unsaved-edit-protection` |
| MC-08 / TASK-8 | Provide a conflict-safe draft autosave contract | `feature/mc-08-draft-autosave-api` |
| MC-09 / TASK-9 | Add debounced entry autosave and recovery feedback | `feature/mc-09-autosave-recovery` |
| MC-10 / TASK-10 | Add Markdown authoring controls and preview | `feature/mc-10-markdown-authoring` |
| MC-11 / TASK-11 | Render Markdown consistently on Moss Example | `feature/mc-11-website-markdown` |
| MC-12 / TASK-12 | Issue scoped expiring preview grants | `feature/mc-12-scoped-preview-grants` |
| MC-13 / TASK-13 | Add secure website preview sessions | `feature/mc-13-website-preview-sessions` |
| MC-14 / TASK-14 | Open saved website previews from the editor | `feature/mc-14-editor-previews` |
| MC-15 / TASK-15 | Define covers and project gallery fields | `feature/mc-15-cover-gallery-contract` |
| MC-16 / TASK-16 | Generate bounded image variants for local and S3 assets | `feature/mc-16-image-variants` |
| MC-17 / TASK-17 | Improve image picking and gallery authoring | `feature/mc-17-image-picker` |
| MC-18 / TASK-18 | Display blog covers and project galleries | `feature/mc-18-website-images` |
| MC-19 / TASK-19 | Replace hash routes with stable website paths | `feature/mc-19-website-routes` |
| MC-20 / TASK-20 | Serve per-page metadata in initial HTML | `feature/mc-20-initial-metadata` |
| MC-21 / TASK-21 | Add published-only sitemap and blog RSS | `feature/mc-21-public-feeds` |
| MC-22 / TASK-22 | Persist structured publication failures | `feature/mc-22-publication-failures` |
| MC-23 / TASK-23 | Build the upcoming and failed publication queue | `feature/mc-23-publication-queue-ui` |
| MC-24 / TASK-24 | Record publication events in a transactional outbox | `feature/mc-24-publication-outbox` |
| MC-25 / TASK-25 | Deliver signed webhooks with bounded retries | `feature/mc-25-signed-webhooks` |
| MC-26 / TASK-26 | Refresh Moss Example from publication events | `feature/mc-26-website-events` |
| MC-27 / TASK-27 | Reconcile uncertain saves and expose request timing | `feature/mc-27-save-reconciliation` |
| MC-28 / TASK-28 | Correct schema delivery preview and make form preview interactive | `feature/mc-28-schema-previews` |
| MC-29 / TASK-29 | Suggest schema migrations from explicit field diffs | `feature/mc-29-migration-suggestions` |
| MC-30 / TASK-30 | Improve enum editing and reference confidence | `feature/mc-30-enum-reference-editing` |
| MC-31 / TASK-31 | Add schema outline, accessible reordering and version comparison | `feature/mc-31-schema-outline-history` |
| MC-32 / TASK-32 | Add type templates and safe duplication | `feature/mc-32-type-templates` |
| MC-33 / TASK-33 | Record end-to-end release acceptance evidence | `feature/mc-33-release-evidence` |
| MC-34 / TASK-34 | Document deployment, recovery and new publishing workflows | `feature/mc-34-operator-editor-guides` |

[Release evidence](../release-acceptance-2026-10-08.md) records PostgreSQL/SQLite/frontend checks, restored-database HTTP scenarios, measured conditions, Docker builds and remaining limits. [Operator guide](../deployment-recovery.md) records the separate stopped-app backup/matched-image database/media recovery rehearsal. [Editor guide](../editor-workflows.md) documents final behavior. Optional MC-31/32 were delivered; broader unselected schema ideas remain in [TYPE_IMPROVEMENTS.md](../../TYPE_IMPROVEMENTS.md).

Inspect a branch commit using `git log -1 BRANCH`; MCP artifacts retain the exact implementation hashes. Publication-failure task MC-22 also has a follow-up test-fixture correction in its branch. Main includes all retained task branches; their sequential ancestry intentionally includes preceding completed tasks.
