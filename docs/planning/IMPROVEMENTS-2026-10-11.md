# MossCMS improvement backlog — 11 October 2026

Help self-hosting owners and small editorial teams reach their first published entry, complete daily editing without losing context, and recover confidently from errors. Extend the shipped MC-01–MC-34 baseline rather than repeat it.

These began as assistant product-management proposals requested by the owner. The owner subsequently authorized implementation with “continue” and “use subagents to do these in parralel.” TASK-35–TASK-44 are implemented and awaiting human acceptance; TASK-45 has partial browser evidence and remaining manual checks documented in [the acceptance report](../editor-acceptance-2026-10-11.md). Priorities, effort and success targets remain estimates rather than measured outcomes. The shipped MC-01–MC-34 work was checked against implementation/release documentation rather than treating stale proposed statuses as unfinished scope.

## Recommended sequence

Address truthful bulk-trash recovery, complete reference selection, and actionable validation first. Then improve first-use onboarding and navigation. Verify that iteration in actual browsers before adding convenience features, locales and historical redirects. P1 means next iteration; P2 means follow-on. Effort is relative, not a time commitment.

| Order | Ticket | Aftur ID | Priority | Relative effort |
| --- | --- | --- | --- | --- |
| 1 | MC-41 — Report partial bulk-trash results and retry only unresolved entries | TASK-41 | P1 | S–M |
| 2 | MC-37 — Find and select references beyond the first 100 entries | TASK-37 | P1 | M |
| 3 | MC-38 — Show validation errors beside the fields editors must fix | TASK-38 | P1 | M |
| 4 | MC-35 — Guide new workspaces to their first published entry | TASK-35 | P1 | M |
| 5 | MC-36 — Make entry links and content-list context survive navigation | TASK-36 | P2 | M |
| 6 | MC-45 — Verify the next editing release in real browsers and assistive technology | TASK-45 | P1 | M |
| 7 | MC-39 — Compare entry revisions and live content in readable form | TASK-39 | P2 | M |
| 8 | MC-40 — Duplicate an entry into a new unpublished draft | TASK-40 | P2 | S–M |
| 9 | MC-43 — Upload and select media without leaving the entry editor | TASK-43 | P2 | M |
| 10 | MC-42 — Configure workspace locales and use the default in new entries | TASK-42 | P2 | M |
| 11 | MC-44 — Preserve previously published website URLs after slug changes | TASK-44 | P2 | L |

## Ticket details

### MC-35 — Guide new workspaces to their first published entry

Aftur: **TASK-35** · P1 · Effort: M

As a new workspace owner, I want a short guided path from defining content to reading a published entry so I can understand whether MossCMS fits my website.

**Problem.** A new owner lands in Content with a prompt to create a type, while publishing and delivery-token setup live on separate screens. Existing type templates help with schemas but do not explain the complete first-use path.

**Scope.** Add a dismissible, resumable workspace checklist: choose or define a type, create an entry, publish it, and verify a delivery query. Reuse existing Article/Product/Person/Event templates and the API explorer. Explain editorial versus delivery access at the point of use and tailor actions to the member's role. Infer completion from real workspace state.

**Out of scope.** New template marketplace, automatic demo publishing, automatic token creation, email onboarding or a hosted service.

**Acceptance criteria**

1. An empty administrator workspace shows the four steps with one actionable next step; switching workspaces does not mix progress, and dismissal survives reload for that user/workspace.
2. Existing content satisfies the relevant steps without creating or overwriting types, entries or tokens; editors/readers see only actions they can perform.
3. The final step verifies a published-only query with a user-selected delivery token; it never marks connection verified without a successful response and never puts a token in a URL or log.
4. A fresh owner can complete the flow using keyboard navigation, and draft saves never satisfy the publish step. Record results from at least three first-use walkthroughs.

**Success measure.** Proposed target: at least 3 of 3 first-use participants independently publish and verify delivery within 10 minutes after sign-in; record sample and obstacles before claiming activation improvement.

**Confidence.** Medium: code confirms disconnected setup steps; activation friction needs user observation

