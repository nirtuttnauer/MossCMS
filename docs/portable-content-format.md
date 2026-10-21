# Portable content format

CMP-02 implementation, 14 October 2026. The admin UI and operator CLI export and import version-1 workspace archives and apply declarative transforms. Schemas, content, references, asset bytes, and selected history travel together. A 1,000-entry local round trip verifies locales, nested references, original/variant bytes, independent source snapshots, history, dry runs, rollback, and retry. The Sanity adapter remains planned.

## Admin UI

Workspace administrators can open **Import & export** from the sidebar or Settings. Export options select entry history and private fields before downloading a ZIP. Imports accept archives up to 64 MiB through the browser; the operator CLI supports larger archives within the format limits.

Select the empty destination workspace, upload an archive, and choose **Validate import**. Validation commits no content or media. It shows source schemas, counts, private-field omissions, and applied transforms. Add/reorder/remove rename, default, drop, and conversion steps. Open **Source schemas → Customize destination schemas** to use the normal visual field editor for destination names, field types, required/localized/private flags, nested fields, references, and lists. Advanced schema JSON is also available. Validate the updated plan, review its results, and choose **Import reviewed archive** followed by the destination-specific confirmation.

Any edit to the archive, steps, or schema overrides invalidates the client review. The server additionally binds its signed review to the archive/pipeline checksum, workspace, and administrator, and expires it after 15 minutes. Applying without a matching review fails before content writes. Destination emptiness, membership, schemas, assets, and references are validated again during import. Retrying after an interrupted response can check the same archive/pipeline without duplicating a committed import.

Browser endpoints are `/api/migration/limits` (GET), `/api/migration/export` (POST form), and `/api/migration/import` (POST multipart). They require administrator access; export/import also require the session CSRF header. They accept uploaded archives rather than server file paths. Temporary downloads are removed after the response and temporary uploads after processing. Uploads are capped at 64 MiB, transform JSON at 256 KiB. Proxy deployments must permit at least 65 MiB multipart bodies and migration request durations; smaller proxy limits remain an additional deployment constraint.

Browser verification used an isolated local SQLite workspace: upload, dry run, visual destination field edit, `headline → title` transform, revalidation, confirmation, and the resulting unpublished draft in the content list. Desktop and 375px layouts were inspected; the mobile document stayed within its viewport width. Escape closed the confirmation dialog and restored focus to the import action. The production frontend build and all 301 frontend tests passed; backend tests cover role/CSRF boundaries, changed/foreign reviews, retry, upload limits, and the local development identity. Live PostgreSQL/S3 and spoken screen-reader testing remain unverified.

## Commands

Run from `api/` with the configured database and media settings. Exports use a consistent database snapshot; imports lock the destination against concurrent content-type creation and media uploads. SQLite imports hold its write transaction. Direct database writers that bypass the application should be stopped during migration. Create the destination workspace and its administrator membership first; the commands require that administrator's email and an explicit workspace ID. This is an operator tool that requires server access. In explicitly enabled local development auth bypass, the existing local developer identity retains the same administrator access as the UI.

```sh
uv run python -m app.cli export --project SOURCE_ID --email admin@example.com --file /secure/source.zip --history

# Validate and report without retaining database changes or writing media.
uv run python -m app.cli import --project DESTINATION_ID --email admin@example.com --file /secure/source.zip

# Validate again, then commit the draft set and media.
uv run python -m app.cli import --project DESTINATION_ID --email admin@example.com --file /secure/source.zip --apply
```

The JSON result includes counts, schema versions, source-to-destination IDs, private-field omissions, and publication behavior. A failed validation exits nonzero with its reason/path. `--history` selects existing entry revisions; schema history and previously imported provenance are always preserved. `--include-private` explicitly includes private content and labels the archive as sensitive. Author identities are omitted. Accounts, credentials, invitations, integrations, and workspace origin settings are excluded. Destination locale settings follow the source; its name, members, and access settings remain destination-owned.

