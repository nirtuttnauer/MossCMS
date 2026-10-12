# Implementation ledger — 8 October 2026

All 34 baseline tasks were approved by the owner and implemented sequentially on feature branches from main. The branches were fast-forwarded into local `main` in dependency order. No Git remote was configured, no pull requests were created and no public deployment was performed during that implementation.

This ledger records implementation. `TASKS.md` and `tasks.json` retain the original planning scope/status with an execution annotation. Release evidence records actual verification and remaining limits.

| Plan ID | Scope | Retained branch |
| --- | --- | --- |
| MC-01 | Define the publication and scheduling state contract | `feature/mc-01-publication-contract` |
| MC-02 | Migrate complete live and scheduled snapshots | `feature/mc-02-snapshot-migration` |
| MC-03 | Separate draft saves from live GraphQL delivery | `feature/mc-03-independent-live-delivery` |
| MC-04 | Publish the captured scheduled revision safely | `feature/mc-04-immutable-schedules` |
| MC-05 | Add explicit unpublish and schedule-cancel actions | `feature/mc-05-publication-actions` |
| MC-06 | Show live, draft and scheduled state in the admin | `feature/mc-06-editorial-state` |
| MC-07 | Protect unsaved entry and schema edits | `feature/mc-07-unsaved-edit-protection` |
| MC-08 | Provide a conflict-safe draft autosave contract | `feature/mc-08-draft-autosave-api` |
| MC-09 | Add debounced entry autosave and recovery feedback | `feature/mc-09-autosave-recovery` |
| MC-10 | Add Markdown authoring controls and preview | `feature/mc-10-markdown-authoring` |
| MC-11 | Render Markdown consistently on Moss Example | `feature/mc-11-website-markdown` |
| MC-12 | Issue scoped expiring preview grants | `feature/mc-12-scoped-preview-grants` |
| MC-13 | Add secure website preview sessions | `feature/mc-13-website-preview-sessions` |
| MC-14 | Open saved website previews from the editor | `feature/mc-14-editor-previews` |
| MC-15 | Define covers and project gallery fields | `feature/mc-15-cover-gallery-contract` |
| MC-16 | Generate bounded image variants for local and S3 assets | `feature/mc-16-image-variants` |
| MC-17 | Improve image picking and gallery authoring | `feature/mc-17-image-picker` |
| MC-18 | Display blog covers and project galleries | `feature/mc-18-website-images` |
| MC-19 | Replace hash routes with stable website paths | `feature/mc-19-website-routes` |
| MC-20 | Serve per-page metadata in initial HTML | `feature/mc-20-initial-metadata` |
| MC-21 | Add published-only sitemap and blog RSS | `feature/mc-21-public-feeds` |
| MC-22 | Persist structured publication failures | `feature/mc-22-publication-failures` |
| MC-23 | Build the upcoming and failed publication queue | `feature/mc-23-publication-queue-ui` |
| MC-24 | Record publication events in a transactional outbox | `feature/mc-24-publication-outbox` |
| MC-25 | Deliver signed webhooks with bounded retries | `feature/mc-25-signed-webhooks` |
| MC-26 | Refresh Moss Example from publication events | `feature/mc-26-website-events` |
| MC-27 | Reconcile uncertain saves and expose request timing | `feature/mc-27-save-reconciliation` |
| MC-28 | Correct schema delivery preview and make form preview interactive | `feature/mc-28-schema-previews` |
| MC-29 | Suggest schema migrations from explicit field diffs | `feature/mc-29-migration-suggestions` |
| MC-30 | Improve enum editing and reference confidence | `feature/mc-30-enum-reference-editing` |
| MC-31 | Add schema outline, accessible reordering and version comparison | `feature/mc-31-schema-outline-history` |
| MC-32 | Add type templates and safe duplication | `feature/mc-32-type-templates` |
| MC-33 | Record end-to-end release acceptance evidence | `feature/mc-33-release-evidence` |
| MC-34 | Document deployment, recovery and new publishing workflows | `feature/mc-34-operator-editor-guides` |

[Release evidence](../release-acceptance-2026-10-08.md) records PostgreSQL/SQLite/frontend checks, restored-database HTTP scenarios, measured conditions, Docker builds and remaining limits. [Operator guide](../deployment-recovery.md) records the separate stopped-app backup/matched-image database/media recovery rehearsal. [Editor guide](../editor-workflows.md) documents final behavior. Optional MC-31/32 were delivered; broader unselected schema ideas remain in [TYPE_IMPROVEMENTS.md](../../TYPE_IMPROVEMENTS.md).

Inspect available branch commits using `git log -1 BRANCH`. Publication-failure task MC-22 also has a follow-up test-fixture correction in its branch. Main includes all retained task branches; their sequential ancestry intentionally includes preceding completed tasks.