**Baseline relationship.** Extends the delivered MC-32 templates; does not recreate schemas, token permissions or publication state.

**Evidence**

- web/src/pages/App.tsx: Overview links users to separate Types/Content/Settings screens
- web/src/pages/Content.tsx: no-types notice
- web/src/pages/Types.tsx: existing starter templates
- web/src/pages/Explorer.tsx

**Dependencies.** None; build on current main.

### MC-36 — Make entry links and content-list context survive navigation

Aftur: **TASK-36** · P2 · Effort: M

As an editor, I want to bookmark an entry and return to my filtered list so I can resume work and share precise context with teammates.

**Problem.** The admin hash identifies a top-level page, but entries, type/search/status filters and sorting live in React state. Reloading or sharing the page cannot reliably return a teammate to the same entry or list.

**Scope.** Define compatible admin URLs for workspace, entry ID and list filters. Add Copy entry link, restore URL state on direct load, and support browser back/forward between list and editor. Restore list position when practical; reset stale pagination safely. Keep current top-level hash links working.

**Out of scope.** Website routing redesign, new collaboration messaging, global search or storing credentials in links.

**Acceptance criteria**

1. A copied entry link opens that entry after sign-in and reload for an authorized member; denied or missing entries produce a useful access/not-found state without leaking another workspace's title or data.
2. Type, status, search and sort survive reload and back/forward; closing an entry returns to the originating list. Invalid filters/cursors recover to a valid list.
3. Existing unsaved-change guards apply to direct navigation, back/forward and workspace switching; canceling navigation preserves both the form and route.
4. Links contain only identifiers and list context, never session/CSRF/delivery/preview tokens; legacy top-level links still resolve.

**Success measure.** All direct-load, reload, back/forward and workspace-switch scenarios return to the intended authorized context; observe whether editors can resume without rebuilding filters.

**Confidence.** High: list filters and the open entry are local component state

**Baseline relationship.** Admin navigation extension; MC-19 covered public website routes only.

**Evidence**

- web/src/pages/App.tsx: route parses only the top-level hash
- web/src/pages/Content.tsx: type/status/search/sort/editor state

**Dependencies.** None; build on current main.

### MC-37 — Find and select references beyond the first 100 entries

Aftur: **TASK-37** · P1 · Effort: M

As an editor with a growing content library, I want to search all valid reference targets so I can link the correct entry regardless of its age or position.

**Problem.** Reference controls only offer the first 100 entries loaded across all types. A valid target outside that set is unselectable, and a previously saved selection may not have a visible label.

**Scope.** Replace the reference dropdown with a searchable, paginated picker scoped to the workspace and reference target type. Resolve an existing selected ID independently of the first result page. Show title, type and publication state, including a clear explanation when a draft reference will not resolve publicly.

**Out of scope.** Changing reference storage, automatic related-content suggestions or cross-workspace references.

**Acceptance criteria**

1. In a fixture with more than 150 entries across multiple types, an editor can find and select a valid target outside the initial 100; search and pagination respect target type and workspace.
2. A stored selection displays its label even when absent from the current result page; deleted or inaccessible targets show an actionable unavailable state without silently clearing the value.
3. Loading, no-results, error/retry and clearing states are keyboard accessible; stale search responses cannot replace newer results or leak results after a workspace change.
4. Server-side target/workspace validation remains authoritative; drafts are selectable only where existing editorial rules permit them, and published delivery never exposes draft content.

**Success measure.** 100% of valid targets in the >150-entry acceptance fixture are reachable; no hidden first-page limit or lost selection.

**Confidence.** High: editor fetches entries(first:100) and filters references locally

**Baseline relationship.** Completes entry-level reference selection; MC-30 covered schema target validation and empty-target warnings.

**Evidence**

- web/src/pages/Content.tsx: EntryEditor initial entries(first:100) query
- web/src/components/Fields.tsx: references.filter mapped into select
- api/app/content.py: validate_value reference rules

**Dependencies.** None; build on current main.

### MC-38 — Show validation errors beside the fields editors must fix

