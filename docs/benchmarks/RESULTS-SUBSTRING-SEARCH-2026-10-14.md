# Substring-search optimization · 14 October 2026

PostgreSQL title/slug substring search now uses two native multicolumn trigram GIN indexes: one for draft metadata and a partial one for published metadata. Migration 0014 installs `pg_trgm` if missing. The title predicate exposes the indexed column while retaining current private-title restrictions for named and untyped delivery lists. Case-insensitive matching, escaped wildcard/backslash literals, bounded terms, database rechecks, publication separation and workspace/token scopes retain their behavior. No body full-text search, ranking, application cache or new Python dependency is introduced. SQLite retains its existing substring query.

## Diagnosis and correctness

[Saved 100k diagnostics](2026-10-14-search-diagnostics/README.md) compare the original query, a covering B-tree and a published trigram index. Selective misses improve in the isolated probes, while the broad `Live` count does not. These SQL timings are outside mixed HTTP load. PostgreSQL's [pg_trgm documentation](https://www.postgresql.org/docs/17/pgtrgm.html) describes substring support and fallback scans when a pattern provides no useful trigrams. Short, broad or punctuation-only terms can remain expensive.

The existing timed search workload searches `article-{turn % 100:06d}` only when `turn % 5 == 1`. Those fixture IDs are unpublished, so timed search measures **published-slug misses**. Its query/mix is unchanged for the matched comparison. Positive live-slug and broad live-title checks/plans are added outside timed load; the resulting miss latency is not a benchmark of arbitrary successful or broad searches.

API verification passed **363 PostgreSQL tests** and **359 SQLite tests with four expected skips**. New checks cover Unicode and short substrings, literal `%`, `_` and backslashes, live/draft title and slug changes, immediate title-privacy changes, scoped/untyped lists, populated upgrade/downgrade preservation and generic prepared-plan trigram usability/rechecks. The generic test rebuilds its index after bulk inserts to match populated migration creation, rather than an unflushed pending list. It does not change the application's planner settings. [PostgreSQL log](2026-10-14-search-diagnostics/postgres-tests.log) and [SQLite log](2026-10-14-search-diagnostics/sqlite-tests.log) are retained. Changed files pass Ruff/formatting and the changed API modules pass mypy.

Separate portability edits appeared in the shared workspace during validation. Initial full-project formatting/mypy reported issues in that unrelated module; it was preserved. The frozen source snapshot includes that module/CLI branch, which the HTTP workload does not exercise. After load, the current workspace passes full Ruff, formatting (92 files) and mypy (27 modules); [final check output](2026-10-14-search-diagnostics/final-static-checks.log) is retained. That later check does not retroactively validate the frozen portability implementation. The built image serves successfully and completes the benchmark/recovery checks. Admin source and OpenTelemetry instrumentation were unchanged by this search slice.

## Sustained 100k result

The [completed manifest](2026-10-14-search-sustained-100k/manifest.json) records **1801.1 seconds**, **260,209 requests and zero errors**. Its deterministic 100k-entry fixture, three-workspace 80/10/10 mix, HTTP queries, 20 readers/three writers and app/database resource caps match the [preceding sustained filter build](2026-10-13-filter-sustained-100k/manifest.json). The main workspace has 80k entries and 48k live entries. Search-miss p95 moves from **407 ms to 197 ms**, **51.5% lower**; search-miss p99 is 270 ms. Negative changes below mean lower latency.

| Operation | Previous p95 | New p50 | New p95 | New p99 | p95 change | Requests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| List | 220 ms | 131 ms | 225 ms | 300 ms | +2.3% | 51,124 |
| Exact filter | 307 ms | 150 ms | 248 ms | 330 ms | -19.2% | 51,128 |
| Generated query | 240 ms | 139 ms | 236 ms | 315 ms | -1.6% | 51,126 |
| Draft save | 305 ms | 166 ms | 291 ms | 417 ms | -4.6% | 4,577 |
| Substring search miss | 407 ms | 112 ms | 197 ms | 270 ms | -51.5% | 51,128 |
| Conditional delivery | 245 ms | 131 ms | 224 ms | 299 ms | -8.7% | 51,126 |

List p95 increased 2.3%, from 220 to 225 ms, while overall throughput rose. These separate shared-host samples do not establish whether that small increase is host variation or an indexing tradeoff; repeated trials remain necessary.

[Raw load data](2026-10-14-search-sustained-100k/load-100000.json) also includes initial/warmed requests, HTTP statuses and throughput. Overall throughput is 144.5 requests/second versus 113.8 previously. Draft writes added 4,577 retained revisions and preserved captured live/scheduled snapshots. Writers deliberately sleep one second between saves; their measured throughput is not maximum write capacity.

Database size after load is **590.9 MiB**, versus 573.0 MiB previously. The new native search indexes occupy **10.6 MiB draft / 7.6 MiB published**. These sizes include their post-load GIN allocation/pending-list state. Existing scalar projection rows remain 480,000, with 78.6 MiB table / 155.9 MiB indexes. Storage differences also reflect retained revisions and page/vacuum allocation, not only new search indexes.

[Sampled resources](2026-10-14-search-sustained-100k/resources-100000.json) record peak app/PostgreSQL memory of 174.8/278.6 MiB, and peak CPU samples of 129.9%/184.7%. Samples can miss spikes and shared-host effects. GIN adds write/vacuum work; this run retains the ordinary planner and maintenance settings rather than forcing a scan method or vacuum during load.

The populated upgrade from 0008 to 0014 completed in **38.8 seconds**, preserving original record/history/media fingerprints. Matched backup/restore fingerprints, captured scheduled publication across restarts, historical restoration, media, private/workspace/token-scope checks and real HTTP delivery-client checks passed. Restore through verification took **48.4 seconds**, excluding backup creation, with 27,004,523 backup bytes. All task-owned benchmark, diagnostic and test containers/volumes were removed.

[Verification plans](2026-10-14-search-sustained-100k/checks-100000.json) contain nine plans: ordered nodes, exact-filter nodes, exact-filter count, then count/page pairs for an unpublished miss (`article-000001`), positive live slug (`article-000002`) and broad live title (`Live`). Equivalent probes run after restore/restart. These and the sequential title-sort probes are outside timed mixed load and are not concurrent latency measurements.

The source snapshot is `e201ab87a18b7537cf2dfc246be71e84bd9bdab206b01bc97023f7b38e781e58`, image ID `sha256:bf1101699926e1ae9311643ef09e1c648d5c331aae889416c28e5434f1d3c4e9`. The [updated graph](performance-100000-sustained-2026-10-14.png) compares four completed 30-minute 100k stages and includes the search-miss operation. The historical 50k chart retains its existing sources; no new 50k trial is claimed.

## Deployment and measurement limits

Migration 0014 requires permission to install the trusted `pg_trgm` extension, or an operator can preinstall it. Populated transactional index creation can block writes; budget a maintenance window. Downgrade removes both search indexes while retaining the potentially shared extension. Richer and more varied titles/slugs can change GIN storage and write costs. SQLite is not accelerated by these indexes.

These are separate samples on shared macOS/ARM64 Docker hardware, with app and database each capped at two CPUs/4 GiB and the load generator outside those caps. The synthetic fixture has compressible text, shared references/assets and three small images. Broad/short successful searches, richer media, repeated trials, production traffic/hardware, multi-instance deployments, replicas, sharding and OpenTelemetry overhead remain unmeasured. The normal CMS and `.env` were unchanged.
