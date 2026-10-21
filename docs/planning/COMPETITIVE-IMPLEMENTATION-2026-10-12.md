# Competitive roadmap implementation

Historical planning and implementation notes from 12–14 October 2026. Proposed work and intermediate states below remain dated records; use the current workflow guides and merged code for present support.

Implementation began 12 October 2026 under the owner's instruction to start with the highest priorities. These are local implementation states, not a production deployment or operational qualification. Earlier working-tree changes were retained.

| Work | Current state | Delivered | Remaining |
| --- | --- | --- | --- |
| CMP-01 | Local baseline and tooling verified | Deterministic 1k/10k/50k/100k fixtures; 30-minute baseline at 100k; sampled CPU/memory, latencies/errors and database size; migration/backup/restore/restart evidence; editable dated cost calculator | Sustained validation of the optimized build, larger media/schema fixtures, cloud validation and matched competitor trials |
| CMP-02 | Contract drafted | Versioned streaming bundle contract for schemas, snapshots, assets, references, selected history and private-field handling | Export/import implementation, resumable staging, Sanity adapter and round-trip acceptance |
| CMP-03 | Typed client implemented and verified | Dependency-free server delivery client, TypeScript declarations, cursor streaming, error codes/request IDs, example-site adoption and real HTTP check | REST delivery, supported Next.js starter, schema-derived type generation and developer trials |
| CMP-12 | Improvements and automatic scalar indexing verified locally | Bounded compiled-schema reuse, publication/due-schedule indexes, transactional draft/live scalar projections, populated backfill and 50k evidence; compatibility regressions retained | Search/reference improvements and sustained scaling evidence |
| CMP-04–CMP-11 except the slices above | Planned | Existing editor, preview, media and publication foundations retained | Visual authoring, permissions, approvals, releases, collaboration, extension and translation scopes |

## Evidence

[Capacity and recovery results](../benchmarks/RESULTS-2026-10-12.md) records the baseline and follow-up source/image identities, conditions and limitations. Matched 60-second samples at 50k changed list p95 from 712 ms to 355 ms and filtered-read p95 from 2,186 ms to 786 ms. The proposed list target below 300 ms is still missed. The 100k baseline ran for 30 minutes; the optimized 100k follow-up was a 60-second sample. Neither run had request failures.

Both 100k recoveries matched all recorded table/media hashes, retained later drafts, and published the captured schedule once after startup and again verified no duplicate effect after another restart. The follow-up also restored a historical revision as a draft without changing live content/schedule, checked unchanged live/scheduled JSON across draft writes, and verified the delivery client over real HTTP.

Final validation: 290 PostgreSQL API tests pass; 288 SQLite tests pass with 2 optional checks skipped. Ruff, formatting and mypy pass. All 46 example-site server tests, its TypeScript check/build, and the client declaration compile pass. The new-index migration is additive and preserves existing JSON text storage. A broader JSONB filter-index proposal failed that compatibility check and was removed.

The final benchmark-helper run passes 11 tests, including two additional cleanup guards. Cleanup verifies Docker project ownership before removing fixture volumes, including original media left unused after recovery. The temporary volumes from all four local runs were removed.

## Implementation entry points

- [Benchmark controller](../../scripts/run_benchmark.py), [fixture/workload](../../scripts/benchmark.py), [isolated Compose definition](../../compose.benchmark.yaml), and [benchmark guide](../benchmarks/README.md).
- [Cost calculator](../../scripts/benchmark_cost.py) and [dated quote/assumption inputs](../benchmarks/cost-inputs-2026-10-12.json).
- [GraphQL compilation cache](../../api/app/graphql.py), [lookup-index migration](../../api/migrations/versions/0010_delivery_page_index.py), and [cache/storage compatibility tests](../../api/tests/test_schema_cache.py).
- [Portable-content contract](../portable-content-format.md).
- [Delivery client](../../shared/delivery.mjs), [TypeScript declarations](../../shared/delivery.d.mts), [integration guide](../delivery-client.md), and [example-site caller](../../example-site/server/moss.mjs).

## Next implementation slice

Implement the empty-workspace export/import round trip from CMP-02 and add REST delivery alongside the existing shared permission/public-snapshot rules in CMP-03. Continue capacity work with a sustained optimized run and filter/search improvements that preserve all accepted JSON values. Any future JSONB storage/indexing change needs an explicit compatibility and migration contract. Keep user data and the normal CMS deployment separate from benchmark fixtures.

## Automatic indexing follow-up

Under the owner's follow-up request, migration 0011 adds [automatic scalar indexing](../automatic-indexing.md). Exact top-level scalar filters use a shared hash projection index, maintained in the content transaction, with separate draft/live rows and original-value rechecks. The migration backfills existing entries without converting their JSON, and `reindex --project` repairs direct imports. Null/coercion comparisons retain the original path; substring/range/nested/localized indexing remains outside this slice. Full API checks passed on PostgreSQL (303) and SQLite (301, two optional skips), with explicit backend selection.

The [50k follow-up report](../benchmarks/RESULTS-AUTOMATIC-INDEXING-2026-10-12.md) records filter p95 of 430 ms and list p95 of 250 ms in the final 60-second sample, with no request failures and successful matched recovery/restarts. Database size increased from 171 MiB to 333 MiB. A simpler joined lookup regressed common filters and was replaced by candidate-first conditional evaluation before the final run. This does not establish sustained 100k performance of migration 0011.

