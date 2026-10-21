# Capacity and operating cost benchmarks

CMP-01 uses disposable PostgreSQL databases and Docker volumes to measure delivery, editing, upgrades, and recovery. The harness takes a copy of the current Git-tracked and non-ignored files, builds that snapshot, and records its SHA-256 and resulting image ID. It does not deploy or connect to the normal CMS.

## Run the benchmark

Prerequisites: Python 3, Git, Docker Compose, and enough disk/memory for the generated fixtures and a second recovered database. The image build installs the locked application dependencies. The host controller uses the Python standard library; the workload runs with the application's existing httpx, SQLAlchemy, and Pillow dependencies.

From the repository root:

```sh
python3 scripts/run_benchmark.py \
  --seconds 60 --sustain-seconds 1800 \
  --output docs/benchmarks/YOUR_NEW_RUN_DIRECTORY
```

The output directory must be new. Each of the 1k, 10k, 50k, and 100k fixtures runs in turn. The smaller fixtures receive a 60-second sample; the largest selected fixture receives a 30-minute sustained measurement. Use `--seconds 1800` to sustain every size. A quick harness check is:

```sh
python3 scripts/run_benchmark.py --sizes 1000 \
  --sustain-seconds 5 --output /tmp/YOUR_NEW_SMOKE_DIRECTORY
```

The controller creates a random `moss-benchmark-*` Compose project with no published host ports. It ignores the normal `.env` and uses fixture-only credentials. It removes only that project's containers and volumes on exit, including on a failed assertion. Backups remain in its private temporary directory until the recovery checks finish and are then deleted. The built benchmark image is retained for inspection. Results contain hashes and counts, not database dumps or account credentials.

## Fixture and workload

The deterministic fixture splits entries across three workspaces at 80%/10%/10%, with two schema types per workspace. Every entry has English/Hebrew rich text, enum data, a reference to a live entry in its own workspace, an asset ID, and private fields at the top level and inside an object. Three small PNG assets exercise signed original-media delivery. Each entry has three retained historical revisions. The repeated body text is highly compressible, so measured database bytes must not be extrapolated to arbitrary content or media libraries.

The status mix repeats every five entries: draft only, scheduled only, live, live with newer draft, and live with a captured schedule. Thus 60% of all entries have a live snapshot and 40% have a schedule. Independent draft/live/scheduled titles expose accidental snapshot mixing. The two smaller workspaces exercise isolation but are not targeted by ordinary load requests; report total fixture entries separately from entries in the main workspace and its live subset.

The fixture is inserted in 1,000-row batches at migration 0008, then upgraded to the current schema. Content, history, and media hashes must match across that upgrade; new locale columns are configured to English/Hebrew and included in subsequent recovery fingerprints. This rehearsal covers that specific migration path, not every historical version.

Twenty delivery clients rotate through a 20-entry generic list, slug search, an exact enum filter, generated localized fields with asset/reference resolution, and conditional ETag requests. Three authenticated editors repeatedly save distinct entries that already have both live and scheduled snapshots, with one second of think time between saves. Each save must preserve its live and scheduled revision IDs. Delivery responses are checked for private-field markers.

Initial process requests and warmed requests are recorded separately before concurrent load. Database and OS caches are not forcibly emptied. A 304 response is a conditional-response result, not proof of a server cache or CDN hit. The current endpoint still computes the result before comparing its ETag.

The largest fixture undergoes a stopped-writer backup into a new recovery database and a new media volume, using the existing operator scripts. All table hashes, including locale values, and all media hashes must match before the recovered app starts. A schedule prepared before shutdown must publish its captured revision after startup, preserve a later draft, and emit exactly one publication event, including after a second restart. HTTP checks verify published delivery, draft exclusion, private-field exclusion, token scope, workspace isolation, and signed media. The current harness also restores a historical revision into a draft while preserving live/scheduled content and runs the typed delivery client's real HTTP smoke check; check each run's manifest to see which harness checks were included.

## Evidence and interpretation

The README's [50k performance graph](performance-50000-2026-10-12.png) reads completed manifests through [the plotting script](../../scripts/plot_benchmarks.py). Regenerate it with `uv run --no-project --with matplotlib python scripts/plot_benchmarks.py` from the repository root. Graph data comes from the recorded baseline, cache/index and final automatic-index samples; telemetry overhead is not measured there.

