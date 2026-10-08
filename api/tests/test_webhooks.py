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
