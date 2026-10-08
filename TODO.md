# MossCMS implementation TODOs

The original starter backlog is implemented. The items below record the delivered scope; deployment-specific OAuth and S3 credentials are configured by the instance owner.

## P0 — required before exposing a real instance

- [x] **T001 — Add authentication and authorization.** Protect the admin UI and editorial GraphQL mutations. Define admin/editor/reader roles, secure session or token handling, password reset, and audit logging. Public delivery clients must not be able to read drafts or call editorial mutations.
- [x] **T002 — Add project/workspace isolation.** Model users, projects, and membership; scope every content query and mutation by the authenticated project. Add tests proving one project cannot access another project's data.
- [x] **T003 — Make deployment configuration safe.** Require secrets in non-development deployments, reject default Postgres credentials outside development, document TLS and trusted origins, and avoid exposing the database port publicly.
- [x] **T034 — Configure browser origins and API access.** Add explicit CORS policy for external frontend clients, and decide which GraphQL operations are available to delivery tokens versus authenticated editors.

## P1 — core CMS capability

- [x] **T010 — Add user-defined content types.** Build a schema registry with field definitions (text, rich text, number, boolean, date, enum, object, list, reference, and asset), validation, schema versioning, and safe GraphQL types/resolvers generated from the registry.
- [x] **T011 — Complete entry editing.** Add read/update/delete workflows to the admin, server-side validation and useful GraphQL errors, slug normalization and uniqueness handling, and an editor for the supported field types.
- [x] **T012 — Add publishing history.** Track revisions and authors, provide preview/restore, add scheduled publishing, and make draft/publish transitions explicit.
- [x] **T013 — Add localization, references, and media.** Support localized field values, reference validation/resolution, and S3-compatible asset upload/storage with metadata and delivery URLs.
- [x] **T014 — Add scalable content queries.** Provide cursor pagination, stable ordering, status/type filters, field filters, and bounded query complexity; update the UI to use server-side pagination and filters.
- [x] **T015 — Separate editorial and delivery APIs.** Give frontend clients a published-only read path with scoped delivery tokens, predictable caching/ETags, and configurable field exposure.

## P2 — complete the admin experience

- [x] **T020 — Wire up admin controls.** Implement navigation/routes for Overview, Assets, Content types, Settings, and API explorer; make type selection, sorting, status filtering, row actions, and pagination functional. Replace the hard-coded API status and counts with live service data.
- [x] **T021 — Improve accessibility and interaction states.** Give the entry modal dialog semantics, focus management, Escape handling, and visible validation; add accessible names/tooltips for icon-only responsive navigation and clear loading, empty, and error states.
- [x] **T022 — Improve authoring workflow.** Generate a slug from the title with an editable override, preserve form values on errors, confirm recoverable deletes, and show a clear save/publish result.

## P2 — operations and reliability

- [x] **T030 — Add database migrations.** Replace startup `create_all` with Alembic migrations, define upgrade/downgrade policy, and test migrations against an existing database.
- [x] **T031 — Harden persistence errors.** Validate IDs, titles, slugs, and status at the API boundary; map uniqueness and constraint failures to typed GraphQL errors; handle concurrent writes and roll back failed transactions cleanly.
- [x] **T032 — Make demo data opt-in.** Gate the welcome article behind an explicit development seed option and provide a repeatable seed command that never inserts demo content into production by default.
- [x] **T033 — Add production health and observability.** Add database-aware readiness, container health checks, structured logs, request IDs, metrics, graceful shutdown, and actionable startup failures. Serve static assets with correct 404/HEAD behavior instead of treating every unknown URL as the SPA entry point.
- [x] **T040 — Make builds reproducible and maintainable.** Commit a web package lock and use `npm ci`; pin or deliberately update base-image versions; add dependency update and vulnerability review guidance.
- [x] **T041 — Document backup and recovery.** Add PostgreSQL backup/restore commands, volume recovery guidance, and a tested upgrade procedure for self-hosters.
- [x] **T050 — Add automated checks.** Cover GraphQL queries/mutations, authorization boundaries, migrations, and UI states; run Python formatting/type/lint checks and frontend type/build checks in CI.


## Additional requested features

- [x] Team management: administrator/editor/reader roles, invitation acceptance and revocation, membership removal, last-administrator protection, and workspace switching.
- [x] OAuth sign-in: GitHub and generic OIDC, invitation-gated onboarding, verified emails, and explicit authenticated account linking.

## Verification

- Python lint, formatting, and mypy checks pass.
- All 21 backend tests pass; the suite covers authentication, tenant isolation, authorization, publishing, history, migration, recovery, OAuth business rules, and local/S3 asset behavior.
- The Docker build passes frontend type checks, seven UI tests, and the production Vite build.
- npm audit reports zero vulnerabilities for the locked dependency graph.
- Local media restoration into an empty volume passed.
- The pre-upgrade PostgreSQL backup was restored into a separate empty database and migrated successfully; the original Article and initial schema history were preserved.
- A separate PostgreSQL integration check passed sign-in, schema creation/deletion, publishing, JSON field filtering, and scoped delivery.
- Live app and database containers are healthy; the setup page, readiness endpoint, and unknown-path 404 behavior were checked.

External provider exchanges and a real S3 bucket require owner-supplied credentials. Recovery/invitation links are shared manually. Rich-text fields currently store text rather than a portable block document format.
