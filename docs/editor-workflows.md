# Editor workflows

Select the correct workspace before editing. Administrators manage schemas/access; editors manage entries and media; readers can inspect drafts, history and publication queues but cannot save, publish, issue previews or retry schedules.

## Draft, live and scheduled versions

An entry can have a working draft, a live version and a captured schedule at the same time. The **Live** badge describes public availability. **Unpublished changes** means the working data or slug differs from live content. A schedule shows its captured revision and due date separately.

- **Save draft** and autosave change only the working copy. A published page stays live; an existing schedule stays captured.
- **Publish now** replaces the live data and slug with the selected working revision and clears any schedule/failure.
- **Schedule** / **Replace schedule** captures the selected revision, slug and metadata. Later draft edits do not change that capture. Replace the schedule explicitly to include them.
- **Cancel schedule** clears pending/failed publication while keeping live content and the draft.
- **Unpublish** removes public availability, clears scheduling and retains editable data/history.
- Trash removes public availability and schedules. Restore from history/trash produces a draft; it does not republish. Restoring an ordinary historical revision leaves any existing live version and schedule intact.

The date picker uses the displayed browser timezone; the API stores UTC. The scheduler checks approximately every five seconds and checks overdue work at startup. Keep the CMS running. Publication revalidates the captured data and live slug, so a conflicting route or removed reference may fail later even when scheduling originally succeeded.

Open **Publications** for upcoming, overdue and failed captures. A failure shows a code, explanation, original due time and revision; it stops automatic retries and preserves the previous live version. Repair the cause and choose **Retry captured revision** to revalidate/requeue the same capture. To publish newer edits, use **Edit / replace schedule**. **Resolve / discard failed schedule** clears the capture without changing live content. The queue refreshes every 15 seconds and pauses while its editor is open; the content library refreshes every ten seconds while visible.

## Autosave, conflicts and uncertain outcomes

After a short pause, valid edits autosave as drafts. Watch the saved/saving/offline/error/conflict feedback; incomplete or invalid required values may prevent a save. Closing, navigation and browser refresh warn about unsaved work. Keep the tab open while offline or resolving an error: in-memory recovery is not a guarantee of persistence after a browser crash.

On conflict, **Compare server version** shows the newer server data while retaining your form values. Copy changes you need, then explicitly discard/reload or reconcile them. Changing workspace cancels delayed writes for the prior editor.

After a lost publication response, **Check outcome** looks up the operation receipt. **Retry same operation** reuses the captured request and key, preventing duplicate entries/events; it does not silently submit a changed draft. The form remains protected while the outcome is uncertain. “Published in CMS” confirms the database commit. Website refresh remains pending until separately observed; inspect the public page if confirmation matters.

## Markdown and images

Rich-text fields remain strings, now interpreted as Markdown. Use the formatting controls and preview for headings, emphasis, lists, links, fenced code and images. Plain existing text remains readable. Raw HTML does not execute; unsafe URL schemes are excluded. Uploaded images use `![description](asset:ASSET_ID)`, keeping an asset ID rather than an expiring URL.

Blog posts/projects have optional covers; projects also have ordered galleries with optional Markdown captions. Search or page through image thumbnails, choose an uploaded JPEG/PNG/WebP raster, set meaningful alt text and optionally focal percentages/cover-or-contain fit. Gallery buttons support keyboard reordering. Non-image IDs and assets from another workspace are rejected. Missing media has a fallback.

New eligible uploads generate bounded WebP sizes without upscaling. Older uploads have no automatic variant backfill; reupload an image to obtain responsive cover/gallery variants. SVG and other non-variant formats remain original downloads. See [image limits and storage rules](images.md).

## Preview a saved website revision

An administrator first sets **Settings → Website preview → Website preview origin** to the exact trusted site origin. The website's server delivery token must cover the selected workspace and type. From a website entry, choose **Save draft & prepare website preview**, then open the saved revision link. Issuance is restricted to editors/admins; the URL is a secret bearer capability, not a viewer sign-in requirement. Do not share it.

The grant lasts 15 minutes and is bound to one saved revision. The website strips the fragment credential and uses an HttpOnly session. A persistent banner identifies preview mode and provides **Exit preview**. Only the selected entry/slide is replaced; private fields remain absent and other visitors keep public content. Every fetch revalidates the grant, issuer access and delivery scope. Revocation, expiry, removal of editing access or a website restart ends access. Use **Revoke preview** in the editor to end it explicitly. Preview responses are no-store/noindex and never enter feeds or the shared public cache.

## Schema editing

Administrators can start from Article, Product, Person or Event templates, copy a type under a new key, or duplicate a field with a new name. The interactive form preview uses temporary values only. The delivery preview shows the generated public shape, including locale arguments and private-field exclusions; optional content fields remain nullable even when editorial validation requires them.

Enum choices validate inline. Reference targets must exist in this workspace (self-references are allowed); zero entries is a warning. Collapse field cards, use the outline to jump to nested fields, reorder with accessible buttons and compare stored schema versions. Migration suggestions require explicit selection/review; they never run automatically. Nested transformations or ambiguous renames require a manually reviewed migration. Saving a schema validates working, live and scheduled data together; old history remains immutable and must validate when restored.
