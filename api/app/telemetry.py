"""Opt-in OTel with bounded dimensions and no request/SQL content capture."""

import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from uuid import uuid4

from fastapi import HTTPException
from graphql import get_operation_ast
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from sqlalchemy import event

DURATION_BUCKETS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.3, 0.5, 0.75, 1, 2.5, 5, 7.5, 10, 30)
METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
SQL_OPERATIONS = {"SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "PRAGMA", "BEGIN", "COMMIT"}
ERROR_CODES = {
    "VALIDATION",
    "GRAPHQL_VALIDATION",
    "QUERY_LIMIT",
    "FORBIDDEN",
    "NOT_FOUND",
    "CONFLICT",
    "INTERNAL",
    "UNAUTHENTICATED",
}
HTTP_SCOPE = ContextVar("moss_otel_http_scope", default=None)


def providers(settings):
    resource = Resource(
        {
            "service.name": settings.otel_service_name,
            "service.version": "0.2.0",
            "service.instance.id": str(uuid4()),
            "deployment.environment.name": settings.environment,
        }
    )
    traces = TracerProvider(resource=resource, sampler=ParentBased(TraceIdRatioBased(settings.otel_sample_rate)))
    traces.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=settings.otel_endpoint.rstrip("/") + "/v1/traces", timeout=3),
            max_queue_size=2048,
            max_export_batch_size=256,
        )
    )
    try:
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=settings.otel_endpoint.rstrip("/") + "/v1/metrics", timeout=3),
            export_interval_millis=settings.otel_metric_interval_ms,
            export_timeout_millis=5000,
        )
        meters = MeterProvider(
            resource=resource,
            metric_readers=[reader],
            views=[
                View(instrument_name="*.duration", aggregation=ExplicitBucketHistogramAggregation(DURATION_BUCKETS))
            ],
        )
    except Exception:
        traces.shutdown()
        raise
    return traces, meters