Aftur: **TASK-38** · P1 · Effort: M

As an editor, I want the failed field highlighted with a clear correction so I can fix my entry without searching the whole form.

**Problem.** Nested and localized validation errors appear as technical text at the bottom of the editor. The autosave required-field check is shallow, so editors may need repeated attempts to discover which value is blocking a save.

**Scope.** Add structured validation paths and reason codes to editorial errors while preserving existing error messages/codes/request IDs. Map errors to nested/list/locale controls, provide a linked error summary, and reveal/focus the failed field on explicit save. Use the same recursive required-field rules for client guidance and autosave readiness; the server remains authoritative.

**Out of scope.** Relaxing schema validation, replacing uncertain-save/conflict handling or applying schema migrations automatically.

**Acceptance criteria**

1. Slug, required scalar, nested object, list-item and locale errors identify the correct visible control; the summary links to that control and associates readable error text using accessible semantics.
2. Explicit save focuses the first invalid control; background autosave reports the problem without repeatedly stealing keyboard focus. Valid false/zero values are not mistaken for missing values.
3. Form values survive rejected writes, and correcting a value clears obsolete local errors; schema/workspace changes cannot attach old errors to new fields.
4. Non-field network, conflict and authorization errors retain their recovery flows and request IDs; old API clients still receive compatible message/code information.

**Success measure.** Editors locate and fix each seeded validation error without reading raw data paths; record first-attempt correction results for nested and localized fixtures.

**Confidence.** High: backend errors embed a data path in text; UI displays a form-level message

**Baseline relationship.** Extends MC-07/MC-09/MC-27 feedback rather than replacing autosave, conflicts or idempotency.

**Evidence**

- api/app/content.py: validate_value/validate_data
- web/src/lib/api.ts: ApiError and gql extensions parsing
- web/src/pages/Content.tsx: requiredComplete and form-error output
- web/src/components/Fields.tsx

**Dependencies.** None; build on current main.

### MC-39 — Compare entry revisions and live content in readable form

Aftur: **TASK-39** · P2 · Effort: M

As an editor, I want a field-by-field comparison of revisions so I can make an informed publish or restore decision.

**Problem.** History and conflict views expose raw JSON, while publication badges only say there are unpublished changes. Editors cannot easily see what a restore or publish would change.

**Scope.** Provide a read-only comparison between saved draft and live snapshot, or two saved revisions. Show labeled additions/removals/changes for nested, localized and list data; render Markdown safely and label assets/references. Display author/time/revision and preserve an optional raw-data view. Confirm restore impact before invoking the existing restore action.

**Out of scope.** Automatic conflict merge, restoring directly to live, schema-history replacement or collaborative real-time editing.

**Acceptance criteria**

1. An editor can compare draft versus live and two historical revisions, including changed slug, Markdown, localized values, nested fields and list order; unchanged fields can be collapsed.
2. Missing live content, removed schema fields and inaccessible assets/references have understandable states; comparison never performs a write or autosave.
3. Restore clearly states that it creates a new draft and preserves live content/schedules, then respects current schema validation and optimistic versions.
4. Readers can compare but cannot restore; Markdown and labels remain safely rendered, and keyboard users can navigate all comparisons.

**Success measure.** In seeded scenarios, reviewers correctly identify all changed public fields and predict the effect of restore without opening raw JSON.

**Confidence.** High: entry history currently shows snapshot JSON

**Baseline relationship.** MC-31 compares schemas, not entry revisions; existing revision storage and restore behavior are reused.

**Evidence**

- web/src/pages/Content.tsx: history snapshot JSON and autosave.server JSON
- api/app/content.py: restore/history functions
- docs/publication-contract.md

**Dependencies.** None; build on current main.

### MC-40 — Duplicate an entry into a new unpublished draft

Aftur: **TASK-40** · P2 · Effort: S–M

As an editor, I want to start from an existing entry so I can produce a similar item without changing or republishing the original.

**Problem.** Editors creating similar projects or posts must manually recreate every field, which is slow and makes repeated structures inconsistent.

