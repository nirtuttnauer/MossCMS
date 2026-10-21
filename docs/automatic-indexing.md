# Automatic scalar indexing

MossCMS automatically maintains lookup and ordering indexes for top-level, non-localized text, rich-text, enum, date, number and boolean fields. Administrators do not need to create an index for each content type or field. Both PostgreSQL and SQLite use the same projection contract.

Draft and published values are indexed separately. A draft edit cannot replace a live filter value. Saving, publishing, unpublishing, scheduled publication, revision restoration, content-type moves and schema migrations maintain the projection in the content transaction. A failed transaction rolls back both content and indexes. New fields are indexed when their values are saved; removed values lose their lookup rows.

## Query behavior

The internal `entry_field_indexes` table stores entry/workspace/type identity, the snapshot, the field name and a typed SHA-256 hash stored as 32 binary bytes. A single covering B-tree lookup index serves all eligible fields. Hash keys have fixed size, including for large strings and strings containing escaped null characters; stored content is not converted to JSONB. Internal hashes are derived data, not secrets or anonymized content, and are not exposed through the content API.

Entry reads first find candidate IDs in the appropriate workspace/type/snapshot index, then recheck the original JSON comparison. String-filter totals use the type-qualified hash plus exact binary projection value, avoiding JSON parsing for every matching document; numeric/boolean/coercion totals retain their original comparison. This recheck preserves equality semantics even if hash candidates collide. Numbers normalize to the float representation used by numeric filters; booleans and strings have separate type prefixes. Workspace scope, token scope, private-field restrictions, publication state, sorting and cursor checks still apply.

String totals check hash candidates and exact-value candidates separately through the existing covering indexes. A `CASE` membership predicate prevents PostgreSQL generic prepared plans from turning a common filter into thousands of primary-key entry probes. Long strings still recheck the full binary value. PostgreSQL index-only scans depend on normal vacuum/visibility conditions. Named content types are authorized by `get_type` before querying their entries; untyped delivery lists retain the token-scope subquery. No additional index, migration, or prepared-statement setting is required.

Null/missing filters and cross-type coercions such as `price: "2"` keep their existing JSON query. Localized fields, nested/list queries and ranges keep their existing paths. Existing pagination/schedule indexes remain in place. This automatically maintains supported lookup/ordering indexes; it does not inspect traffic or generate arbitrary DDL in response to queries.

## Title and slug substring search

PostgreSQL migration 0014 installs `pg_trgm` if missing and adds separate multicolumn GIN indexes for draft and published titles/slugs. The published index excludes entries without a published slug. PostgreSQL maintains these indexes with the content transaction; no projection worker or new application dependency is required. `search` keeps its existing bounded, escaped, case-insensitive substring semantics and exact database recheck. Draft edits stay separate from live search. Current schema privacy excludes private titles, including after a schema change; public slugs remain searchable. Workspace and token scopes still apply.