Imports create new working drafts. Source trash stays trashed. Published and scheduled source snapshots, original schema versions, original IDs, selected history, and the mapping for their referenced entries/assets are retained in the imported entry's initial immutable revision under `snapshot.imported`. They are carried by subsequent exports even without `--history`. They are provenance rather than active publication, schedules, or separately restorable destination revisions; an operator can inspect the archive and explicitly recreate the desired state through normal content editing. No overdue schedule is activated.

## Ordered transform pipeline

Pass `--pipeline /secure/pipeline.json` to either an import dry run or `--apply`. Steps run in order on every working, published, and scheduled snapshot before reference remapping and destination validation. The original source snapshots/history remain unchanged in provenance. Supply the complete destination fields for any schema you change:

```json
{
  "schemas": {
    "article": {
      "fields": [
        {"name": "title", "type": "text", "required": true},
        {"name": "count", "type": "number"}
      ]
    }
  },
  "steps": [
    {"typeKey": "article", "op": "rename", "path": "headline", "to": "title"},
    {"typeKey": "article", "op": "rename", "path": "amount", "to": "count"},
    {"typeKey": "article", "op": "convert", "path": "count", "to": "number"},
    {"typeKey": "article", "op": "default", "path": "title", "value": "Untitled"},
    {"typeKey": "article", "op": "drop", "path": "obsolete"}
  ]
}
```

Omit `typeKey` to apply a step to every type. Paths address fields in objects, with `*` for list objects or locale maps, such as `sections.*.heading` or `title.*`. Rename stays within the same object and refuses an occupied destination. Default fills an absent field in an existing object, preserving explicit nulls. Drop is an explicit deletion. Convert supports text, finite numbers, and booleans (`true`/`false` strings or existing booleans); invalid conversions stop the import. No supplied code executes. The report identifies each applied step, entry, snapshot, and field path without printing content values.

Every current snapshot must validate against the destination schema. References to trashed entries fail normal MossCMS reference validation, including old links retained in trashed drafts. Resolve those values through an explicit pipeline or source repair; the importer does not silently delete links. Errors identify the source entry, snapshot, and field path.

The same steps work in existing `saveContentType` schema migrations through `migration: {"steps": [...]}`. Legacy `rename`, `drop`, and `defaults` still run first in their existing order.

## Version and layout

Use a ZIP archive containing UTF-8 JSON metadata, line-delimited JSON content, and local asset bytes. Line-delimited JSON permits bounded streaming through larger libraries. The version-1 layout is:

```text
manifest.json
schemas.json
entries.ndjson
assets.ndjson
revisions.ndjson       # empty unless history is selected
provenance.ndjson      # retained source snapshots/history from earlier imports
assets/SHA256         # original or variant bytes, deduplicated by hash
```

The manifest identifies `format: "mosscms.content"`, `version: 1`, UTC export time, source workspace ID/name/locales/default locale, counts, history selection, private-field inclusion, omissions, and SHA-256/byte-length values for every payload file. A version the importer cannot understand fails before database writes. The schema file preserves content-type keys, names, versions, complete supported field definitions, and schema history. Active destination schemas start at version 1; original versions stay in provenance. It contains no access credentials or executable extensions.

## Content records

Each entry has a source ID, type key, and independent `draft`, `published`, and `scheduled` snapshots. Snapshot objects carry the slug, data, revision/schema version, and relevant UTC publication/due time; absent public or scheduled snapshots are null. The draft also records the current optimistic version. IDs in references and asset fields point to source IDs in this bundle, including references inside objects/lists and durable media IDs in Markdown. Target IDs are remapped consistently at import time.

Asset records contain source ID, display name, MIME type, dimensions, byte length, SHA-256, and a bundle path for original bytes and each selected variant. Storage credentials, backend keys, bucket names, and expiring download URLs are excluded. Exporting S3 assets requires reading authorized source objects into the bundle; missing files stop completion or appear as explicit unresolved assets in a dry-run report. A metadata-only archive cannot claim to be a complete portable export.

Selected history records identify their entry, original revision number, timestamp, and stored snapshot. Old values remain even when they do not validate against today's schema. History remains immutable provenance, with original IDs rather than live destination references. Author names/emails are omitted. Historical revisions do not automatically become new live or scheduled content.

