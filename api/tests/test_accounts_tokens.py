"""Delivery secrets, invitation links, and logout.

Create shows the delivery secret in that response. List and other reads leave it
out, and the list id does not authorize a delivery call. An invitation can be
accepted once, and it is rejected after expiry or after revoke while unused.
Logout rejects the previous session cookie. Request logs and the audit log do
not contain those secrets or passwords.
"""

import logging
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Token, User, now

INVITE_PASSWORD = "member-invite-pass"
ADMIN_PASSWORD = "secure-test-password"
REJECTED = "This invitation or recovery link is invalid or expired."


def assert_status(response, code):
    if response.status_code != code:
        raise AssertionError(
            f"status {response.status_code} != {code} for {response.request.method} {response.request.url.path}"
        )


def assert_hidden(blob, *needles):
    for needle in needles:
        if needle and needle in blob:
            raise AssertionError("a secret appeared in a response or log")


def issue_invite(client, admin, email, role="editor"):
    response = client.post("/api/team/invitations", headers=admin, json={"email": email, "role": role})
    assert_status(response, 200)
    if response.headers.get("cache-control") != "no-store":
        raise AssertionError("invitation create was cacheable")
    url = response.json().get("url", "")
    raw = url.rsplit("/", 1)[-1]
    if not raw or raw == url or "/" in raw:
        raise AssertionError("invitation response did not carry a secret segment")
    return raw


def accept_payload(raw, email):
    return {"token": raw, "email": email, "password": INVITE_PASSWORD, "name": "Invited member"}


def invitation_row(client, admin, email):
    response = client.get("/api/team", headers=admin)
    assert_status(response, 200)
    if response.headers.get("cache-control") != "no-store":
        raise AssertionError("team read was cacheable")
    rows = [row for row in response.json()["invitations"] if row["email"] == email]
    return response, rows


def user_id(app, email):
    with app.state.db() as session:
        return session.scalar(select(User.id).where(User.email == email))


def test_delivery_create_returns_secret_and_reads_omit_it(client, admin, caplog):
    with caplog.at_level(logging.INFO):
        created = client.post("/api/tokens", headers=admin, json={"name": "Website reader", "scopes": [], "days": 7})
    assert_status(created, 200)
    if created.headers.get("cache-control") != "no-store":
        raise AssertionError("delivery create was cacheable")
    body = created.json()
    if set(body) != {"token"}:
        raise AssertionError("create response keys: " + ", ".join(sorted(body)))
    raw = body["token"]
    if not isinstance(raw, str) or len(raw) < 20:
        raise AssertionError("create response did not include a delivery secret")
    assert_hidden(str(created.headers), raw)

    listed = client.get("/api/tokens", headers=admin)
    assert_status(listed, 200)
    if listed.headers.get("cache-control") != "no-store":
        raise AssertionError("delivery list was cacheable")
    matches = [row for row in listed.json() if row.get("name") == "Website reader"]
    if len(matches) != 1:
        raise AssertionError("delivery list did not contain the created token")
    record = matches[0]
    if set(record) != {"id", "name", "scopes", "expiresAt"}:
        raise AssertionError("delivery list fields: " + ", ".join(sorted(record)))
    handle = record["id"]
    if handle == raw:
        raise AssertionError("delivery list id repeated the secret")
    assert_hidden(listed.text, raw)
    assert_hidden(str(listed.headers), raw)

    fetched = client.get("/api/tokens/" + handle, headers=admin)
    if fetched.status_code == 200:
        raise AssertionError("a delivery token read returned a document")
    assert_hidden(fetched.text, raw)

    denied = client.get("/delivery/types", headers={"Authorization": "Bearer " + handle})
    assert_status(denied, 401)
    allowed = client.get("/delivery/types", headers={"Authorization": "Bearer " + raw})
    assert_status(allowed, 200)
    assert allowed.json() == []

    again = client.get("/api/tokens", headers=admin)
    assert_status(again, 200)
    assert_hidden(again.text, raw)

    audit = client.post("/graphql", headers=admin, json={"query": "{auditLog}"})
    assert_status(audit, 200)
    assert_hidden(audit.text, raw)
    assert_hidden(caplog.text, raw)

    removed = client.delete("/api/tokens/" + handle, headers=admin)
    assert_status(removed, 200)
    assert_status(client.get("/delivery/types", headers={"Authorization": "Bearer " + raw}), 401)
    assert_status(client.get("/delivery/types", headers={"Authorization": "Bearer " + handle}), 401)
    remaining = client.get("/api/tokens", headers=admin)
    assert_hidden(remaining.text, raw)
    if any(row.get("id") == handle for row in remaining.json()):
        raise AssertionError("revoked delivery token stayed in the list")


