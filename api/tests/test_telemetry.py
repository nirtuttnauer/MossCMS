import asyncio
import json
import logging
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode
from sqlalchemy import event, text

from app import telemetry
from app.main import create_app
from conftest import define, entry, gql


@pytest.fixture
def observed(app, monkeypatch):
    spans = InMemorySpanExporter()
    reader = InMemoryMetricReader()
    traces = TracerProvider()
    traces.add_span_processor(SimpleSpanProcessor(spans))
    meters = MeterProvider(
        metric_readers=[reader],
        views=[
            View(
                instrument_name="*.duration", aggregation=ExplicitBucketHistogramAggregation(telemetry.DURATION_BUCKETS)
            )
        ],
    )
    monkeypatch.setattr(telemetry, "providers", lambda settings: (traces, meters))
    application = create_app(replace(app.state.settings, otel_enabled=True, otel_sample_rate=1))
    with TestClient(application) as client:
        yield SimpleNamespace(app=application, client=client, spans=spans, reader=reader)
    assert not event.contains(application.state.engine, "before_cursor_execute", application.state.telemetry.before_sql)


@pytest.fixture
def client(observed):
    return observed.client


def metrics(reader):
    data = reader.get_metrics_data()
    return {
        metric.name: metric.data
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
    }


def test_http_templates_propagation_and_no_private_data(observed):
    secret = "SENSITIVE_TELEMETRY_SENTINEL"
    parent = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
    response = observed.client.get(
        f"/media/{secret}?signature={secret}",
        headers={"traceparent": parent, "Authorization": f"Bearer {secret}", "baggage": f"secret={secret}"},
    )
    assert response.status_code in {401, 403, 404, 422}
    span = next(span for span in observed.spans.get_finished_spans() if span.kind == SpanKind.SERVER)
    assert span.name == "GET /media/{id}"
    assert span.context.trace_id == int("0123456789abcdef0123456789abcdef", 16)
    assert span.parent.span_id == int("0123456789abcdef", 16)
    assert secret not in str(
        [(span.name, dict(span.attributes), span.events) for span in observed.spans.get_finished_spans()]
    )
    points = metrics(observed.reader)["http.server.request.duration"].data_points
    point = next(point for point in points if point.attributes["http.route"] == "/media/{id}")
    assert point.count == 1 and point.sum >= 0
    assert 0.3 in point.explicit_bounds
    assert secret not in str(points)


def test_graphql_and_sql_share_request_trace_without_query_values(observed, client, admin):
    define(client, admin)
    entry(client, admin, data={"title": "PRIVATE_CONTENT_SENTINEL", "body": "BODY_SENTINEL"})
    observed.spans.clear()
    result = gql(client, admin, 'query PrivateOperationName{ entries(typeKey:"article"){total}}')
    assert result["data"]["entries"]["total"] == 1
    spans = observed.spans.get_finished_spans()
    http = next(span for span in spans if span.kind == SpanKind.SERVER)
    graphql = next(span for span in spans if span.name == "moss.graphql")
    sql = [span for span in spans if span.kind == SpanKind.CLIENT and span.context.trace_id == http.context.trace_id]
    assert graphql.parent.span_id == http.context.span_id
    assert sql and all(span.context.trace_id == graphql.context.trace_id for span in sql)
    assert all(
        span.attributes["http.route"] == "/graphql" and span.attributes["moss.execution"] == "request" for span in sql
    )
    assert graphql.attributes["graphql.operation.type"] == "query"
    assert graphql.attributes["moss.graphql.endpoint"] == "editorial"
    serialized = str([(span.name, dict(span.attributes), span.events) for span in spans])
    for secret in ("PrivateOperationName", "PRIVATE_CONTENT_SENTINEL", "BODY_SENTINEL", admin["x-moss-csrf"]):
        assert secret not in serialized
    assert "db.query.text" not in serialized and "db.statement" not in serialized


def test_graphql_errors_are_counted_even_when_http_is_200(observed, client, admin):
    define(client, admin)
    result = gql(client, admin, '{notAField(value:"PRIVATE_QUERY_SENTINEL")}')
    assert result.get("errors")
    points = metrics(observed.reader)["moss.graphql.errors"].data_points
    assert any(point.value >= 1 and point.attributes["moss.error.code"] == "GRAPHQL_VALIDATION" for point in points)
    span = [span for span in observed.spans.get_finished_spans() if span.name == "moss.graphql"][-1]
    assert span.status.status_code == StatusCode.ERROR
    assert "PRIVATE_QUERY_SENTINEL" not in str((span.attributes, span.events))


def test_database_failure_has_no_statement_parameters_or_exception_details(observed):
    observed.spans.clear()
    with observed.app.state.engine.connect() as connection:
        connection.execute(text("SELECT :secret"), {"secret": "PRIVATE_BIND_SENTINEL"})
        with pytest.raises(Exception):
            connection.execute(text("SELECT * FROM private_missing_table_sentinel"))
    spans = observed.spans.get_finished_spans()
    failed = [span for span in spans if span.status.status_code == StatusCode.ERROR]
    assert failed and failed[-1].attributes["error.type"] == "database_error"
    serialized = str([(span.name, dict(span.attributes), span.events, span.status.description) for span in spans])
    assert "PRIVATE_BIND_SENTINEL" not in serialized and "private_missing_table_sentinel" not in serialized
    assert all(not span.events for span in failed)
    assert failed[-1].attributes["moss.execution"] == "background"


