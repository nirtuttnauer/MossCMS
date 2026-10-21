# 100k filtering optimization · 13 October 2026

The 100k diagnosis reproduced a common exact-filter count under a PostgreSQL generic prepared plan with 20,000 primary-key entry probes and repeated token-scope scans. String totals now use separate hashed membership checks through the existing hash and exact-prefix covering indexes. A named type is authorized by the existing workspace/token check before reading entries; untyped lists retain their token-scope subquery. Node candidates still recheck original JSON, and totals retain typed hash and exact-value guards, including long-prefix collisions. No new index, schema migration, prepared-statement configuration or dependency was added.

## Query evidence and correctness

PostgreSQL can choose generic or parameter-specific plans for prepared statements; the diagnostic exercises both explicitly, as described in the [PostgreSQL PREPARE documentation](https://www.postgresql.org/docs/17/sql-prepare.html).

[Saved query diagnostics](2026-10-13-filter-diagnostics/README.md) compare original, combined and separate membership shapes under forced generic/custom plans. The warmed covering-plan generic count drops from 52.192 ms / 89,561 buffer accesses to 12.981 ms / 1,158 accesses. These isolated SQL timings are outside mixed load. That diagnostic explicitly vacuumed its fixture to separate index visibility costs; the HTTP harness retains its original setup without forced vacuum. PostgreSQL covering execution still depends on ordinary vacuum and visibility conditions.

A new PostgreSQL regression explicitly prepares the count under `force_generic_plan` and checks common, rare and absent results, absence of per-match primary-key probes and absence of repeated type-scope scans. Existing tests cover long strings and prefix collisions, fabricated hash collisions, legacy Boolean/string type guards, multiple filters, null/coercion behavior, private/workspace/token scopes, draft/live/scheduled snapshots, ordering/cursors, repair and migration/recovery.

Final source validation passed **351 PostgreSQL tests** and **348 SQLite tests, three expected skips**, plus repository Ruff/formatting and mypy checks. [PostgreSQL log](2026-10-13-filter-diagnostics/postgres-tests.log) and [SQLite log](2026-10-13-filter-diagnostics/sqlite-tests.log) are retained. The harness also builds locked application dependencies and compiled admin. Admin source and OpenTelemetry instrumentation were unchanged in this slice; existing telemetry correctness tests run in the API suites. Collector export/privacy evidence from the preceding slice remains linked in [observability documentation](../observability.md).

## Sustained 100k result

The [completed manifest](2026-10-13-filter-sustained-100k/manifest.json) records **1800.7 seconds** of measured load, with **204,911 requests and zero errors**. The unchanged deterministic fixture has 100k entries across three workspaces; the main workspace contains 80k entries and 48k live entries, with 20k matching the common category. Queries, 20 readers / three writers, resource caps and requested 1,800-second duration match the [preceding sustained run](2026-10-13-sustained-100k/manifest.json). No smaller/shorter trial is used as the sustained comparator.

Exact-filter p95 moves from **1113 ms to 307 ms** (72.4% lower); filter p99 is 391 ms. Negative changes below mean lower latency.

| Operation | Previous p95 | New p50 | New p95 | New p99 | p95 change | Requests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| List | 388 ms | 119 ms | 220 ms | 304 ms | -43.3% | 40,070 |
| Exact filter | 1113 ms | 198 ms | 307 ms | 391 ms | -72.4% | 40,068 |
| Generated query | 351 ms | 141 ms | 240 ms | 301 ms | -31.7% | 40,067 |
| Draft save | 527 ms | 174 ms | 305 ms | 416 ms | -42.1% | 4,565 |
| Substring search | 799 ms | 237 ms | 407 ms | 501 ms | -49.1% | 40,071 |
| Conditional delivery | 388 ms | 140 ms | 245 ms | 305 ms | -36.8% | 40,070 |

Substring search is now the slowest measured operation at 407 ms p95. Repeated trials, substring-search plans and combined filter/order workloads are the next measurements before choosing additional indexes, replicas or sharding.

[Raw load data](2026-10-13-filter-sustained-100k/load-100000.json) records initial/warmed requests, HTTP statuses and per-operation throughput. Overall throughput is 113.8 requests/second, compared with 58.2 previously. Draft saves added 4,565 retained revisions while leaving captured live/scheduled snapshots unchanged.

Database size after load is **573.0 MiB**, versus 572.2 MiB previously. Scalar rows remain **480,000**, with 78.6 MiB of table storage and 155.9 MiB of indexes. This change adds no index. Database size also reflects retained revisions and vacuum/page allocation, so a byte difference between trials is not a new storage-format reduction.

[Sampled resources](2026-10-13-filter-sustained-100k/resources-100000.json) show peak app/PostgreSQL memory of 148.4/315.8 MiB, with peak CPU samples of 114.0%/206.3%. These are sampled shared-host measurements rather than continuous peaks or dedicated-hardware guarantees.

The original populated upgrade to 0013 completed in **25.7 seconds**, preserving original record/media fingerprints. Matched backup/restore fingerprints, captured scheduled publication across restarts, historical revision restoration, private/workspace/token-scope checks, media and real HTTP delivery-client checks passed. Restore through verification took **42.0 seconds**, excluding backup creation; backup size was 27,001,528 bytes. All disposable fixture containers/volumes were removed.

[Verification plans](2026-10-13-filter-sustained-100k/checks-100000.json) now retain ordered-node, filtered-node and filtered-count plans, in that order, outside timed load. Equivalent plans are retained after restore/restart. These application plans use the verification connection's planner choices; forced generic/custom comparisons are separately retained in the diagnosis. Sequential title-sort probes are also outside load and are not mixed-load percentiles.

The final source snapshot is `ef04f0cc7a5735e5bc6362a91da0fa3ff10a6eaf9bc23283b9a1a8d45d8bce04` and image ID is `sha256:9ead0960d02a88c8fa0e2e2949484f2b0f3163102ef19b71ff1769656361a8a6`. The [README graph](performance-100000-sustained-2026-10-13.png) compares three completed 30-minute 100k runs: original baseline, compact-index/request-reuse build and this filtering build. The matching 50k graph remains its existing 60-second comparison.

## Provenance and limits

The [preliminary 60-second 100k run](2026-10-13-filter-100k-short/manifest.json) completed with zero errors and successful recovery but predates the named-type scope cleanup and separate covering checks. Its source snapshot is `9f6a40f96685ce6df1fe5458e6740fbbbe62c96754b8521554c95e4a890ed4c3`. It is excluded from the sustained graph and is not a claim about the final implementation.

The benchmark uses shared macOS/ARM64 Docker hardware, with app and database each capped at two CPUs and 4 GiB. The load generator is outside these caps. The fixture contains highly compressible synthetic text, three small images and shared references/assets; it does not cover arbitrary schema or media distributions. Separate local trials can vary with host/cache/vacuum conditions. Writers intentionally sleep one second between saves, so write throughput is not maximum write capacity. Resource snapshots can miss spikes. Production traffic/hardware, multiple instances, replicas, sharding and OpenTelemetry overhead are unmeasured. The normal CMS and `.env` were unchanged; disposable test and benchmark containers/volumes were removed.