**Scope.** Add Duplicate entry for active entries. Copy an explicitly identified saved working revision into an editable new-entry form; propose an editable unique slug and copy title. Preserve localized/nested values and same-workspace references/assets, then create the draft only through the normal explicit save flow.

**Out of scope.** Copying live/scheduled state, history, authorship or preview grants; cross-workspace copy; entry-template system.

**Acceptance criteria**

1. Duplicating creates no record until explicitly saved; the saved copy has a new ID, draft state and independent history, with no live snapshot, schedule or inherited preview grant.
2. The source revision is named clearly; unsaved source edits are saved explicitly or excluded with explanation. The original remains unchanged.
3. Nested/list/locale values are deep-copied; current-schema, reference/asset and slug validation still apply, including a concurrent slug collision.
4. Readers cannot duplicate; failures preserve the new form, and an ambiguous save uses existing idempotent reconciliation rather than creating multiple copies.

**Success measure.** A representative populated entry can be copied and edited without re-entering unchanged fields; zero inherited publication/schedule state in acceptance scenarios.

**Confidence.** Medium: duplicate type exists; entry duplication is absent

**Baseline relationship.** Entry duplication is separate from the delivered MC-32 type/field duplication.

**Evidence**

- web/src/pages/Content.tsx: row actions only Edit/Restore/Trash
- web/src/pages/Types.tsx: existing Duplicate type
- web/src/lib/autosave.ts

**Dependencies.** None; build on current main.

### MC-41 — Report partial bulk-trash results and retry only unresolved entries

Aftur: **TASK-41** · P1 · Effort: S–M

As an editor cleaning a content library, I want a truthful result for each selected entry so I can recover safely from a partial failure.

**Problem.** Bulk trash can delete earlier entries and then stop on a conflict or lost connection. The UI exposes a generic error and retains the original selection, leaving editors unsure which content was removed and which items a retry will touch.

**Scope.** Track per-entry success, failure, uncertain and not-attempted outcomes for the existing bounded page selection. Refresh completed rows, retain unresolved items, show counts and actionable reasons, and retry only confirmed unresolved entries after checking current versions/status. Explain that trash removes public availability and cancels schedules.

**Out of scope.** Bulk publish, cross-page select-all, permanent deletion or introducing a generic bulk-job service.

**Acceptance criteria**

1. With five selected entries and a forced failure on the third, the result identifies two completed, one failed and two not attempted; counts/selection/list agree with server state.
2. After a response is lost, the client reconciles the item's current status before reporting success or retrying; confirmed completed entries are excluded from subsequent attempts.
3. Conflict retries require fresh versions and an explicit user retry; permission changes are respected, and one failure cannot be presented as success for the entire batch.
4. The confirmation explains live/schedule impact; the result provides a route to Trash/history for recovery, uses accessible announcements, and preserves workspace isolation.

**Success measure.** Every item in success/conflict/network-interruption fixtures has a truthful outcome; zero retries of entries already confirmed trashed.

**Confidence.** High: remove() sequentially deletes and stops on the first exception

**Baseline relationship.** Improves existing bulk trash recovery; reuses publication state and MC-27 uncertain-outcome principles.

**Evidence**

- web/src/pages/Content.tsx: remove() sequential mutation loop and catch
- web/src/pages/Content.tsx: bulk selection and trash dialog
- docs/publication-contract.md: trash interactions

**Dependencies.** None; build on current main.

### MC-42 — Configure workspace locales and use the default in new entries

Aftur: **TASK-42** · P2 · Effort: M

As a multilingual workspace owner, I want a default locale and suggested locale list so new entries start in the language my team uses.

**Problem.** Every new localized field starts with en, and editors manually enter locale codes. Teams authoring Hebrew or other languages repeatedly correct defaults and risk inconsistent locale keys.

**Scope.** Add administrator-managed default/suggested locale settings with a backwards-compatible en default. Apply them recursively to new-entry localized field initialization and present a locale picker while retaining valid pre-existing locale keys. Show which locales are present/missing without inventing delivery fallback rules.

