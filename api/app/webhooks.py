"""Admin-managed signed delivery with DNS pinning and recoverable bounded retries."""

import hashlib
import hmac
import http.client
import ipaddress
import json
import secrets
import socket
import time
from datetime import timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from .accounts import context
from .models import PublicationEvent, Webhook, WebhookDelivery, now, uid
from .outbox import claim_events, prune_events
from .security import CmsError, audit, require

router = APIRouter()
RETRY_DELAYS_SECONDS = (5, 30, 120, 600, 3600, 3600)
_HTTP_TIMEOUT_SECONDS = 5


def destination(url, allowed=()):
    parsed = urlsplit(url)
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        raise CmsError("Invalid webhook destination.") from None
    origin = f"{parsed.scheme}://{parsed.netloc}"
    local = origin in allowed
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.query
        or (parsed.scheme != "https" and not local)
    ):
        raise CmsError(
            "Webhooks require HTTPS without credentials, query or fragment; local origins require operator allowlisting."
        )
    try:
        addresses = sorted({row[4][0] for row in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)})
        if not addresses or (not local and any(not ipaddress.ip_address(ip).is_global for ip in addresses)):
            raise CmsError("Private-network webhook destinations require an explicit operator origin allowlist.")
    except (OSError, ValueError):
        raise CmsError("Webhook destination could not be safely resolved.") from None
    return parsed, port, addresses[0]


def send(url, payload, secret, allowed):
    parsed, port, ip = destination(url, allowed)  # resolve and validate on every attempt
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    kind = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = kind(parsed.hostname, port, timeout=_HTTP_TIMEOUT_SECONDS)
    # Pin the verified address, while HTTPSConnection retains original-host TLS SNI/verification.
    setattr(
        connection,
        "_create_connection",
        lambda address, timeout=_HTTP_TIMEOUT_SECONDS, source_address=None: socket.create_connection(
            (ip, port), timeout, source_address
        ),
    )
    try:
        connection.request(
            "POST",
            parsed.path or "/",
            body,
            {
                "Content-Type": "application/json",
                "X-Moss-Event-ID": payload["id"],
                "X-Moss-Timestamp": timestamp,
                "X-Moss-Signature": "sha256=" + signature,
            },
        )
        return connection.getresponse().status  # redirects are failures; no response bodies retained
    finally:
        connection.close()


class SubscriptionInput(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


@router.get("/api/webhooks")
def subscriptions(request: Request):
    with request.app.state.db() as session:
        c = context(request, session)
        require(c, "admin")
        rows = session.scalars(select(Webhook).where(Webhook.project_id == c["project_id"])).all()
        history = session.scalars(
            select(WebhookDelivery)
            .where(WebhookDelivery.project_id == c["project_id"])
            .order_by(WebhookDelivery.created_at.desc())
            .limit(100)
        ).all()
        return {
            "endpoints": [{"id": r.id, "url": r.url, "enabled": r.enabled} for r in rows],
            "deliveries": [
                {
                    "id": r.id,
                    "eventId": r.event_id,
                    "webhookId": r.webhook_id,
                    "state": r.state,
                    "attempts": r.attempts,
                    "error": r.error,
                    "nextAt": r.next_at.isoformat() + "Z",
                }
                for r in history
            ],
        }


@router.post("/api/webhooks")
def subscribe(body: SubscriptionInput, request: Request):
    with request.app.state.db.begin() as session:
        c = context(request, session)
        require(c, "admin", write=True)
        if session.scalar(select(Webhook.id).where(Webhook.project_id == c["project_id"], Webhook.enabled).offset(9)):
            raise CmsError("Use at most ten active webhook endpoints per workspace.")
        destination(body.url, request.app.state.settings.webhook_origins)
        secret = secrets.token_urlsafe(32)
        hook = Webhook(project_id=c["project_id"], url=body.url, secret=secret)
        session.add(hook)
        session.flush()
        audit(session, c["project_id"], c["actor"], "webhook.create", webhookId=hook.id)
        return {"id": hook.id, "secret": secret}


@router.delete("/api/webhooks/{id}")
def disable(id: str, request: Request):
    with request.app.state.db.begin() as session:
        c = context(request, session)
        require(c, "admin", write=True)
        hook = session.get(Webhook, id)
        if not hook or hook.project_id != c["project_id"]:
            raise CmsError("Webhook not found.", "NOT_FOUND")
        hook.enabled = False
        hook.secret = "revoked"
        audit(session, c["project_id"], c["actor"], "webhook.disable", webhookId=id)
    return {"ok": True}


def fanout(factory):
    for event in claim_events(factory):
        with factory.begin() as session:
            row = session.scalar(select(PublicationEvent).where(PublicationEvent.id == event["id"]).with_for_update())
            if row.state != "processing" or row.claim != event["claim"]:
                continue
            for hook in session.scalars(
                select(Webhook).where(Webhook.project_id == row.project_id, Webhook.enabled)
            ).all():
                session.add(
                    WebhookDelivery(project_id=row.project_id, event_id=row.id, webhook_id=hook.id, payload=row.payload)
                )
            row.state = "processed"
            row.claim = None
            row.lease_until = None


def deliver(factory, settings):
    fanout(factory)
    for _ in range(10):
        with factory.begin() as session:
            row = session.scalar(
                select(WebhookDelivery)
                .where(WebhookDelivery.state.in_(["pending", "retry", "sending"]), WebhookDelivery.next_at <= now())
                .order_by(WebhookDelivery.next_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if not row:
                break
            hook = session.get(Webhook, row.webhook_id)
            if not hook or not hook.enabled or row.attempts >= len(RETRY_DELAYS_SECONDS):
                row.state = "failed"
                row.error = "Disabled endpoint or retry limit reached"
                continue
            row.attempts += 1
            row.state = "sending"
            row.claim = uid()
            row.next_at = now() + timedelta(minutes=2)
            id, claim, payload, url, secret = row.id, row.claim, row.payload, hook.url, hook.secret
        try:
            status = send(url, payload, secret, settings.webhook_origins)
            success = 200 <= status < 300
            reason = None if success else f"HTTP {status}"
        except Exception:
            success = False
            reason = "Destination policy, connection or timeout failure"
        with factory.begin() as session:
            row = session.scalar(select(WebhookDelivery).where(WebhookDelivery.id == id).with_for_update())
            if row.claim != claim or row.state != "sending":
                continue
            row.state = "delivered" if success else "failed" if row.attempts >= len(RETRY_DELAYS_SECONDS) else "retry"
            row.error = reason
            row.claim = None
            row.next_at = now() + timedelta(seconds=RETRY_DELAYS_SECONDS[row.attempts - 1])
    prune_events(factory)
    with factory.begin() as session:
        session.execute(
            delete(WebhookDelivery).where(
                WebhookDelivery.state.in_(["delivered", "failed"]),
                WebhookDelivery.created_at < now() - timedelta(days=30),
            )
        )
