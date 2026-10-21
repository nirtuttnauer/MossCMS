# OpenTelemetry performance measurements

MossCMS can export traces and latency histograms over **OTLP HTTP/protobuf**. Telemetry is disabled by default. Enable it to compare request latency, GraphQL schema/execution time, SQL calls and scheduled-publication/webhook work. The existing administrator-only `/metrics` endpoint remains unchanged; richer OTel metrics go to your Collector/backend.

## Connect a backend

Set these variables in `.env`, then restart the app on an image containing this integration:

```dotenv
MOSS_OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=https://YOUR_COLLECTOR_BASE_URL
OTEL_SERVICE_NAME=mosscms
MOSS_OTEL_TRACES_SAMPLE_RATE=0.1
OTEL_METRIC_EXPORT_INTERVAL=10000
# Optional backend authentication; keep this value private.
OTEL_EXPORTER_OTLP_HEADERS=
```

The base URL receives `/v1/traces` and `/v1/metrics`, preserving an existing base-path prefix. Transport is HTTP/protobuf, not gRPC. The SDK exporters read `OTEL_EXPORTER_OTLP_HEADERS`. Sample rates are 0–1; metric export intervals are 1–3,600 seconds, configured in milliseconds. Resources include service name, API version, environment and a fresh service-instance ID so replicas remain distinct.

The rate applies to new root traces. Valid W3C `traceparent` headers connect upstream traces and preserve parent sampling decisions. HTTP request logs include `traceId`/`spanId` alongside `requestId` when telemetry is enabled. Unsampled requests still have correlation IDs and metric measurements, but no exported trace.

## Try the local Collector

```sh
docker compose -f compose.yaml -f compose.observability.yaml up --build -d app otel-collector
docker compose -f compose.yaml -f compose.observability.yaml logs --tail 100 otel-collector
curl http://127.0.0.1:9464/metrics
```

The optional overlay enables telemetry and sends it to `http://otel-collector:4318` on the Compose network. The pinned Collector exports metrics on loopback port **9464** and writes detailed sampled traces to its logs. Set `MOSS_OTEL_METRICS_PORT` if occupied. Logs rotate at 10 MiB with two files; Collector memory is capped at 256 MiB.

