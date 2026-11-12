"""Bounded bodies for /health and /ready, and an admin session for /metrics."""

import re

from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from test_cms import delivery, invited

METRIC_NAMES = (
    "moss_requests_total",
    "moss_errors_total",
    "moss_request_duration_seconds_sum",
    "moss_uptime_seconds",
)
METRIC_BODY = re.compile(
    r"^moss_requests_total \d+\n"
    r"moss_errors_total \d+\n"
    r"moss_request_duration_seconds_sum \S+\n"
    r"moss_uptime_seconds \S+\n$"
)
FAILURE_MARKER = "ready-check-failed-moss087"


def _sentinels(settings):
    url = make_url(settings.database_url)
    candidates = [
        settings.secret,
        settings.setup_token,
        settings.database_url,
        settings.public_url,
        settings.otel_endpoint,
        str(settings.storage_dir),
        url.password,
        *settings.origins,
        *settings.webhook_origins,
    ]
    if settings.s3_bucket:
        candidates.append(settings.s3_bucket)
    if settings.s3_endpoint:
        candidates.append(settings.s3_endpoint)
    return [value for value in candidates if isinstance(value, str) and len(value) >= 8]


def _assert_absent(body, sentinels):
    for name in METRIC_NAMES:
        assert name not in body
    for value in sentinels:
        assert value not in body
    assert FAILURE_MARKER not in body
    assert "Traceback" not in body


def _assert_status(response, status_code, status, sentinels):
    assert response.status_code == status_code, response.text
    assert response.json() == {"status": status}
    _assert_absent(response.text, sentinels)


def test_health_body_is_a_bounded_status(client, app):
    sentinels = _sentinels(app.state.settings)
    marker = "health-query-moss087"
    response = client.get("/health", params={"token": marker}, headers={"X-Moss-Debug": marker})
    _assert_status(response, 200, "ok", [*sentinels, marker])


def test_ready_body_is_a_bounded_status(client, app):
    sentinels = _sentinels(app.state.settings)
    marker = "ready-query-moss087"
    response = client.get("/ready", params={"database_url": marker}, headers={"X-Moss-Debug": marker})
    _assert_status(response, 200, "ready", [*sentinels, marker])


def test_ready_failure_is_unavailable_without_settings(client, app, monkeypatch):
    sentinels = _sentinels(app.state.settings)
    detail = FAILURE_MARKER + " " + " ".join(sentinels)

    def fail_connect(*_args, **_kwargs):
        raise RuntimeError(detail)

    monkeypatch.setattr(app.state.engine, "connect", fail_connect)
    response = client.get("/ready")
    _assert_status(response, 503, "unavailable", sentinels)
    assert client.get("/health").json() == {"status": "ok"}


def test_metrics_without_admin_omits_values(app, client, admin):
    sentinels = _sentinels(app.state.settings)
    anonymous = TestClient(app)
    denied = anonymous.get(
        "/metrics",
        headers={"Authorization": f"Bearer {app.state.settings.secret}", "x-moss-project": admin["x-moss-project"]},
    )
    assert denied.status_code in {401, 403}, denied.text
    _assert_absent(denied.text, sentinels)

    delivered = anonymous.get("/metrics", headers=delivery(client, admin))
    assert delivered.status_code in {401, 403}, delivered.text
    _assert_absent(delivered.text, sentinels)

    reader, reader_headers, _ = invited(app, client, admin, "reader", "health-reader@example.com")
    reader_denied = reader.get("/metrics", headers=reader_headers)
    assert reader_denied.status_code in {401, 403}, reader_denied.text
    _assert_absent(reader_denied.text, sentinels)

    editor, editor_headers, _ = invited(app, client, admin, "editor", "health-editor@example.com")
    editor_denied = editor.get("/metrics", headers=editor_headers)
    assert editor_denied.status_code in {401, 403}, editor_denied.text
    _assert_absent(editor_denied.text, sentinels)

    missing_project = client.get("/metrics")
    assert missing_project.status_code in {401, 403}, missing_project.text
    _assert_absent(missing_project.text, sentinels)


def test_metrics_admin_body_is_the_counter_lines(client, admin, app):
    sentinels = _sentinels(app.state.settings)
    response = client.get("/metrics", headers=admin)
    assert response.status_code == 200, response.text
    assert METRIC_BODY.match(response.text)
    for value in sentinels:
        assert value not in response.text
    assert FAILURE_MARKER not in response.text