def test_request_logs_include_trace_correlation(observed, caplog):
    with caplog.at_level(logging.INFO, logger="mosscms"):
        response = observed.client.get("/health")
    record = next(json.loads(record.message) for record in caplog.records if '"seconds"' in record.message)
    assert record["requestId"] == response.headers["X-Request-ID"]
    assert len(record["traceId"]) == 32 and len(record["spanId"]) == 16


def test_unauthenticated_graphql_is_not_an_internal_error(observed):
    response = observed.client.post("/graphql", json={"query": "{contentTypes{id}}"})
    assert response.status_code == 401
    points = metrics(observed.reader)["moss.graphql.errors"].data_points
    assert any(point.attributes["moss.error.code"] == "UNAUTHENTICATED" for point in points)


def test_http_span_covers_stream_completion_and_resets_context(observed):
    observed.spans.clear()
    scope = {"type": "http", "method": "GET", "headers": [], "route": SimpleNamespace(path="/stream/{id}")}

    async def stream(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        assert not any(span.kind == SpanKind.SERVER for span in observed.spans.get_finished_spans())
        await send({"type": "http.response.body", "body": b"first", "more_body": True})
        await send({"type": "http.response.body", "body": b"last", "more_body": False})
        assert not any(span.kind == SpanKind.SERVER for span in observed.spans.get_finished_spans())

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        pass

    asyncio.run(telemetry.TelemetryMiddleware(stream, observed.app.state.telemetry)(scope, receive, send))
    assert any(span.name == "GET /stream/{id}" for span in observed.spans.get_finished_spans())
    assert telemetry.HTTP_SCOPE.get() is None


def test_early_rejections_and_unmatched_paths_have_bounded_labels(observed):
    observed.client.get("/PRIVATE_UNKNOWN_SENTINEL")
    response = observed.client.post("/graphql", headers={"Origin": "https://untrusted.invalid"}, json={"query": "{}"})
    assert response.status_code == 403
    points = metrics(observed.reader)["http.server.request.duration"].data_points
    assert any(
        point.attributes["http.route"] == "unmatched" and point.attributes["http.response.status_code"] == 403
        for point in points
    )
    assert "PRIVATE_UNKNOWN_SENTINEL" not in str(points)


def test_disabled_telemetry_never_creates_exporters_or_database_hooks(app, monkeypatch):
    monkeypatch.setattr(
        telemetry, "providers", lambda settings: pytest.fail("Disabled telemetry must not start exporters")
    )
    observer = telemetry.Telemetry(replace(app.state.settings, otel_enabled=False))
    observer.start(app.state.engine)
    with observer.operation("disabled"), app.state.engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    assert observer.log_fields() == {}
    assert not event.contains(app.state.engine, "before_cursor_execute", observer.before_sql)
    observer.shutdown()
    app.state.engine.dispose()


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"otel_endpoint": "ftp://collector"}, "OTEL_EXPORTER_OTLP_ENDPOINT"),
        ({"otel_endpoint": "https://secret:password@collector"}, "OTEL_EXPORTER_OTLP_ENDPOINT"),
        ({"otel_endpoint": "http://collector?token=secret"}, "OTEL_EXPORTER_OTLP_ENDPOINT"),
        ({"otel_sample_rate": float("nan")}, "MOSS_OTEL_TRACES_SAMPLE_RATE"),
        ({"otel_sample_rate": 2}, "MOSS_OTEL_TRACES_SAMPLE_RATE"),
        ({"otel_metric_interval_ms": 0}, "OTEL_METRIC_EXPORT_INTERVAL"),
        ({"otel_service_name": ""}, "OTEL_SERVICE_NAME"),
    ],
)
def test_telemetry_configuration_validation(app, changes, message):
    with pytest.raises(RuntimeError, match=message):
        replace(app.state.settings, otel_enabled=True, **changes).validate()


def test_startup_failure_still_closes_telemetry(app, monkeypatch):
    from app import main

    spans = InMemorySpanExporter()
    traces = TracerProvider()
    traces.add_span_processor(SimpleSpanProcessor(spans))
    meters = MeterProvider()
    monkeypatch.setattr(telemetry, "providers", lambda settings: (traces, meters))
    monkeypatch.setattr(main, "migrate", lambda engine: (_ for _ in ()).throw(RuntimeError("migration failed")))
    application = create_app(replace(app.state.settings, otel_enabled=True))
    with pytest.raises(RuntimeError, match="migration failed"), TestClient(application):
        pass
    assert application.state.telemetry.trace_provider is None
    assert application.state.telemetry.meter_provider is None
    assert not event.contains(application.state.engine, "before_cursor_execute", application.state.telemetry.before_sql)