class Telemetry:
    def __init__(self, settings):
        self.settings = settings
        self.enabled = settings.otel_enabled
        self.tracer = trace.NoOpTracerProvider().get_tracer("mosscms")
        self.trace_provider = self.meter_provider = self.engine = None

    def start(self, engine):
        if not self.enabled:
            return
        self.trace_provider, self.meter_provider = providers(self.settings)
        self.tracer = self.trace_provider.get_tracer("mosscms", "0.2.0")
        meter = self.meter_provider.get_meter("mosscms", "0.2.0")
        self.http_duration = meter.create_histogram("http.server.request.duration", unit="s")
        self.db_duration = meter.create_histogram("db.client.operation.duration", unit="s")
        self.operation_duration = meter.create_histogram("moss.operation.duration", unit="s")
        self.graphql_duration = meter.create_histogram("moss.graphql.operation.duration", unit="s")
        self.graphql_errors = meter.create_counter("moss.graphql.errors", unit="1")
        from .models import Base

        self.tables = frozenset(Base.metadata.tables)
        self.db_system = {"postgresql": "postgresql", "sqlite": "sqlite"}.get(engine.dialect.name, "other_sql")
        self.engine = engine
        event.listen(engine, "before_cursor_execute", self.before_sql)
        event.listen(engine, "after_cursor_execute", self.after_sql)
        event.listen(engine, "handle_error", self.sql_error)

    def shutdown(self):
        if self.engine is not None:
            event.remove(self.engine, "before_cursor_execute", self.before_sql)
            event.remove(self.engine, "after_cursor_execute", self.after_sql)
            event.remove(self.engine, "handle_error", self.sql_error)
            self.engine = None
        try:
            if self.meter_provider is not None:
                self.meter_provider.shutdown(timeout_millis=5000)
        finally:
            self.meter_provider = None
            if self.trace_provider is not None:
                self.trace_provider.shutdown()
                self.trace_provider = None
            self.tracer = trace.NoOpTracerProvider().get_tracer("mosscms")

    @contextmanager
    def operation(self, name):
        if not self.enabled:
            yield
            return
        attributes = {"moss.operation": name}
        started = time.perf_counter()
        with self.tracer.start_as_current_span(name, record_exception=False, set_status_on_exception=False) as span:
            try:
                yield
            except BaseException:
                attributes["error.type"] = "operation_failed"
                span.set_attribute("error.type", "operation_failed")
                span.set_status(Status(StatusCode.ERROR))
                raise
            finally:
                self.operation_duration.record(time.perf_counter() - started, attributes)

    def graphql_kind(self, request, document, operation_name):
        if self.enabled:
            operation = get_operation_ast(document, operation_name)
            request.state.otel_graphql_kind = operation.operation.value if operation else "unknown"

    def graphql_result(self, request, payload):
        if self.enabled:
            request.state.otel_graphql_errors = [
                code if code in ERROR_CODES else "OTHER"
                for error in payload.get("errors") or []
                for code in [error.get("extensions", {}).get("code", "INTERNAL")]
            ]

    def graphql(self, function):
        if not self.enabled:
            return function

        @wraps(function)
        def measured(body, request):
            attributes = {
                "moss.graphql.endpoint": "delivery" if request.url.path.startswith("/delivery/") else "editorial"
            }
            started = time.perf_counter()
            with self.tracer.start_as_current_span(
                "moss.graphql", record_exception=False, set_status_on_exception=False
            ) as span:
                try:
                    return function(body, request)
                except HTTPException as exc:
                    request.state.otel_graphql_errors = [
                        {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND"}.get(exc.status_code, "INTERNAL")
                    ]
                    raise
                except BaseException:
                    request.state.otel_graphql_errors = ["INTERNAL"]
                    raise
                finally:
                    attributes["graphql.operation.type"] = getattr(request.state, "otel_graphql_kind", "unknown")
                    errors = getattr(request.state, "otel_graphql_errors", [])
                    if errors:
                        attributes["error.type"] = "graphql_error"
                        span.set_status(Status(StatusCode.ERROR))
                        for code in errors:
                            self.graphql_errors.add(1, {**attributes, "moss.error.code": code})
                    span.set_attributes(attributes)
                    self.graphql_duration.record(time.perf_counter() - started, attributes)

        return measured

    def before_sql(self, connection, cursor, statement, parameters, context, executemany):
        first = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else "OTHER"
        operation = first if first in SQL_OPERATIONS else "OTHER"
        table = "other"
        match = re.search(r'\b(?:FROM|INTO|UPDATE|TABLE)\s+"?([a-zA-Z_][a-zA-Z_0-9]*)', statement, re.IGNORECASE)
        if match and match[1] in self.tables:
            table = match[1]
        attributes = {"db.system.name": self.db_system, "db.operation.name": operation, "db.collection.name": table}
        scope = HTTP_SCOPE.get()
        attributes["moss.execution"] = "request" if scope is not None else "background"
        if scope is not None:
            attributes["http.route"] = getattr(scope.get("route"), "path", "unmatched")
        span = self.tracer.start_span(f"DB {operation} {table}", kind=SpanKind.CLIENT, attributes=attributes)
        context._moss_otel_query = (span, time.perf_counter(), attributes)

    def finish_sql(self, context, failed=False):
        captured = getattr(context, "_moss_otel_query", None)
        if captured is None:
            return
        context._moss_otel_query = None
        span, started, attributes = captured
        if failed:
            attributes["error.type"] = "database_error"
            span.set_attribute("error.type", "database_error")
            span.set_status(Status(StatusCode.ERROR))
        self.db_duration.record(time.perf_counter() - started, attributes)
        span.end()

    def after_sql(self, connection, cursor, statement, parameters, context, executemany):
        self.finish_sql(context)

    def sql_error(self, exception_context):
        self.finish_sql(exception_context.execution_context, failed=True)

    def log_fields(self):
        if not self.enabled:
            return {}
        context = trace.get_current_span().get_span_context()
        if not context.is_valid:
            return {}
        return {"traceId": f"{context.trace_id:032x}", "spanId": f"{context.span_id:016x}"}


class TelemetryMiddleware:
    def __init__(self, app, telemetry):
        self.app, self.telemetry = app, telemetry

    async def __call__(self, scope, receive, send):
        telemetry = self.telemetry
        if scope["type"] != "http" or not telemetry.enabled:
            return await self.app(scope, receive, send)
        method = scope["method"] if scope["method"] in METHODS else "_OTHER"
        attributes = {"http.request.method": method}
        carrier = {
            "traceparent": value.decode("latin1") for key, value in scope.get("headers", []) if key == b"traceparent"
        }
        parent = TraceContextTextMapPropagator().extract(carrier)
        started = time.perf_counter()
        status = None
        scope_token = HTTP_SCOPE.set(scope)

        async def measured_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        with telemetry.tracer.start_as_current_span(
            f"HTTP {method}",
            context=parent,
            kind=SpanKind.SERVER,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                await self.app(scope, receive, measured_send)
            except BaseException:
                attributes["error.type"] = "request_aborted"
                span.set_status(Status(StatusCode.ERROR))
                raise
            finally:
                route = getattr(scope.get("route"), "path", "unmatched")
                attributes["http.route"] = route
                if status is not None:
                    attributes["http.response.status_code"] = status
                    if status >= 500:
                        attributes["error.type"] = str(status)
                        span.set_status(Status(StatusCode.ERROR))
                span.update_name(f"{method} {route}")
                span.set_attributes(attributes)
                request_id = scope.get("state", {}).get("request_id")
                if request_id:
                    span.set_attribute("moss.request.id", request_id)
                try:
                    telemetry.http_duration.record(time.perf_counter() - started, attributes)
                finally:
                    HTTP_SCOPE.reset(scope_token)