**Out of scope.** Automatic translation, changing delivery fallback semantics, mandatory migration of existing locale maps or a website localization redesign.

**Acceptance criteria**

1. Only administrators can update validated, unique locale settings; existing workspaces behave as before until configured, and settings are isolated per workspace.
2. New localized fields use the configured default at supported nested levels; existing entry values and locale keys are never silently renamed or deleted.
3. Editors choose suggested locales without typing codes; removing a suggestion does not erase stored translations, and invalid/duplicate additions receive usable feedback.
4. Localized plain text/Markdown authoring supports appropriate text direction for Hebrew/Arabic without forcing identifiers or code blocks into that direction; validation and delivery behavior remain compatible.

**Success measure.** A Hebrew-default workspace creates a localized draft without manually replacing en; upgrade preserves all existing translation maps.

**Confidence.** High: initialData hard-codes en; locale entry is free text

**Baseline relationship.** Explicit follow-up outside MC-01–MC-34; extends existing locale maps rather than replacing them.

**Evidence**

- web/src/pages/Content.tsx: initialData localized en
- web/src/components/Fields.tsx: newLocale text input
- web/src/pages/Settings.tsx
- TYPE_IMPROVEMENTS.md: workspace default locales follow-up

**Dependencies.** None; build on current main.

### MC-43 — Upload and select media without leaving the entry editor

Aftur: **TASK-43** · P2 · Effort: M

As an editor, I want to upload a missing image where I am selecting it so I can finish my post without switching screens.

**Problem.** An editor attaching a new cover or gallery item must leave the entry flow to upload through Assets, then find the file again in the picker. This interrupts authoring and adds navigation around an unsaved form.

**Scope.** Add an Upload action to AssetPicker for authorized editors/admins using the existing upload endpoint. Validate the field's accepted media and documented limits, show upload state and errors, and select the successfully uploaded asset in the current field. Reuse this for cover/gallery items while preserving the form.

**Out of scope.** New image-processing formats, bulk asset ingestion, deletion/cleanup policies or automatically publishing the entry.

**Acceptance criteria**

1. An editor uploads and selects a new image from a cover or gallery picker; the surrounding entry data remains intact and the draft/live/schedule state changes only through existing save/publication behavior.
2. imageOnly pickers reject unsupported formats and oversized files with readable guidance; the server enforces the same limits and processing rules.
3. Progress/busy, success and retry states are visible and keyboard accessible; a workspace switch or closed picker prevents the result from attaching to the wrong entry.
4. Readers cannot upload; a failed upload retains form values, and uncertain outcomes never cause an automatic duplicate upload. Signed URLs are refreshed through normal asset reads.

**Success measure.** Complete the new-cover workflow without leaving the entry editor; no lost form values or unintended publication in failure fixtures.

**Confidence.** High: AssetPicker only selects existing uploads; Assets owns upload UI

**Baseline relationship.** Extends MC-17 picker/gallery authoring; reuses MC-16 processing and existing storage authorization.

**Evidence**

- web/src/components/AssetPicker.tsx: selection-only controls
- web/src/pages/Assets.tsx: upload endpoint flow
- api/app/images.py
- docs/images.md

**Dependencies.** None; build on current main.

### MC-44 — Preserve previously published website URLs after slug changes

Aftur: **TASK-44** · P2 · Effort: L

As a site owner, I want previously shared URLs to keep resolving after I rename a published page so readers can still reach it.

**Problem.** Publishing a changed blog/project/page slug removes its prior canonical route. Existing shared links can break because the website's aliases are derived only from current content.

**Scope.** Record historical public path changes transactionally when publication changes a website entry's live URL. Serve a permanent same-site redirect to the currently published canonical path; resolve repeated renames directly and define a collision policy that rejects ambiguous path reuse with an actionable error. Show the URL impact before publishing a changed slug.

**Out of scope.** Arbitrary external redirects, custom rewrite rules, redirecting draft-only paths or changing all existing route semantics.

**Acceptance criteria**

