# Automatic indexing: 50k follow-up

Local measurements collected on 12 October 2026 for migration 0011. Automatic scalar indexing reduces the final sample's exact-filter latency, with a substantial storage cost. The first joined implementation regressed and was replaced before completion.

## Conditions

The same deterministic 50,000-entry fixture, 20 delivery readers and three draft writers described in the [benchmark guide](README.md) ran for 60 seconds per image. Each app/database container was capped at 2 CPUs and 4 GiB on shared macOS/ARM64 Docker Desktop. The main workspace has 40,000 entries and 24,000 live entries; the enum query matches 10,000 live entries. Assets are three tiny PNGs and text is highly compressible. These are separate local samples, not statistically established speedups, dedicated cloud results or competitor trials.

## Results

Nearest-rank p95 latency, including failed-request samples. All recorded error counters were empty.

| Build | List p95 | Filter p95 | Generated p95 | Draft-save p95 | Database size |
| --- | --- | --- | --- | --- | --- |
| [Before automatic indexing](2026-10-12-optimized/manifest.json) | 355 ms | 786 ms | 827 ms | 401 ms | 170.7 MiB |
| [Joined prototype (replaced)](2026-10-12-auto-index/manifest.json) | 502 ms | 1811 ms | 1075 ms | 591 ms | 332.7 MiB |
| [Final conditional lookup](2026-10-12-auto-index-conditional/manifest.json) | 250 ms | 430 ms | 644 ms | 364 ms | 332.8 MiB |

The final sample changed filtered-read p95 from 786 ms to 430 ms and list p95 from 355 ms to 250 ms. It meets the proposed 50k list target below 300 ms and draft-save target below 750 ms in this run. Database bytes increased from 179,041,971 to 348,993,203 (about 95%); the projection adds one bounded hash row per top-level scalar value per draft/live snapshot, plus its primary/lookup indexes. Measure this cost for your schemas, revision history and data before sizing storage.

## Query adjustment

The joined prototype used an `IN` candidate lookup alongside the original JSON comparison. PostgreSQL underestimated the common enum match count and chose repeated primary-key probes after scanning/parsing content. The final query uses `CASE` to check candidate membership before evaluating the original JSON predicate, allowing a hashed lookup subplan and avoiding those per-row probes. The original comparison still checks collisions and scalar equality.

The [diagnostic query plans](2026-10-12-auto-index/query-plans.txt) were collected sequentially on a separate fresh fixture with the same source image as the joined prototype; their cache state and execution timings differ. They explain the plan choice and are not a controlled latency comparison. The HTTP workload above provides the performance observations. PostgreSQL remains free to choose its cost-based plans; rare values, larger sets, different memory settings and multiple filters need further measurements.

## Upgrade, recovery and correctness

The final fixture upgraded from 0008 through 0011 in 8.1 seconds, preserving original content/history/media fingerprints. This includes the new projection backfill. Migration holds row locks and runs in one transaction; stop older writers and allow a maintenance window for larger datasets.

Matched backup/restore, full table/media fingerprints, delivery isolation and restart checks passed. Restore through final verification took 30.3 seconds, excluding backup creation; backup age at verification was 33.7 seconds. These fixture timings do not define a production recovery guarantee.

The captured schedule published once across two starts while retaining the later draft. Historical restoration created a draft and preserved live/scheduled content. The workload preserved exact live/scheduled JSON through draft writes. The typed delivery client checked two pages, private-field exclusion, token scope and structured errors over real HTTP. Temporary fixtures were removed after each run.

API verification: 303 PostgreSQL tests passed; 301 SQLite tests passed with two optional checks skipped. Ruff, formatting and mypy passed. Follow-up query regression checks passed on both engines. No normal CMS deployment or user content was changed.

## Remaining limits

This is a 60-second 50k sample. The earlier 30-minute 100k baseline predates these indexes; the final automatic-index build still needs sustained 100k validation. Null/missing and cross-type coercion filters keep their original path. Substring search, nested/localized/range filters, arbitrary field sorts and adaptive traffic-driven index selection remain outside this slice. Direct SQL/bulk writes need the documented projection repair before serving indexed queries.

See the [automatic indexing contract and repair command](../automatic-indexing.md).
