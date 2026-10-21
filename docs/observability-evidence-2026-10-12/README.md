# OpenTelemetry verification · 12 October 2026

The integration was verified locally with synthetic disposable SQLite content and an isolated loopback Collector. The normal CMS and its configuration were unchanged.

| Check | Observed result |
| --- | --- |
| API regression suites | 343 PostgreSQL tests passed; 341 SQLite tests passed, two optional skips (including scalar ordering) |
| Static checks | Ruff, formatting and mypy passed |
| Runtime dependencies | OpenTelemetry SDK/OTLP HTTP exporter 1.45.0, locked in `api/uv.lock` |
| Production build | Docker image `mosscms:otel-local-smoke` built with the locked Python dependencies and compiled admin |
| Collector | Pinned official contrib 0.156.0 configuration validated; actual OTLP traces and Prometheus histograms received |
| Privacy | Synthetic content, private fields, query name, credentials and bind values excluded from exported observations |
| Outage | Twenty health requests and database readiness returned HTTP 200 with the Collector stopped; lifespan cleanup completed |

- [Export receipt](collector-smoke.json) records actual metric families and observed trace/privacy/context checks.
- [Representative Prometheus output](collector-smoke.prom) retains request/GraphQL measurements and selected request SQL; full startup output was checked before filtering.
- [Collector trace output](collector-traces.log) contains synthetic spans with routes, bounded SQL labels and correlation IDs. The final smoke was repeated after migration 0012 and scalar ordering changes; trace content/private markers were checked before saving.
- [Outage receipt](collector-outage.json) records request-loop and shutdown timing. This tiny local test is an availability check, not an instrumentation-overhead benchmark.

SDK providers export asynchronously; a manual force-flush while background workers continue producing spans can wait longer than its nominal timeout. The smoke now closes the app/workers before checking Collector output; ordinary request handlers never force-flush. Queue/export failures remain best-effort.

Reproduce with [the smoke script](../../ci/telemetry_smoke.py) and [setup guide](../observability.md). CI contains the same real-export check. CI has not been run remotely in this task. Production overhead, retention and sustained capacity of the instrumented build remain unmeasured.
