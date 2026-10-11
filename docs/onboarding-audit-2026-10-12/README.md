# Onboarding audit and screenshot evidence — 12 October 2026

These fifteen saved screenshots record the UI progression from setup through the completed onboarding checklist, mobile editing and example-website publication. They were visually reviewed before inclusion; the setup fields are empty and no password, setup token or delivery credential is visible.

| Screenshot | Visible state |
| --- | --- |
| [Setup](01-setup.png) | First administrator form and MossCMS branding; all credential fields are empty. |
| [First content](02-first-content.png) | Empty content library, checklist at 0/4 and quick-start content-type controls. |
| [New entry](03-new-entry.png) | Article editor with required title, draft/publish/schedule choices and an incomplete draft status. |
| [Saved draft](04-saved-draft.png) | One unpublished Article, draft-save confirmation and checklist at 2/4. Publication remains incomplete and delivery verification is disabled. |
| [Publish selection](05-publish-selection.png) | Saved version-1 Article with Publish now selected; status remains unpublished before submission. |
| [Published](06-published.png) | UI reports one live entry, checklist at 3/4 and a blank delivery-token field. Website display is explicitly not yet confirmed. |
| [Settings](07-settings.png) | Example-test account, workspace/locales and empty delivery-token creation form; no credential is displayed. |
| [Ready](08-ready.png) | UI reports 4/4, one live entry and a successful delivery-check result without exposing the token. |
| [Mobile editor](10-editor-mobile.png) | Narrow editor with saved newer draft, uploaded image and publishing controls; the entry still has a live snapshot. |
| [Mobile checklist](11-checklist-mobile.png) | Completed guide and content library at narrow width; the long page illustrates the vertical-scroll finding. |
| [Example home](12-example-website.png) | Public example homepage displaying the seeded post. |
| [Workspace access hurdle](13-example-workspace-missing.png) | Original administrator's content workspace after normal sign-in; the accompanying API/source evidence records missing example-workspace membership. |
| [Example blog](14-example-blog.png) | Public blog list containing the seeded post. |
| [Missing preview configuration](15-preview-not-configured.png) | Preview action reports that an administrator must configure the website preview origin. |
| [Confirmed website publication](16-confirmed-website-publication.png) | Public post renders the audit's edited body after explicit publication. |

At the initial image-only review, the capture environment, browser version and operator had not yet been documented; the completed trial below now records that provenance. This review inspected the saved images; it did not repeat the browser journey. The images show reported UI states, including 4/4 completion; they do not independently verify exact delivery payloads, website rendering, keyboard recovery or screen-reader behavior. The separate [accepted editing report](../editor-acceptance-2026-10-11.md) retains its own evidence and unverified limits.

## Fresh-instance product trial

The accompanying [full trial report](report.json) now records the capture environment and the actual browser/API walkthrough: Chromium 156.0.8078.4, desktop 1440×1000 and mobile 390×844, using a disposable copy of the working tree and initially empty PostgreSQL/media volumes. The earlier paragraph describes the separate image-only review, not the scope of this trial.

Administrator setup, Article creation, publication, scoped delivery verification, draft/live separation and inline image upload worked. The example website also built and served published content. Its documented setup required disabling authentication and left the new workspace without administrator membership after normal sign-in returned. A local invitation restored access in the disposable instance. Website preview needed a separate trusted-origin setting; it then opened correctly. A subsequent draft remained private until publication, and the edited body was confirmed on the public website in [the final screenshot](16-confirmed-website-publication.png).

All twelve actionable hurdles are saved as **TASK-46–TASK-57** in the existing **MossCMS** Aftur project, with proposed fixes, evidence and acceptance criteria. [Ticket mapping](aftur-tickets.json) links each audit item to its saved task. Prioritize TASK-46 (example-workspace access), TASK-51 (direct checklist actions) and TASK-52 (publishing mode versus action). TASK-47 records the baseline development-port finding; its current status is qualified below.

The proposed streamlined path is: ready local startup → named workspace → starter type → first draft → clear publish action → inline token verification → frontend handoff and preview → compact completed guide. No application code was changed by this audit. Cold installation, external hosting/TLS, OAuth, S3, Safari and screen-reader checks remain unverified.

## Review against the completed README

The audit reproduced an older working-tree snapshot based on `a47713d`. While it was running, the separate README chat committed and pushed [`9321596`](https://github.com/nirtuttnauer/MossCMS/commit/9321596), adding `--port 8001` to the local Uvicorn command. That addresses the primary mismatch reported in ONB-02 / TASK-47. Custom-port guidance and the intended API/proxy isolation checks remain unevaluated in this integration review, so TASK-47 remains proposed. An attributed review note is saved in Aftur at revision 567.

This review checked the report, screenshot contents, evidence references, ticket mapping and relevant source paths. It did not repeat the browser trial or implement the proposed application fixes. The audit's historical observations and original receipt revision are retained; the 12 new tasks remain proposals.
