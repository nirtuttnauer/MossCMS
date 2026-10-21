# Mixed-load optimization · 13 October 2026

The owner requested resolving the ordering build's mixed-load slowdown, reducing index storage, and completing sustained 100k validation. The matching 50k sample improves every measured operation while retaining scalar ordering. The separate 30-minute 100k run also completed with zero request errors and successful matched recovery.

## Changes

- Saves update only changed top-level scalar fields within the changed draft/live snapshot; localized-only edits leave those projections untouched. Type/workspace or scalar-eligibility changes rebuild the relevant snapshots, including unchanged values becoming eligible.
- Projection rows now follow current scalar schema fields. Reference IDs, asset IDs, locale maps and unknown fields are excluded. Migration 0013 prunes old unused rows and stores hashes as 32 binary bytes instead of 64 hexadecimal characters. It preserves content/history, supports hash-format downgrade, and recreates the long-value index with its Boolean key first.
- String-filter totals use the typed hash and exact binary projection value, including full comparisons for long strings sharing prefixes. Returned rows retain the original JSON recheck; numeric, Boolean, null and coercion behavior retain the existing path. Direct SQL imports require repair before indexed reads/totals are served.
- GraphQL requests hold schema/entry/asset records only for that request. Repeated references/assets reuse lookups, while scope/publication checks still run and the next request sees new content. Distinct references/assets can still require individual lookups. This is not a cross-request content cache.

## Matched 50k sample

The same deterministic fixture, 60 seconds, 20 delivery readers/three draft writers, app/database each capped at 2 CPUs/4 GiB on shared macOS/ARM64 Docker Desktop. The main workspace has 40k entries and 24k live entries. Readers execute the original list/search/filter/generated/ETag queries; writers update the same three draft titles. Telemetry is disabled. Fixtures use compressible text, shared reference/asset IDs and three tiny PNGs; results do not establish arbitrary schema/media performance.

| Build | List p95 | Exact-filter p95 | Generated p95 | Draft-save p95 | Database |
| --- | --- | --- | --- | --- | --- |
| [Ordering before this work](2026-10-12-ordering/manifest.json) | 308 ms | 509 ms | 802 ms | 411 ms | 440.2 MiB |
| [First compact-hash/lookup sample](2026-10-13-mixed-load-initial/manifest.json) | 306 ms | 778 ms | 282 ms | 394 ms | 363.5 MiB |
| [Final scalar-only/count sample](2026-10-13-mixed-load/manifest.json) | 189 ms | 243 ms | 185 ms | 206 ms | 287.6 MiB |

All recorded error counters are empty. These separate local samples show improvement and meet the proposed <300 ms list and <750 ms draft-save targets at 50k; they do not establish statistical confidence or a production guarantee. The final sample also improves all four operations relative to the earlier automatic-filter build (250/430/644/364 ms; 332.8 MiB), while retaining scalar ordering.

Database bytes decrease about 35% from the ordering build. Projection rows decrease from 400k to 240k (40%) because unsupported field values are no longer indexed. The final projection is 39.5 MiB of table storage plus 77.2 MiB of indexes. These are physical allocations after the workload, including maintenance effects, not normalized logical bytes. Scalar edits now replace one relevant row instead of all scalar rows; shared references/assets are tested with one asset lookup and bounded entry/schema lookups per request.

[The final manifest](2026-10-13-mixed-load/manifest.json) records source snapshot, image ID, raw client percentiles, resources, plans and recovery. [Storage breakdown](2026-10-13-mixed-load/load-50000.json) is captured after the timed load. The initial sample's breakdown was read separately after load and is saved with that run.

The 50k populated upgrade took 110.7 seconds before the empty-projection backfill fix. The attempted 100k setup then exposed repeated sequential deletes on rows that cannot exist in new/cleared projections; it was stopped before timed load and is [retained as incomplete evidence](2026-10-13-sustained-100k-backfill-stopped/README.md). Fresh backfills now skip those deletes, while existing-projection repair still replaces rows. The 50k latency/storage sample precedes that migration-only fix; its request code and resulting projection format are unchanged.