def test_invitation_works_once(app, client, admin, caplog):
    email = "once@example.com"
    with caplog.at_level(logging.INFO):
        raw = issue_invite(client, admin, email)
        listed, rows = invitation_row(client, admin, email)
    if len(rows) != 1:
        raise AssertionError("pending invitation was missing")
    record = rows[0]
    if set(record) != {"id", "email", "role", "expiresAt"}:
        raise AssertionError("invitation fields: " + ", ".join(sorted(record)))
    if record["id"] == raw or record["role"] != "editor":
        raise AssertionError("invitation list repeated the secret or stored the wrong role")
    assert_hidden(listed.text, raw)

    outsider = TestClient(app)
    rejected = outsider.post("/auth/accept", json=accept_payload(record["id"], email))
    assert_status(rejected, 400)
    if rejected.json().get("detail") != REJECTED:
        raise AssertionError("list id was treated as an invitation secret")
    assert user_id(app, email) is None

    body = accept_payload(raw, email)
    member = TestClient(app)
    with caplog.at_level(logging.INFO):
        accepted = member.post("/auth/accept", json=body)
    assert_status(accepted, 200)
    if accepted.headers.get("cache-control") != "no-store":
        raise AssertionError("invitation accept was cacheable")
    account = member.get("/auth/me")
    assert_status(account, 200)
    if account.json()["user"]["email"] != email:
        raise AssertionError("accepted account email did not match the invitation")

    repeat = TestClient(app)
    second = repeat.post("/auth/accept", json=body)
    assert_status(second, 400)
    if second.json().get("detail") != REJECTED:
        raise AssertionError("used invitation was still acceptable")
    assert_hidden(second.text, raw, INVITE_PASSWORD)

    team = client.get("/api/team", headers=admin)
    assert_status(team, 200)
    payload = team.json()
    if not any(row["email"] == email and row["role"] == "editor" for row in payload["members"]):
        raise AssertionError("accepted member was missing")
    if any(row["email"] == email for row in payload["invitations"]):
        raise AssertionError("used invitation stayed pending")
    assert_hidden(team.text, raw, INVITE_PASSWORD)

    with app.state.db() as session:
        stored = session.scalar(select(User.password_hash).where(User.email == email))
        token = session.scalar(select(Token.id).where(Token.kind == "invite", Token.email == email))
    assert_hidden(stored or "", INVITE_PASSWORD)
    if token is not None:
        raise AssertionError("used invitation row remained")

    audit = client.post("/graphql", headers=admin, json={"query": "{auditLog}"})
    assert_status(audit, 200)
    assert_hidden(audit.text, raw, INVITE_PASSWORD)
    assert_hidden(caplog.text, raw, INVITE_PASSWORD)
    assert_hidden(str(member.cookies), raw, INVITE_PASSWORD)


def test_expired_invitation_is_rejected(app, client, admin, caplog):
    email = "expired@example.com"
    with caplog.at_level(logging.INFO):
        raw = issue_invite(client, admin, email, role="reader")
    with app.state.db.begin() as session:
        row = session.scalar(select(Token).where(Token.kind == "invite", Token.email == email))
        if row is None:
            raise AssertionError("invitation row was missing before expiry")
        if row.id == raw:
            raise AssertionError("invitation row stored the raw secret")
        row.expires_at = now() - timedelta(hours=1)
    listed, rows = invitation_row(client, admin, email)
    if rows:
        raise AssertionError("expired invitation stayed in the pending list")
    assert_hidden(listed.text, raw)
    outsider = TestClient(app)
    with caplog.at_level(logging.INFO):
        rejected = outsider.post("/auth/accept", json=accept_payload(raw, email))
    assert_status(rejected, 400)
    if rejected.json().get("detail") != REJECTED:
        raise AssertionError("expired invitation was accepted")
    assert_hidden(rejected.text, raw, INVITE_PASSWORD)
    assert user_id(app, email) is None
    audit = client.post("/graphql", headers=admin, json={"query": "{auditLog}"})
    assert_hidden(audit.text, raw, INVITE_PASSWORD)
    assert_hidden(caplog.text, raw, INVITE_PASSWORD)