## Private data and publication

Require workspace administrator access to export and to select the destination. Omit private fields by default from schemas, all snapshots, and history; list every omitted field path in the report. Explicitly including private fields produces a sensitive content archive and must be labeled in its manifest. Accounts, password hashes, sessions, OAuth credentials, delivery/preview grants, invitations, webhook secrets, and trusted-origin settings are never part of this content format.

Imported working values become drafts by default. Published and scheduled source snapshots remain preserved provenance with an explicit operator selection required to recreate publication or scheduling. A dry run must identify how those source states will be stored and cannot silently discard them. Importing historical timestamps does not execute overdue schedules.

## Import validation and recovery

The initial destination is an explicitly selected empty workspace. Validate the complete manifest and all checksums before activation. Reject absolute paths, path traversal, duplicate archive names/record IDs, links, malformed JSON, unsupported versions, oversized records, invalid schemas, unresolved references, and slug conflicts. Asset bytes obey the existing upload/image rules. Apply bounded limits to decompressed bytes and compression ratios to avoid archive bombs; expose larger limits only as deliberate operator configuration.

The importer stages checksum-verified payloads in a private temporary directory and validates destination records within a database transaction. All required references, snapshots, and assets validate before any media writes. Dry runs roll back that transaction. IDs derive from destination ID, archive SHA-256, pipeline, and source ID; a committed audit receipt makes retries no-ops even after later edits. A different archive or pipeline cannot overwrite a populated destination. On handled errors, database changes roll back and newly written media is removed. After a process interruption, retry from the original archive and pipeline: matching deterministic local media is verified and reused. Temporary validation is restarted rather than resumed from a persistent staging database. The dry-run ID mapping also identifies orphan media for manual cleanup. Archive files use mode `0600`; interrupted exports retain `.partial` until finalized and never overwrite a completed export.

Version 1 caps decompressed payloads at 512 MiB, each NDJSON record and the manifest at 2 MiB, each record collection at 50,000, archive files at 100,000, compression ratio at 200:1, and nested prior-import provenance at eight levels. Per-entry provenance must also fit the record limit before an import commits. Asset originals/variants obey the configured upload limit and raster decoding checks. Exports use stored ZIP payloads to avoid rejecting highly repetitive content under the ratio check. Metadata is loaded within these fixed bounds. Browser migrations run synchronously with loading/error feedback; this implementation does not provide persistent background jobs or an unbounded streaming import.

The dry-run report includes source/destination schema mappings, counts, private-field omissions, source/destination IDs, transformations, and publication behavior. A successful report means checksums, asset integrity, slug uniqueness, reference closure, and destination schema validation passed. Validation stops on the first error with its reason and field path where available. A successful report and a committed import have distinct `applied` values. The automated fixtures include a 1k-entry round trip, corrupt/unsafe archives, failed commit/storage cleanup, interrupted media reuse, private historical data after a type move, re-exported provenance, and mocked S3 transfers. A live PostgreSQL/S3 deployment rehearsal remains unverified.

## Sanity adapter boundary

Accept an authorized [Sanity dataset export](https://www.sanity.io/docs/content-lake/exporting-data) and an explicit schema/field mapping. Sanity exports include line-delimited documents and can include asset binaries; an [Export API stream](https://www.sanity.io/docs/http-reference/export) includes drafts and asset documents but does not by itself establish that all required binary files were collected.

Pair draft/published variants by source identity without treating each as a separate MossCMS entry. Handle release variants explicitly rather than selecting one silently. Map references, assets, localized structures, and slugs using the supplied schema mapping. Preserve the source IDs and source values in a transformation report so a partial conversion can be traced and retried.

[Portable Text](https://www.sanity.io/docs/studio/block-type) supports custom blocks, annotations, and inline objects beyond MossCMS's current Markdown representation. Start with ordinary paragraphs, headings, supported lists/emphasis/links, and known image blocks. Unsupported blocks or annotations stop activation and appear with their exact source paths. No lossy plain-text fallback or implicit deletion is allowed. The dry run must list every conversion before an operator applies it.