## OpenTelemetry follow-up

The owner's instrumentation request adds opt-in OTLP HTTP tracing and all-operation histograms for HTTP, GraphQL, SQL and worker work, plus bounded GraphQL error counters and request-log trace IDs. SQL timings are grouped by route/table/operation and separated from background work. The [setup/query guide](../observability.md) and optional Collector overlay support collecting evidence for CMP-01/CMP-12 optimization work. Query documents/variables, SQL/binds, content and exception text are omitted from exported telemetry.

Local verification includes actual Collector traces/Prometheus output, privacy checks, offline-Collector health/readiness and shutdown, 320 PostgreSQL API tests, 318 SQLite API tests (two optional skips), lint/type checks and a production image build. See [the verification record](../observability-evidence-2026-10-12/README.md). CI now runs the real export smoke. Production instrumentation overhead, long-term retention and a dashboard/backend deployment remain unverified.

## Scalar ordering and performance follow-up

The owner selected any scalar schema field with automatic indexing. Migration 0012 backfills binary sort keys, bounded prefixes and calendar-date values, with shared indexes covering every top-level non-localized scalar field. Both draft/editorial and published/delivery paths use stable value/ID cursors with nulls last. The existing editor offers ascending/descending field sorts after choosing a content type. Private delivery fields remain forbidden, and accepted long/null-containing strings retain exact ordering through a fallback. GraphQL totals are now counted only when selected; generated lists avoid unused counts and default delivery lists avoid unnecessary title-metadata work.

The [scaling plan](PERFORMANCE-SCALING-2026-10-12.md) prioritizes measured query/batching/index cost improvements and sustained verification before optional PostgreSQL delivery replicas or tenant sharding. These infrastructure proposals are not deployed. The [ordering evidence](../benchmarks/RESULTS-SCALAR-ORDERING-2026-10-12.md) and README graph record dated source/workload limits and recovery checks.

Final regression verification: 343 PostgreSQL API tests, 341 SQLite API tests with two optional skips, all 294 web tests and the admin TypeScript/production build pass. Ruff/formatting and mypy pass. Actual Collector export/privacy checks were repeated after the ordering changes.

## Mixed-load/storage optimization · 13 October 2026

The owner requested fixing the ordering build's regression, reducing index storage and running sustained 100k validation. Migration 0013 prunes unsupported projection rows and stores binary hashes; field-level maintenance avoids unchanged scalar writes. Exact string totals avoid reparsing every matching document. Request-local schema/reference/asset records remove repeated lookups while keeping scope/publication checks and fresh state on the next request. Schema rename/reclassification tests cover projection updates during revision flushes.

The matched 50k sample now reports list/filter/generated/save p95 of 189/243/185/206 ms with no errors, compared with 308/509/802/411 ms before this work. Database bytes fall from 440.2 to 287.6 MiB and projection rows from 400k to 240k. Matched recovery, captured publication/restarts, historical restoration, scope/privacy and real delivery-client checks pass. [The optimization report](../benchmarks/RESULTS-MIXED-LOAD-2026-10-13.md) retains the slower initial sample and the stopped pre-load setup for provenance.

The 100k setup exposed scans from unnecessary deletes on new/cleared projections. Those backfills now skip deletes; repairs retain them. The fresh 100k upgrade then completed in 23.1 seconds with original fingerprints preserved. Its verified 30-minute workload completed 104,828 requests with zero errors: list/filter/generated/save p95 388/1113/351/527 ms. Matched recovery, publication/restart, history, media, privacy/scope and delivery-client checks passed. Database size was 572.2 MiB; the report and separate sustained graph retain the full results and remaining filter bottleneck.

Final optimization verification passes 350 PostgreSQL API tests, 348 SQLite API tests with two optional skips, lint/formatting/mypy and actual Collector export/privacy checks. The normal CMS and `.env` were unchanged; only disposable benchmark/test fixtures were started and removed.

### 13 October · 100k filtering follow-up

String totals now use separate hash/exact-value memberships through existing covering indexes, preventing per-match primary-key probes in generic prepared plans. Named types retain the existing workspace/token authorization check and omit the redundant scope subquery; untyped lists remain scoped. No new index or migration was added. The [completed 30-minute 100k run](../benchmarks/RESULTS-FILTERING-2026-10-13.md) records 204,911 requests with zero errors, filter p95 307 ms (72.4% below 1113 ms), matching recovery and isolation checks. Final validation passed 351 PostgreSQL tests, 348 SQLite tests with three expected skips, lint/formatting and mypy. The README sustained graph now compares all three matching 30-minute stages.

### 14 October · Substring search

PostgreSQL migration 0014 adds separate native draft/published title-and-slug trigram indexes, preserving publication and current private-title/workspace/token scope semantics. The [matched 30-minute 100k run](../benchmarks/RESULTS-SUBSTRING-SEARCH-2026-10-14.md) completed 260,209 requests with zero errors; search-miss p95 is 197 ms (51.5% lower than 407 ms). Timed searches target unpublished slugs; positive/broad search plans remain separate probes. Search-index storage and matched recovery are recorded. SQLite retains its existing path, and broader search trials remain. Full API suites passed 363 PostgreSQL and 359 SQLite tests with four expected skips; separate in-progress portability static-check issues are disclosed in the report. The sustained graph now includes search misses across all four matching stages.
