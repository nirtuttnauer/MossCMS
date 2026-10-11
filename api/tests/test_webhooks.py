import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import Mock, patch
import pytest
from sqlalchemy import select
from app.models import WebhookDelivery, now
from app.security import CmsError
from app.webhooks import destination, send, deliver
from conftest import define, entry
from test_cms import invited


def dns(ip):
    return [(2, 1, 6, "", (ip, 443))]


def test_destination_policy_and_pinned_signed_send():
    for url in [
        "http://public.example/hook",
        "https://user:pass@host/hook",
        "https://host/hook?secret=x",
        "file:///path",
    ]:
        with pytest.raises(CmsError):
            destination(url)
    with patch("app.webhooks.socket.getaddrinfo", return_value=dns("127.0.0.1")):
        with pytest.raises(CmsError):
            destination("https://host/hook")
        assert destination("http://host/hook", ["http://host"])[2] == "127.0.0.1"
    connection = Mock()
    connection.getresponse.return_value.status = 302
    payload = {"id": "event-id", "event": "published"}
    with (
        patch("app.webhooks.socket.getaddrinfo", return_value=dns("1.1.1.1")),
        patch("app.webhooks.http.client.HTTPSConnection", return_value=connection),
        patch("app.webhooks.socket.create_connection") as connect,
    ):
        assert send("https://host/hook", payload, "secret", []) == 302
        connection._create_connection(("host", 443))
        assert connect.call_args.args[0] == ("1.1.1.1", 443)
        args = connection.request.call_args.args
        timestamp = args[3]["X-Moss-Timestamp"]
        assert (
            args[3]["X-Moss-Signature"]
            == "sha256=" + hmac.new(b"secret", timestamp.encode() + b"." + args[2], hashlib.sha256).hexdigest()
        )
        assert json.loads(args[2]) == payload


@pytest.mark.parametrize(
    "url,allowed,connection_kind,port,ip",
    [
        ("https://host:8443/hook", [], "HTTPSConnection", 8443, "1.1.1.1"),
        ("http://host:8080/hook", ["http://host:8080"], "HTTPConnection", 8080, "127.0.0.1"),
    ],
)
def test_send_connection_kind_timeout_and_pinned_address(url, allowed, connection_kind, port, ip):
    connection = Mock()
    connection.getresponse.return_value.status = 204
    with (
        patch("app.webhooks.socket.getaddrinfo", return_value=dns(ip)),
        patch("app.webhooks.http.client.HTTPSConnection", return_value=connection) as https,
        patch("app.webhooks.http.client.HTTPConnection", return_value=connection) as http,
        patch("app.webhooks.socket.create_connection") as connect,
    ):
        assert send(url, {"id": "event-id"}, "secret", allowed) == 204
        selected, unused = (https, http) if connection_kind == "HTTPSConnection" else (http, https)
        selected.assert_called_once_with("host", port, timeout=5)
        unused.assert_not_called()
        assert connection._create_connection(("host", port)) is connect.return_value
        connect.assert_called_once_with((ip, port), 5, None)
        source_address = ("127.0.0.1", 1234)
        assert (
            connection._create_connection(("other-host", 9999), timeout=7, source_address=source_address)
            is connect.return_value
        )
        connect.assert_called_with((ip, port), 7, source_address)
        connection.close.assert_called_once_with()


@pytest.mark.parametrize("failed_call", ["request", "getresponse"])
def test_send_closes_connection_and_propagates_transport_failure(failed_call):
    connection = Mock()
    failure = OSError("transport failed")
    getattr(connection, failed_call).side_effect = failure
    with (
        patch("app.webhooks.socket.getaddrinfo", return_value=dns("1.1.1.1")),
        patch("app.webhooks.http.client.HTTPSConnection", return_value=connection),
        pytest.raises(OSError) as raised,
    ):
        send("https://host/hook", {"id": "event-id"}, "secret", [])
    assert raised.value is failure
    connection.close.assert_called_once_with()
    if failed_call == "request":
        connection.getresponse.assert_not_called()


def test_send_default_path_canonical_body_and_signature():
    connection = Mock()
    connection.getresponse.return_value.status = 302
    payload = {"z": {"b": 2, "a": 1}, "id": "event-id", "event": "published"}
    body = b'{"event":"published","id":"event-id","z":{"a":1,"b":2}}'
    timestamp = "1700000000"
    signature = hmac.new(b"secret", timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    with (
        patch("app.webhooks.socket.getaddrinfo", return_value=dns("1.1.1.1")),
        patch("app.webhooks.http.client.HTTPSConnection", return_value=connection),
        patch("app.webhooks.time.time", return_value=1700000000.75),
    ):
        assert send("https://host", payload, "secret", []) == 302
    connection.request.assert_called_once_with(
        "POST",
        "/",
        body,
        {
            "Content-Type": "application/json",
            "X-Moss-Event-ID": "event-id",
            "X-Moss-Timestamp": timestamp,
            "X-Moss-Signature": "sha256=" + signature,
        },
    )
    connection.close.assert_called_once_with()


@pytest.mark.parametrize("url", ["http://host/hook", "https://host/hook"])
def test_send_rejects_destination_before_constructing_connection(url):
    with (
        patch("app.webhooks.socket.getaddrinfo", return_value=dns("127.0.0.1")),
        patch("app.webhooks.http.client.HTTPSConnection") as https,
        patch("app.webhooks.http.client.HTTPConnection") as http,
        patch("app.webhooks.socket.create_connection") as connect,
        pytest.raises(CmsError),
    ):
        send(url, {"id": "event-id"}, "secret", [])
    https.assert_not_called()
    http.assert_not_called()
    connect.assert_not_called()


def test_delivery_history_roles_bounded_retries_and_secret_redaction(app, client, admin):
    with patch("app.webhooks.socket.getaddrinfo", return_value=dns("1.1.1.1")):
        created = client.post("/api/webhooks", headers=admin, json={"url": "https://host/hook"}).json()
    assert len(created["secret"]) > 32
    history = client.get("/api/webhooks", headers=admin)
    assert created["secret"] not in history.text
    reader, headers, _ = invited(app, client, admin, "reader", "hook-reader@example.com")
    assert reader.get("/api/webhooks", headers=headers).status_code == 403
    define(client, admin)
    entry(client, admin, status="published")
    with patch("app.webhooks.send", return_value=302) as sender:
        for _ in range(6):
            with app.state.db.begin() as session:
                for row in session.scalars(select(WebhookDelivery)).all():
                    row.next_at = now() - timedelta(seconds=1)
            deliver(app.state.db, app.state.settings)
        assert sender.call_count == 6
    history = client.get("/api/webhooks", headers=admin).json()["deliveries"]
    assert len(history) == 1 and history[0]["state"] == "failed" and history[0]["attempts"] == 6
    assert client.delete("/api/webhooks/" + created["id"], headers=admin).status_code == 200