1. Publishing A→B→C keeps A and B reachable with a permanent redirect directly to C; saving a draft slug alone creates no public redirect or route change.
2. A conflicting new canonical or historical path is rejected before commit with a usable explanation; redirects cannot loop, chain indefinitely or target an external origin.
3. Unpublished/deleted destinations return the normal public unavailable response without exposing draft titles, slugs or metadata; republishing restores only valid mappings under the documented policy.
4. Sitemap/RSS/canonical metadata list current live paths only, and cache invalidation updates redirects. Existing content upgrades without fabricating historical URLs that were never recorded.

**Success measure.** All recorded previously published URLs in rename fixtures reach their current live canonical page in one redirect; no private/draft path exposure.

**Confidence.** High: PRD documents no historical redirect retention

**Baseline relationship.** Follow-up to MC-19–MC-21; those delivered stable routes and legacy aliases without retaining historical published paths.

**Evidence**

- docs/PRD.md: hosting and redirects limitation
- personal-site/server/moss.mjs: current-slug aliases
- shared/routes.mjs
- personal-site/server/pages.mjs
- api/app/content.py: publish state transitions

**Dependencies.** None; build on current main.

### MC-45 — Verify the next editing release in real browsers and assistive technology

Aftur: **TASK-45** · P1 · Effort: M

As a workspace owner, I want the normal editing journey verified in the interfaces my team uses so a passing build does not hide a blocked workflow.

**Problem.** The shipped baseline has API, component and HTTP coverage, but the release report records no actual browser visual walkthrough or assistive-technology review. The next authoring improvements need user-level evidence before release.

**Scope.** Create a repeatable browser acceptance checklist and meaningful smoke coverage for first-use publishing/delivery verification, direct-entry navigation, references outside the first 100, nested validation and interrupted bulk trash. Run desktop Chromium and Safari plus a narrow viewport and a macOS VoiceOver/keyboard walkthrough. Fix failures within these flows and record evidence/remaining limitations.

**Out of scope.** Production deployment, an external service benchmark, a whole-product redesign or claims of universal accessibility conformance.

**Acceptance criteria**

1. Use an isolated workspace and synthetic content; execute the listed flows in Chromium and Safari, including a >150-entry fixture and a forced partial failure, without modifying production data.
2. At a 390px viewport and 200% desktop zoom, primary controls, validation messages and dialogs remain reachable; keyboard/VoiceOver expose labels, focus transitions and recovery announcements.
3. At least one actual browser smoke path asserts that a draft edit preserves live delivery and that publish replaces it; publication success is not inferred from a toast alone.
4. Check in reproducible steps/results with browser versions, observed failures and fixes. No blocking defect remains in the scoped flows; untested scenarios remain explicitly unverified.

**Success measure.** All scoped critical journeys complete with mouse and keyboard, and the documented VoiceOver walkthrough finds no blocker; evidence accompanies the release.

**Confidence.** High: release evidence explicitly excludes browser visual/assistive review

**Baseline relationship.** Complements MC-33's completed local HTTP/component evidence with browser-level checks for the new iteration.

**Evidence**

- docs/release-acceptance-2026-10-08.md: checks still requiring deployment evidence
- web/src/components/ui/dialog.tsx
- web/src/pages/Content.test.tsx

**Dependencies.** TASK-35 (MC-35), TASK-36 (MC-36), TASK-37 (MC-37), TASK-38 (MC-38), TASK-41 (MC-41)

## Import verification

Created and read back 11 proposed tasks through the MossCMS-scoped MCP server. Existing tasks were unchanged. Titles, scope, acceptance criteria and dependencies were verified. Priority and effort are recorded in descriptions because propose_task has no priority/estimate parameters.

All 44 acceptance criteria were verified in the native acceptance-criteria fields and in the ticket descriptions. The current MCP bridge preserved them, unlike the initial 7 October import. The [import receipt](improvements-2026-10-11-aftur.json) records IDs, status, dependencies and verification. The [structured plan](improvements-2026-10-11.json) contains the same scopes and Aftur IDs.