SQLite keeps its existing substring query. Short, punctuation-only or broad terms can still require scans; trigram indexing is not ranked full-text search or a general index over document bodies. GIN adds storage and write/vacuum work, measured separately in the benchmark. See [PostgreSQL trigram support](https://www.postgresql.org/docs/17/pgtrgm.html).

An operator can preinstall `pg_trgm`, or the migration user needs extension-install permission. Populated index creation is transactional and can block writes, so use a maintenance window. Downgrade drops the two search indexes and retains the potentially shared extension.

## Sorting schema fields

Use one scalar field with `orderBy` and a `typeKey`; the existing `sort` strings remain supported. The editor exposes ascending/descending choices for scalar fields after selecting a content type.

```graphql
query Products($after: String) {
  entries(typeKey: "product", first: 20, after: $after,
          orderBy: {field: "price", direction: ASC}) {
    nodes { id slug data }
    endCursor
    hasNextPage
  }
}
```

Text, rich-text and enum fields sort by Unicode/UTF-8 ordinal value; numbers use exact numeric order, booleans sort false before true, and dates sort by calendar day. Equal values use the entry ID in the same direction. Missing/null values appear last in both directions. Localized maps, nested objects, references, assets and lists require a different ordering contract and are rejected. Private fields cannot be used by delivery tokens. Editorial ordering uses the current draft; delivery ordering uses the published snapshot.

The projection stores a bounded 1,024-byte binary prefix, reusing it as the full sort value for short scalars. Only long scalars store an additional full binary value. A shared B-tree index on workspace/type/snapshot/field/prefix/entry ID serves short scalar values in either direction. A partial calendar-date index excludes rows without a parsed date and avoids ordering dates by their textual representation. When a field contains long values, prefix plus full value plus ID preserves exact order; this path can require additional sorting. A small partial index detects such fields without scanning all projection rows. The database still chooses its execution plan; selective filters and unusual distributions need measurement.

Cursors bind the workspace, content type, field/type, direction and draft/live snapshot, and include the last value and ID. Treat them as opaque continuation values, not secrets or stable bookmarks across content edits. Long values produce larger cursors, bounded to 1 MiB. Changing a field sort requires restarting pagination.

`total` is calculated only if selected in GraphQL, once even when selected through multiple aliases/fragments. Omit it for bounded delivery lists; `hasNextPage` remains available without a count. Existing callers requesting totals retain their behavior.

## Upgrade and repair

Migration **0011** creates and backfills the new empty projection in batches of 100 entries and then creates its lookup index. Fresh/cleared backfills skip per-batch deletes; repair of an existing projection still replaces its rows. Migration **0012** adds the sort columns, clears/rebuilds the derived projection under the upgrade lock, and creates shared ordering/date/long-value indexes. Clearing the derived table before backfill avoids retaining its obsolete PostgreSQL row/index copy. Content/history tables are unchanged. Migration **0013** removes projection rows for references, assets, locale maps and unknown schema fields, converts 64-character hexadecimal hashes to 32 binary bytes, and rebuilds the lookup/long-value index as needed. PostgreSQL rewrites the derived table/indexes; SQLite converts in bounded batches and recreates that table. Only the derived projection changes. Run the normal migration before starting the new application:

```sh
docker compose run --rm app python -m app.cli migrate
```

Stop older app instances/writers before this upgrade and restart all instances on the new version. Older application versions do not maintain the projection. The backfill holds entry row locks until its transaction commits on PostgreSQL. Allow a maintenance window for a large dataset; first-start migration can take longer than earlier index-only upgrades. The model hooks use the active transaction's connection, following [SQLAlchemy's persistence-event contract](https://docs.sqlalchemy.org/en/20/orm/events.html#sqlalchemy.orm.MapperEvents.after_insert).

For recovery after a direct SQL/bulk import that bypassed the ORM, rebuild one workspace explicitly:

```sh
docker compose run --rm app python -m app.cli reindex --project WORKSPACE_ID
```

The repair locks and rebuilds existing entries in one transaction. Schedule large repairs during maintenance. Direct SQL writes do not run the automatic application hooks; indexed reads/totals can be incorrect until the repair commits. Rebuild before serving content modified outside the application. Application imports must use the normal content transaction or maintain/rebuild projections before serving queries. Matched database backups include the projection table.

## Cost and verification

There is at most one lookup row per present top-level scalar field per draft/live snapshot, including private fields used by editorial filters. With the current 40-field schema limit, the upper bound is 80 lookup rows per entry. Scheduled snapshots are indexed only when they become live. Reference IDs, asset IDs, unknown schema fields, and strings in objects or locale maps do not generate rows. Ordering stores binary prefixes, full long values and three additional indexes (date and long-value indexes are partial), increasing storage and write work; ordinary saves replace only changed scalar fields in the changed snapshot. Edits to localized/nested content alone do not rewrite scalar projections. Type/workspace moves, scalar eligibility changes and unknown previous-value history rebuild the affected snapshots.

Regression checks cover snapshot separation, captured scheduled revisions, schema renames, private/scoped delivery, multiple scalar filters, rollback, collision rechecks, populated backfill, repair, deletion and usable lookup plans on both engines. Performance results are recorded separately from correctness checks; previous benchmark numbers describe earlier images.

The [50k indexing follow-up](benchmarks/RESULTS-AUTOMATIC-INDEXING-2026-10-12.md) reports the final query, the rejected slower query, recovery checks and storage cost. In the final 60-second local sample, filtered-read p95 was 430 ms versus 786 ms before automatic indexing; database size increased from 171 MiB to 333 MiB. These are local samples, not production guarantees or sustained 100k validation.