def test_revoked_unused_invitation_is_rejected(app, client, admin, caplog):
    email = "revoked@example.com"
    with caplog.at_level(logging.INFO):
        raw = issue_invite(client, admin, email)
        listed, rows = invitation_row(client, admin, email)
    if len(rows) != 1:
        raise AssertionError("unused invitation was missing")
    assert_hidden(listed.text, raw)
    with caplog.at_level(logging.INFO):
        revoked = client.delete("/api/team/invitations/" + rows[0]["id"], headers=admin)
    assert_status(revoked, 200)
    if revoked.json() != {"ok": True}:
        raise AssertionError("revoke did not acknowledge")
    gone, remaining = invitation_row(client, admin, email)
    if remaining:
        raise AssertionError("revoked invitation stayed pending")
    assert_hidden(gone.text, raw)
    outsider = TestClient(app)
    with caplog.at_level(logging.INFO):
        rejected = outsider.post("/auth/accept", json=accept_payload(raw, email))
    assert_status(rejected, 400)
    if rejected.json().get("detail") != REJECTED:
        raise AssertionError("revoked invitation was accepted")
    assert_hidden(rejected.text, raw, INVITE_PASSWORD)
    assert user_id(app, email) is None
    with app.state.db() as session:
        leftover = session.scalar(select(Token.id).where(Token.kind == "invite", Token.email == email))
    if leftover is not None:
        raise AssertionError("revoked invitation row remained")
    audit = client.post("/graphql", headers=admin, json={"query": "{auditLog}"})
    assert_hidden(audit.text, raw, INVITE_PASSWORD)
    assert_hidden(caplog.text, raw, INVITE_PASSWORD)


def test_logout_rejects_the_previous_session_cookie(app, client, admin, caplog):
    saved = client.cookies.get("moss_session")
    if not saved:
        raise AssertionError("session cookie was missing")
    probe = TestClient(app)
    probe.cookies.set("moss_session", saved)
    assert_status(probe.get("/auth/me"), 200)

    with caplog.at_level(logging.INFO):
        logged_out = client.post("/auth/logout", headers={"x-moss-csrf": admin["x-moss-csrf"]})
    assert_status(logged_out, 200)
    if logged_out.json() != {"ok": True}:
        raise AssertionError("logout did not acknowledge")
    if logged_out.headers.get("cache-control") != "no-store":
        raise AssertionError("logout was cacheable")
    assert_hidden(logged_out.text, saved, ADMIN_PASSWORD)
    assert_hidden(str(logged_out.headers), saved)

    assert_status(probe.get("/auth/me"), 401)
    assert_status(probe.get("/api/tokens", headers={"x-moss-project": admin["x-moss-project"]}), 401)
    replay = TestClient(app)
    replay.cookies.set("moss_session", saved)
    assert_status(replay.get("/auth/me"), 401)
    replay.cookies.set("moss_session", saved)
    denied = replay.post("/graphql", json={"query": "{auditLog}"})
    assert_status(denied, 401)

    with caplog.at_level(logging.INFO):
        signed = client.post("/auth/login", json={"email": "admin@example.com", "password": ADMIN_PASSWORD})
    assert_status(signed, 200)
    me = client.get("/auth/me")
    assert_status(me, 200)
    if me.json()["user"]["email"] != "admin@example.com":
        raise AssertionError("a new sign-in did not restore the account")
    assert_status(probe.get("/auth/me"), 401)
    assert_status(replay.get("/auth/me"), 401)
    current = client.cookies.get("moss_session")
    if not current or current == saved:
        raise AssertionError("sign-in reused the logged-out session cookie")
    assert_hidden(caplog.text, saved, current, ADMIN_PASSWORD)
    audit = client.post(
        "/graphql",
        headers={"x-moss-project": me.json()["projects"][0]["id"], "x-moss-csrf": me.json()["csrf"]},
        json={"query": "{auditLog}"},
    )
    assert_status(audit, 200)
    assert_hidden(audit.text, saved, current, ADMIN_PASSWORD)