`manifest.json` records the source revision/snapshot, image ID, runtime information, fixture mix, workload duration, assertions, sampled resources, and recovery results. Current runs also record scalar projection table/index bytes and row counts after the timed workload. Each `load-SIZE.json` reports operation counts, throughput, nearest-rank p50/p95/p99 latency, HTTP status counts, error categories, and database size. Latency samples include failed requests; consult errors and status counts alongside percentiles. Resource files retain the raw Docker samples and peak sampled CPU/memory, which can miss spikes between samples.

The app and PostgreSQL each receive a ceiling of 2 CPUs and 4 GiB, for a combined 4-CPU/8-GiB budget; the load generator runs outside that budget. Local Docker Desktop shares the host with other workloads. These limits do not reproduce dedicated cloud hardware, network latency, production traffic, or a managed database. Three tiny fixture images do not establish performance for a large media library. Publish the observed envelope and bottlenecks rather than promise arbitrary entry counts or an uptime SLA.

## Calculate operating cost

```sh
python3 scripts/benchmark_cost.py docs/benchmarks/cost-inputs-2026-10-12.json
```

Edit a copy of the [dated inputs](cost-inputs-2026-10-12.json) to match your deployment. The monthly formula is compute + platform snapshots + object storage and transfer + compute transfer overage + other services + operator hours × hourly rate. Software seat and total-entry charges are zero.

The example uses a [DigitalOcean Basic Regular 4-vCPU/8-GiB Droplet at $48/month](https://www.digitalocean.com/pricing/droplets), [weekly snapshots at 20% of compute](https://docs.digitalocean.com/products/backups/details/pricing/), and [Spaces at $5/month with 250 GiB storage and 1 TiB outbound transfer included](https://www.digitalocean.com/pricing/spaces-object-storage). Quotes were checked on 12 October 2026. Compute transfer includes 5,000 GiB; [additional transfer is $0.01/GiB](https://docs.digitalocean.com/platform/billing/bandwidth/).

Under the stated storage/traffic assumptions, infrastructure is **$62.60/month**. Assuming two operator hours at $50/hour adds $100, for **$162.60/month**. Operator time is a budgeting assumption, not a measured maintenance result. The inputs assume 50 GiB local media and 100 GiB off-host backup storage, with 500 GiB monthly compute transfer and 100 GiB object transfer. Measure your database/revision sizes and retained backups before relying on those allowances. The same base worksheet can be evaluated for 50k or 100k entries; if measured memory, disk, traffic, or maintenance needs exceed it, change the inputs.

This is an editable budget example, not a deployed service price or evidence that the quoted VM matches the local benchmark. Frontend hosting, taxes, domains, initial setup, incidents, paid monitoring, optional managed databases, and high availability are excluded. Platform snapshots do not replace matched application backups or define a suitable recovery-point target.

## Scalar-ordering follow-up

The current verification phase checks two ordered pages, runs 20 alternating sequential HTTP requests each for legacy title sorting and indexed field ordering (both without totals), and captures actual application `EXPLAIN (ANALYZE, BUFFERS)` plans after load and after restore/restart. These probes are outside the timed mixed workload; their percentiles are not comparable to concurrent workload percentiles. The generated/list/filter/save load queries and deterministic fixture remain unchanged. See [the ordering report](RESULTS-SCALAR-ORDERING-2026-10-12.md).

[The mixed-load/storage follow-up](RESULTS-MIXED-LOAD-2026-10-13.md) records migration 0013, the matched improved 50k sample and the completed 30-minute 100k comparison, with both README graphs and raw evidence.

[The 100k filtering follow-up](RESULTS-FILTERING-2026-10-13.md) records the completed 30-minute run after covering counts and named-type scope cleanup. Verification plans now include the filtered total count after the ordered and filtered node plans, outside timed load.

[The substring-search follow-up](RESULTS-SUBSTRING-SEARCH-2026-10-14.md) records migration 0014, the completed sustained 100k result and native GIN index cost. Timed searches are unpublished-slug misses; positive and broad search probes/plans are captured separately outside load.
