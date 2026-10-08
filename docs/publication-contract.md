# Publication and scheduling contract

MC-01 · Implementation contract · 8 October 2026

## Records and invariants

An entry has three independent versions. `data`, `slug`, `title` and `version` describe
the editable working copy. An optional live snapshot contains `published_data`,
`published_slug`, `published_title`, `published_at` and `published_revision`. An
optional scheduled snapshot contains `scheduled_data`, `scheduled_slug`,
`scheduled_title`, `scheduled_revision` and the UTC `scheduled_at` due time.
JSON values are copied when captured: subsequent edits cannot mutate a snapshot.
The schema version used for each capture is recorded. Publication revisions refer
to the working revision captured, not a later scheduler bookkeeping revision.

`status` remains a compatibility summary: deleted, scheduled (pending snapshot),
published (live snapshot), or draft. It is not the delivery visibility predicate.
Editorial fields expose `isLive`, `hasUnpublishedChanges`, `publishedAt`,
`publishedRevision`, `scheduledRevision` and any persistent schedule failure.
Comparison includes data, title and slug; an unchanged draft is not labeled dirty
just because its bookkeeping version advanced. A live entry may also be scheduled
and have newer unpublished edits.

Delivery checks for a live snapshot and excludes trash. It uses only live data,
slug, title, publication time and revision for generic and generated fields,
references, search, sorting, pagination and cache content. Private fields are
recursively projected against the current schema and token scopes still apply.
Current schema changes may deliberately change public field shape; a draft save
may not. No delivery response exposes pending snapshot or failure details.

Two independent database unique indexes enforce `(project_id, type_id, slug)`
for working copies and `(project_id, type_id, published_slug)` for live URLs.
Null public slugs are allowed for unpublished entries. Scheduled URLs are checked
again at publication, since another publication may claim them in the meantime.

## Transitions

Every editorial mutation requires workspace membership, editor permission, CSRF
and the current entry version. Schema/type moves require an administrator.
Changes, revisions and audit events commit in the same transaction.

| Action | Working copy | Live snapshot | Schedule |
| --- | --- | --- | --- |
| Create/save draft or autosave | Create/update, advance version | Preserve | Preserve |
| Restore historical revision | Copy old working data/slug into a new validated revision | Preserve | Preserve |
| Publish now | Save selected working data | Atomically replace complete snapshot | Clear pending/failure |
| Schedule / explicitly replace schedule | Save selected working data | Preserve | Capture complete selected revision; clear prior failure |
| Cancel schedule | Preserve data; advance version | Preserve | Clear pending/failure |
| Unpublish | Preserve data/history; advance version | Remove complete snapshot | Clear pending/failure |
| Trash | Preserve recoverable data/history | Remove complete snapshot | Clear pending/failure |
| Restore from trash | Restore as working draft | Remain unpublished | Remain absent |
| Schedule due, valid | Preserve any newer working edits | Replace with captured snapshot | Clear pending/failure |
| Schedule due, invalid/conflicting | Preserve | Preserve | Stop automatic retry; retain captured revision and actionable failure |
| Retry after repair | Explicitly schedule a newly validated working revision | Preserve | Replace failed capture explicitly |

Draft saves no longer cancel a schedule or unpublish. Existing callers can keep
using `saveEntry(status: draft|published|scheduled)`, but must use new
`cancelSchedule` / `unpublishEntry` operations for those actions. Clients must
upgrade if they relied on saving a draft to unpublish. This intentional behavior
change is needed to prevent live-content loss. A regular draft save cannot revive
trash; historical restore is the explicit recovery path.

## Failure and worker semantics

Validation and optimistic-version conflicts roll back the entire operation.
Database uniqueness is authoritative, including concurrent public slug claims.
Workers lock due entries with PostgreSQL `FOR UPDATE SKIP LOCKED`, process each
entry within a savepoint, and atomically clear a successful schedule. A crash
before commit leaves the schedule due; after commit it is no longer selectable.
SQLite is supported for isolated development tests; it is not evidence of the
PostgreSQL concurrent-worker guarantee. No external callback runs in the publish
transaction. A failure records code, explanation, due time and captured revision;
it never removes the previous live snapshot or retries continuously.

## Migration, history and schema changes

Use a forward Alembic migration. Only entries currently marked published receive
a live snapshot; current public body and route metadata are retained. Pending
schedules capture their current working data/version and existing UTC due time.
Draft/deleted entries never become public during backfill. Existing entry IDs,
revision IDs/numbers and historical JSON are retained. Older snapshots without
the new fields are interpreted as working-copy history on restore.

Schema migrations explicitly transform and validate working, live and pending
data together in one transaction. Snapshot schema versions advance; the captured
content revision provenance stays intact. Historical revisions remain immutable
and must validate against the current schema when restored. Type moves validate
all three snapshots against the destination and both slug indexes before commit.
Missing/deleted references are checked at save and again when a schedule is due;
delivery resolves only currently live references within its token scope.

Rehearse upgrades on a separate restored database. Recovery is a matched database
backup and previous application image; downgrading schema alone cannot represent
independent working/live/scheduled versions without losing information.