Matched table/media fingerprints, scheduled snapshot publication across restarts, historical restoration, private/workspace/token-scope checks and typed delivery client checks passed. Restore through all checks took 31.3 seconds, excluding backup creation; this fixture timing is not a recovery guarantee. The upgraded application was built with locked dependencies and compiled admin. All disposable 50k fixtures were removed.

## Sustained 100k validation

The [completed 100k manifest](2026-10-13-sustained-100k/manifest.json) verifies **1800.6 seconds** of measured mixed load, requested duration 1,800 seconds, 20 readers and three writers. **104,828 requests completed with zero recorded errors**. The fixture has 100k entries across three workspaces; the main workspace has 80k entries and 48k live entries, and the common category filter matches 20k live entries.

The comparator is the original [30-minute 100k baseline](2026-10-12-baseline/manifest.json), before schema/pagination/automatic indexing improvements. Both use the same deterministic fixture, HTTP queries, concurrency and app/database caps. Short 100k samples are excluded. The 50k sample precedes the migration-only empty-projection fix; the serving request code and resulting projection format are unchanged.

| Operation | Baseline p95 | Optimized p50 | Optimized p95 | Optimized p99 | Optimized requests |
| --- | --- | --- | --- | --- | --- |
| List | 2200 ms | 193 ms | 388 ms | 509 ms | 20,119 |
| Exact filter | 5930 ms | 715 ms | 1113 ms | 1300 ms | 20,120 |
| Generated query | 3001 ms | 170 ms | 351 ms | 506 ms | 20,118 |
| Draft save | 1701 ms | 253 ms | 527 ms | 698 ms | 4,229 |
| Substring search | 2000 ms | 497 ms | 799 ms | 919 ms | 20,122 |
| Conditional delivery | 2177 ms | 186 ms | 388 ms | 520 ms | 20,120 |

[Raw load data](2026-10-13-sustained-100k/load-100000.json) also records per-operation throughput, HTTP statuses and initial/warmed requests. Overall throughput is about 58.2 requests/second for this workload. Writers deliberately sleep one second between saves; their throughput is not an unconstrained write-capacity measurement. Draft load preserved the original live/scheduled snapshots. It added 4,229 retained revisions, which affect storage.

Database size after load is **572.2 MiB**, including 480,000 scalar projection rows. Projection table bytes are 78.6 MiB and indexes 155.7 MiB. The original baseline database was 330.0 MiB and had no automatic scalar projection. The new 100k database is therefore larger than that original baseline; the measured storage reduction is the matched 50k ordering-to-optimized comparison, not a claim that indexing costs no space.

Sampled Docker memory peaks were 161.1 MiB for the app and 301.6 MiB for PostgreSQL. The database reached its two-CPU allowance; instantaneous Docker samples can briefly report above 200%. [Raw samples](2026-10-13-sustained-100k/resources-100000.json) and manifest peaks are not continuous monitoring and can miss spikes. The load generator remains outside those caps.

The populated upgrade completed in **23.1 seconds** with original content/history/media fingerprints preserved. Matched backup/restore, full table/media fingerprints, captured scheduled publication across restarts, historical restoration, private/workspace/token-scope checks and real HTTP delivery-client checks passed. Restore through final verification took **43.3 seconds**, excluding backup creation; backup bytes were 26,966,662. These fixture timings do not establish a production recovery guarantee. All disposable benchmark containers/volumes were cleaned up.

The [100k graph](performance-100000-sustained-2026-10-13.png) shows the matching sustained comparison. Filters remain the slowest operation at 1113 ms p95 and 1300 ms p99; list p95 is 388 ms. Further count/filter-plan tuning, distinct-reference batching and repeated trials are higher-priority next steps than sharding. The <300 ms list target was proposed for the short 50k sample; this larger sustained run has a different observed envelope. Production hardware, richer schemas/media, replicas and OpenTelemetry overhead remain unmeasured.

## Final verification

Final checks passed: **350 PostgreSQL API tests**, **348 SQLite API tests with two optional skips**, Ruff/formatting and mypy. [Actual Collector export](2026-10-13-telemetry-check/collector-smoke.json) and saved trace privacy checks passed after the optimized code and migrations. The production image and compiled admin were built by the isolated harness. Web source was unchanged in this slice; the existing admin test results belong to the prior UI change. Remote CI and the normal CMS deployment were not run or changed.
