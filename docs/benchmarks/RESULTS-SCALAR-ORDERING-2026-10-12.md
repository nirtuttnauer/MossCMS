# Scalar ordering: 50k follow-up · 12 October 2026

Migration 0012 adds automatically indexed sorting for scalar schema fields, cursor pagination and lazy GraphQL totals. The existing editor exposes field sorts. The final focused title-sort probe improves latency, with additional storage and slower mixed-load results than the earlier filter-only build. These tradeoffs remain visible in the README graph.

## Conditions

The same deterministic 50,000-entry PostgreSQL fixture and mixed HTTP queries ran for 60 seconds with 20 delivery readers and three draft writers. App/database caps were each 2 CPUs/4 GiB on shared macOS/ARM64 Docker Desktop. The main workspace has 40,000 entries and 24,000 live entries. Telemetry was disabled; the new image contains the opt-in integration but these numbers do not measure its overhead. Original content/history fingerprints were preserved through upgrade.

The [final manifest](2026-10-12-ordering/manifest.json) records source snapshot, image ID, resources, checks and recovery. These are separate local samples, not repeated statistical trials, cloud capacity guarantees or competitor benchmarks. A subsequent SQLite-only partial-index predicate spelling fix was verified separately; it does not change PostgreSQL behavior measured here.

## Mixed workload

Nearest-rank p95 including failed samples. All completed runs below have empty error counters.

| Build | List | Exact filter | Generated query | Draft save | Database size |
| --- | --- | --- | --- | --- | --- |
| [Automatic filters (0011)](2026-10-12-auto-index-conditional/manifest.json) | 250 ms | 430 ms | 644 ms | 364 ms | 332.8 MiB |
| [Initial ordering (superseded)](2026-10-12-ordering-initial/manifest.json) | 308 ms | 886 ms | 815 ms | 401 ms | 654.7 MiB |
| [Compact keys (superseded)](2026-10-12-ordering-compact/manifest.json) | 323 ms | 814 ms | 790 ms | 480 ms | 596.7 MiB |
| [Final ordering (0012)](2026-10-12-ordering/manifest.json) | 308 ms | 509 ms | 802 ms | 411 ms | 440.2 MiB |

The final sample misses the proposed <300 ms list target at 308 ms; draft saves meet the <750 ms target. It remains slower than the earlier automatic-filter sample across these four operations. Extra indexes/write work and shared-host variation prevent attributing each difference to one cause. Repeated trials and sustained 100k validation remain necessary. This is a new sorting capability, not evidence of an across-the-board speedup.

Two changes reduced the initial ordering build's measured storage: short binary keys reuse their prefixes and the date index excludes non-date rows; the migration clears/rebuilds the derived projection under its existing upgrade lock rather than retaining obsolete PostgreSQL rows/index entries. Final database size is about 32% above the filter-only build, and about 33% below the initial ordering build. Physical size includes migration/write allocation; this is not a normalized logical-byte calculation. No content/history table is truncated or rewritten by this projection reset.

## Focused ordering probe and actual plans

After the timed workload, 20 alternating sequential requests for each title-sort method read the same first 20 published entries, without totals. Client p95 was **29.4 ms** for legacy `sort: "title_asc"` and **13.2 ms** for `orderBy: {field: "title", direction: ASC}`. This small warmed, single-client probe is separate from concurrent-load percentiles; it establishes no sustained throughput guarantee.

[Actual application plans](2026-10-12-ordering/checks-50000.json) show the indexed title query using `ix_entry_fields_order` in an index-only scan, returning 21 projection rows for pagination with no explicit sort. Its post-load diagnostic execution took 0.315 ms. The exact-filter plan still uses the covering hash lookup and the existing delivery page index. Diagnostic execution time excludes API/auth/schema/serialization/network time and does not replace the HTTP measurements.

Two ordered pages, date/numeric/boolean/text/enum/rich-text values, null tails, exact large integers, long strings sharing prefixes, private fields, draft/live separation, filters and cursor scope changes are covered by regression checks. SQLite's long-value partial index uses `IS 1`, matching SQLAlchemy's emitted predicate; its actual probe plan is checked to prevent a silent full lookup scan.

## Upgrade and recovery

The populated upgrade from 0008 through 0012 took **17.8 seconds**. Stop older writers and allow a maintenance window: this small local fixture is not a production duration estimate. [The indexing contract](../automatic-indexing.md) documents transactional hooks, repair for direct SQL imports and ordering limits.

Matched database/media fingerprints, delivery/private/workspace/token-scope checks and historical restoration passed. A captured scheduled revision published once across restarts while retaining later draft content. Typed delivery client checks passed over real HTTP. Restore through all verification took **38.8 seconds**, excluding backup creation; the verification now includes ordering probes/plans, so its work differs from earlier recovery reports. Temporary fixture containers/volumes were removed.

Validation: complete suites passed with 343 PostgreSQL API tests, 341 SQLite API tests (two optional skips), and 294 web tests; lint, formatting, mypy, TypeScript and the admin/production image build passed. The final SQLite predicate fix received focused ordering/backfill/repair tests. Actual OTLP export and private-value checks were verified using a loopback Collector.

## Next work

Prioritize repeated/sustained measurements, SQL calls per route, reference/asset batching, count costs and combined filter/order plans. Long-value ordering may need extra sorting; localized/nested fields, ranges and multi-field ordering remain future contracts. Optional PostgreSQL delivery replicas and tenant sharding require the consistency and recovery gates in the [performance/scaling plan](../planning/PERFORMANCE-SCALING-2026-10-12.md).

The [incomplete timing-probe run](2026-10-12-ordering-probe-failed/README.md) is retained for provenance and excluded from the graph. Superseded completed runs above explain the storage adjustments.