This is an inspection/scrape configuration without durable trace retention or a dashboard service. For ongoing use, replace its debug trace exporter with your Jaeger, Tempo or other backend exporter and add it to the trace pipeline. Start from [the Collector configuration](../ops/otel-collector.yaml), [official Collector guide](https://opentelemetry.io/docs/collector/configuration/) and [Python exporter guide](https://opentelemetry.io/docs/languages/python/exporters/).

For Prometheus sharing the Compose network:

```yaml
scrape_configs:
  - job_name: mosscms
    scrape_interval: 15s
    static_configs:
      - targets: [otel-collector:9464]
```

Host-installed Prometheus can scrape `127.0.0.1:9464`. A container's loopback points to that container; use the service name on a shared network.

## What is measured

| Signal | Instrument / span | Dimensions and meaning |
| --- | --- | --- |
| HTTP | `http.server.request.duration` / server span | Method, matched route template, status; ends after response streaming; early rejection/unknown routes use `unmatched` |
| GraphQL | `moss.graphql.operation.duration` / `moss.graphql` | Editorial/delivery endpoint, operation kind and failure state; includes authentication, execution and commit/rollback |
| GraphQL errors | `moss.graphql.errors` | Bounded code and endpoint/kind; counts errors even with HTTP 200, plus handler auth/internal failures |
| Schema/execution | `moss.operation.duration` / `moss.graphql.schema`, `moss.graphql.execute` | Separates schema construction/cache lookup from execution |
| SQL | `db.client.operation.duration` / `DB OPERATION TABLE` | System, bounded verb, known table, request/background context and request route template |
| Workers/startup | `moss.operation.duration` / `moss.worker.publish`, `moss.worker.webhooks`, `moss.startup.migrate` | Polling iterations and lifespan migration check; polls may find no work |

Histograms use seconds with boundaries from 1 ms to 30 seconds, including the 300 ms/750 ms roadmap thresholds. Counts/sums/buckets include every instrumented operation regardless of trace sampling. SQL timing measures cursor execution and failures; it excludes pool waiting, fetching/materialization and transaction commit/rollback. Executemany counts once per call, not per row. Surrounding HTTP/GraphQL timings capture more application work. Initial CLI migrations before the ASGI lifespan are outside these spans.

## Calculate bottlenecks

These PromQL names were verified against the included Collector's [real export smoke](observability-evidence-2026-10-12/collector-smoke.json). Adjust `service_name` if changed.

HTTP p95 seconds by route:

```promql
histogram_quantile(0.95,
  sum by (le, http_route) (
    rate(http_server_request_duration_seconds_bucket{service_name="mosscms"}[5m])
  )
)
```

GraphQL p95 by delivery/editorial:

```promql
histogram_quantile(0.95,
  sum by (le, moss_graphql_endpoint) (
    rate(moss_graphql_operation_duration_seconds_bucket{service_name="mosscms"}[5m])
  )
)
```

HTTP 5xx fraction:

```promql
sum(rate(http_server_request_duration_seconds_count{service_name="mosscms",http_response_status_code=~"5.."}[5m]))
/
sum(rate(http_server_request_duration_seconds_count{service_name="mosscms"}[5m]))
```

GraphQL errors/second, including HTTP-200 errors:

```promql
sum by (moss_graphql_endpoint, moss_error_code) (
  rate(moss_graphql_errors_total{service_name="mosscms"}[5m])
)
```

SQL calls per HTTP request, excluding workers/startup:

```promql
sum by (http_route) (
  rate(db_client_operation_duration_seconds_count{service_name="mosscms",moss_execution="request"}[5m])
)
/
sum by (http_route) (
  rate(http_server_request_duration_seconds_count{service_name="mosscms"}[5m])
)
```

Zero traffic gives absent/undefined ratios, not evidence of an outage. Histogram quantiles estimate within buckets and need enough observations. These server measurements differ from benchmark client percentiles.

Find a regression by route p95/errors, then inspect sampled GraphQL phases and SQL children. Repeated SQL children suggest extra lookups; slow cursor spans suggest database work; gaps between SQL and GraphQL/HTTP totals suggest schema/resolver/serialization/fetch cost. Automatic-index writes appear as `INSERT`/`DELETE` on `entry_field_indexes`. Worker timings reveal polling/publication/webhook work independently of requests.

For scalar ordering, compare `orderBy` and legacy sorts with matching fields and page sizes. Omit `total` unless needed, then check SQL-call counts and route latency; counts and generated reference expansion can dominate bounded lists. See the [performance/scaling priorities](planning/PERFORMANCE-SCALING-2026-10-12.md).

Compare matching fixtures, schemas, concurrency, sampling, export intervals and Collector setups. Retain [raw benchmark percentiles](benchmarks/README.md) and repeat sustained runs before capacity claims. Telemetry does not automatically change queries or indexes.

## Privacy and lifecycle

Telemetry omits URLs/query strings, headers/cookies, GraphQL documents/variables/operation names, SQL statements/binds, user/workspace/entry IDs, content, and exception messages/stacks. It exports route templates, method/status, bounded codes/operation labels and known tables. Request UUIDs and trace/span IDs support trace/log correlation and never become metric labels. Baggage/tracestate are not propagated. Existing application logs are separate; no OTel log exporter was added.

Providers belong to each app instance; SQL hooks attach only to its engine. Telemetry starts in the ASGI lifespan and shuts down after workers stop; startup failures also clean up. Disabled telemetry creates no SDK providers, exporters, SQL hooks or export threads. Exports use background SDK workers, a bounded trace queue and a three-second export timeout. Collector outages do not block normal requests; failed/dropped exports are best-effort, not exact traffic totals. Shutdown may wait for queued exports. Do not call manual SDK force-flush from request handlers; SDK timeout behavior is not an application deadline.

CPU/memory/network overhead and production retention costs remain unbenchmarked. Browser/example-site, S3 and outbound webhook client instrumentation, host/process metrics, SQL plans/text, per-field resolver traces and a hosted backend/dashboard are outside this slice.

## Verification

SQLite/PostgreSQL tests cover propagation, route/SQL context, streaming, errors, privacy, disabled operation and cleanup. CI runs synthetic content through actual OTLP and Prometheus exports with the pinned Collector. To repeat from `api/`, start a separate test Collector with OTLP HTTP published only on loopback:

```sh
MOSS_USE_SQLITE=false PYTHONPATH=. uv run python ../ci/telemetry_smoke.py \
  --endpoint http://127.0.0.1:4318 \
  --metrics-url http://127.0.0.1:9464/metrics \
  --output /tmp/moss-otel-evidence/collector-smoke.json
```

The default overlay does not publish OTLP to the host. The smoke creates disposable SQLite data and refuses non-loopback destinations. See [local verification evidence](observability-evidence-2026-10-12/README.md). No normal instance was deployed/reconfigured.
