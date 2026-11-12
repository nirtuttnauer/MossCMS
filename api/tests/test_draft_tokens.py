import json
import logging
import uuid
from datetime import timedelta

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from sqlalchemy import select

from app.accounts import context
from app.config import Settings
from app.content import save_entry
from app.draft_tokens import issue_draft_token, read_draft_snapshot, revoke_draft_token
from app.main import create_app
from app.models import Audit, Token, now
from app.security import CmsError, audit, digest, identify, require
from conftest import define, entry, gql
from test_cms import delivery, invited

HEBREW = "בְּרֵאשִׁית בָּרָא"


def as_request(app, headers, *, bearer=None, cookie=None):
    pairs = []
    if bearer is not None:
        pairs.append((b"authorization", b"Bearer " + bearer.encode()))
    if cookie is not None:
        pairs.append((b"cookie", f"moss_session={cookie}".encode()))
    for key, value in headers.items():
        pairs.append((key.lower().encode(), str(value).encode()))
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": pairs,
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "app": app,
        }
    )


def test_draft_token_reads_same_project_draft_including_hebrew_niqqud(app, client, admin):
    define(client, admin)
    published = entry(
        client,
        admin,
        slug="live",
        data={"title": "Live", "body": "public", "secret": "hidden"},
        status="published",
    )["data"]["saveEntry"]
    updated = entry(
        client,
        admin,
        slug="live",
        data={"title": HEBREW, "body": HEBREW, "secret": "סוֹד"},
        status="draft",
        id=published["id"],
        version=published["version"],
    )["data"]["saveEntry"]
    request = as_request(app, admin, cookie=client.cookies.get("moss_session"))
    with app.state.db.begin() as session:
        raw = issue_draft_token(session, context(request, session), name="Draft reader")
        stored = session.get(Token, digest(raw))
        assert stored.kind == "drafts"
        assert stored.project_id == admin["x-moss-project"]
        assert stored.role == "reader"
        assert stored.csrf == ""
        assert stored.user_id is None
        issued = session.scalars(select(Audit).where(Audit.action == "draft_token.issue")).all()
    assert raw not in json.dumps([row.details for row in issued])
    assert raw not in "".join(row.actor for row in issued)

    snapshot = None
    with app.state.db() as session:
        snapshot = read_draft_snapshot(as_request(app, {}, bearer=raw), session, updated["id"])
    assert snapshot["id"] == updated["id"]
    assert snapshot["slug"] == "live"
    assert snapshot["title"] == HEBREW
    assert snapshot["data"] == {"title": HEBREW, "body": HEBREW, "secret": "סוֹד"}
    assert "\u05b0" in snapshot["data"]["body"]
    assert "\u05bc" in snapshot["data"]["title"]
    assert "\u05c1" in snapshot["data"]["body"]
    assert snapshot["data"]["title"] != "Live"

    delivered = gql(client, delivery(client, admin), "{entries{nodes{data}}}", delivery=True)
    assert delivered["data"]["entries"]["nodes"] == [{"data": {"title": "Live", "body": "public"}}]


def test_draft_token_fails_closed_for_expiry_other_projects_and_other_kinds(app, client, admin):
    define(client, admin)
    saved = entry(client, admin, slug="kept", data={"title": "Kept", "body": HEBREW})["data"]["saveEntry"]
    request = as_request(app, admin, cookie=client.cookies.get("moss_session"))
    with app.state.db.begin() as session:
        identity = context(request, session)
        raw = issue_draft_token(session, identity, name="Draft reader")
        with pytest.raises(CmsError):
            issue_draft_token(session, identity, name=" ", days=1)
        with pytest.raises(CmsError):
            issue_draft_token(session, identity, name="Draft reader", days=0)
    bearer = as_request(app, {}, bearer=raw)
    with app.state.db() as session:
        assert read_draft_snapshot(bearer, session, saved["id"])["data"]["body"] == HEBREW
        with pytest.raises(HTTPException) as missing:
            read_draft_snapshot(as_request(app, {}), session, saved["id"])
        assert missing.value.status_code == 401
        with pytest.raises(HTTPException) as session_cookie:
            read_draft_snapshot(as_request(app, admin, cookie=client.cookies.get("moss_session")), session, saved["id"])
        assert session_cookie.value.status_code == 401
        with pytest.raises(CmsError) as absent:
            read_draft_snapshot(bearer, session, "missing-entry")
        assert absent.value.code == "NOT_FOUND"

    other = client.post("/api/projects", headers=admin, json={"name": "Elsewhere"}).json()
    other_headers = {**admin, "x-moss-project": other["id"]}
    define(client, other_headers)
    foreign = entry(client, other_headers, slug="foreign", data={"title": "Foreign", "body": "other"})["data"][
        "saveEntry"
    ]
    with app.state.db.begin() as session:
        other_identity = context(as_request(app, other_headers, cookie=client.cookies.get("moss_session")), session)
        other_raw = issue_draft_token(session, other_identity)
    published_token = delivery(client, admin)["Authorization"].removeprefix("Bearer ")
    with app.state.db() as session:
        with pytest.raises(CmsError) as crossed:
            read_draft_snapshot(bearer, session, foreign["id"])
        assert crossed.value.code == "NOT_FOUND"
        with pytest.raises(CmsError) as reverse:
            read_draft_snapshot(as_request(app, {}, bearer=other_raw), session, saved["id"])
        assert reverse.value.code == "NOT_FOUND"
        with pytest.raises(HTTPException) as delivery_kind:
            read_draft_snapshot(as_request(app, {}, bearer=published_token), session, saved["id"])
        assert delivery_kind.value.status_code == 401

    with app.state.db.begin() as session:
        session.get(Token, digest(raw)).expires_at = now() - timedelta(seconds=1)
    with app.state.db() as session:
        with pytest.raises(HTTPException) as expired:
            read_draft_snapshot(bearer, session, saved["id"])
        assert expired.value.status_code == 401
        assert raw not in str(expired.value.detail)

    with app.state.db.begin() as session:
        kept = issue_draft_token(session, context(request, session), name="Revoked reader", days=2)
        revoke_draft_token(session, context(request, session), digest(kept))
    with app.state.db() as session:
        with pytest.raises(HTTPException) as revoked:
            read_draft_snapshot(as_request(app, {}, bearer=kept), session, saved["id"])
        assert revoked.value.status_code == 401
        rows = session.scalars(select(Audit).where(Audit.action == "draft_token.revoke")).all()
    assert kept not in json.dumps([row.details for row in rows], ensure_ascii=False)


def test_draft_token_never_authorizes_writes(app, client, admin):
    define(client, admin)
    saved = entry(client, admin)["data"]["saveEntry"]
    reader, reader_headers, _reader_id = invited(app, client, admin, "reader", "draft-reader@example.com")
    request = as_request(app, admin, cookie=client.cookies.get("moss_session"))
    with app.state.db.begin() as session:
        raw = issue_draft_token(session, context(request, session), name="Draft reader")
    bearer = {"Authorization": "Bearer " + raw}
    draft_request = as_request(app, bearer)
    with app.state.db.begin() as session:
        drafts = {**identify(draft_request, session, drafts=True), "request": draft_request, "session": session}
        require(drafts)
        with pytest.raises(CmsError) as blocked:
            require(drafts, "reader", write=True)
        assert blocked.value.code == "FORBIDDEN"
        forged = {**drafts, "role": "admin"}
        with pytest.raises(CmsError) as elevated:
            require(forged, "editor", write=True)
        assert elevated.value.code == "FORBIDDEN"
        with pytest.raises(CmsError) as editor_read:
            require(forged, "editor")
        assert editor_read.value.code == "FORBIDDEN"
        with pytest.raises(CmsError):
            save_entry(session, drafts, "article", "nope", {"title": "Nope", "body": "x"})
        with pytest.raises(CmsError):
            issue_draft_token(session, drafts, name="Nested")
        with pytest.raises(HTTPException) as both:
            identify(draft_request, session, delivery=True, drafts=True)
        assert both.value.status_code == 401

    reader_request = as_request(app, reader_headers, cookie=reader.cookies.get("moss_session"))
    with app.state.db.begin() as session:
        with pytest.raises(CmsError) as reader_issue:
            issue_draft_token(session, context(reader_request, session), name="Reader drafts")
        assert reader_issue.value.code == "FORBIDDEN"

    assert client.post("/graphql", headers=bearer, json={"query": "{entries{total}}"}).status_code == 401
    assert (
        client.post(
            "/graphql",
            headers=bearer,
            json={"query": 'mutation{deleteEntry(id:"' + saved["id"] + '",version:1)}'},
        ).status_code
        == 401
    )
    assert client.post("/delivery/graphql", headers=bearer, json={"query": "{entries{total}}"}).status_code == 401
    assert client.post("/api/preview/redeem", headers=bearer, json={"token": "x" * 32}).status_code == 401
    client.cookies.clear()
    client.cookies.set("moss_session", raw)
    assert client.post("/graphql", json={"query": "{entries{total}}"}).status_code == 401


def test_audit_omits_raw_tokens_and_passwords_from_details_and_logs(app, client, admin, caplog):
    define(client, admin)
    saved = entry(client, admin, data={"title": HEBREW, "body": HEBREW})["data"]["saveEntry"]
    password = "drafts-only-password"
    request = as_request(app, admin, cookie=client.cookies.get("moss_session"))
    caplog.set_level(logging.DEBUG)
    with app.state.db.begin() as session:
        raw = issue_draft_token(session, context(request, session), name="Draft reader")
        audit(
            session,
            admin["x-moss-project"],
            raw,
            "draft_token.probe",
            password=password,
            token=raw,
            note=raw,
            nested={"secret": password, "title": HEBREW, "tokenId": "a" * 64},
            authorization="Bearer " + raw,
            tokenId=digest(raw),
        )
    with app.state.db() as session:
        snapshot = read_draft_snapshot(as_request(app, {}, bearer=raw), session, saved["id"])
        row = session.scalar(select(Audit).where(Audit.action == "draft_token.probe"))
        issued = session.scalars(select(Audit).where(Audit.action == "draft_token.issue")).one()
    rendered = json.dumps({"details": row.details, "actor": row.actor, "issued": issued.details}, ensure_ascii=False)
    assert password not in rendered
    assert raw not in rendered
    assert "Bearer" not in rendered
    assert row.actor == "[redacted]"
    assert row.details["password"] == "[redacted]"
    assert row.details["token"] == "[redacted]"
    assert row.details["note"] == "[redacted]"
    assert row.details["nested"]["secret"] == "[redacted]"
    assert row.details["nested"]["title"] == HEBREW
    assert row.details["nested"]["tokenId"] == "a" * 64
    assert row.details["tokenId"] == digest(raw)
    assert snapshot["data"]["title"] == HEBREW
    assert password not in caplog.text
    assert raw not in caplog.text
    log_record = "\n".join(record.getMessage() for record in caplog.records)
    assert password not in log_record
    assert raw not in log_record


def test_skip_auth_does_not_turn_into_a_drafts_token(tmp_path):
    local = create_app(
        Settings(
            skip_auth=True,
            secret="s" * 40,
            setup_token="t" * 30,
            database_url=f"sqlite:///{tmp_path}/drafts.db",
            storage_dir=tmp_path / "media",
        )
    )
    from fastapi.testclient import TestClient

    with TestClient(local) as client:
        me = client.get("/auth/me").json()
        headers = {"x-moss-project": me["projects"][0]["id"], "x-moss-csrf": me["csrf"]}
        define(client, headers)
        saved = entry(client, headers, data={"title": HEBREW, "body": HEBREW})["data"]["saveEntry"]
        with local.state.db() as session:
            with pytest.raises(HTTPException) as denied:
                identify(as_request(local, {}), session, drafts=True)
            assert denied.value.status_code == 401
            developer = identify(as_request(local, headers), session)
            assert developer["role"] == "admin"
            assert not developer.get("drafts")
        with local.state.db.begin() as session:
            raw = issue_draft_token(session, context(as_request(local, headers), session), name="Local drafts")
        with local.state.db() as session:
            snapshot = read_draft_snapshot(as_request(local, {}, bearer=raw), session, saved["id"])
        assert snapshot["data"]["body"] == HEBREW
        assert raw not in snapshot["title"]


def test_draft_snapshot_applies_project_field_rules(app, client, admin):
    define(client, admin)
    saved = entry(client, admin, slug="ruled", data={"title": HEBREW, "body": "visible", "secret": "hidden"})["data"][
        "saveEntry"
    ]
    request = as_request(app, admin, cookie=client.cookies.get("moss_session"))
    with app.state.db.begin() as session:
        raw = issue_draft_token(session, context(request, session), name="Draft reader")
    bearer = as_request(app, {}, bearer=raw)
    with app.state.db() as session:
        unruled = read_draft_snapshot(bearer, session, saved["id"])
    assert unruled["data"] == {"title": HEBREW, "body": "visible", "secret": "hidden"}

    rules = {"article": {"reader": {"read": ["title", "body"], "write": ["title", "body"]}}}
    response = client.patch("/api/project/permissions", headers=admin, json={"enabled": True, "fieldRules": rules})
    assert response.status_code == 200, response.text
    with app.state.db() as session:
        ruled = read_draft_snapshot(bearer, session, saved["id"])
    assert ruled["data"] == {"title": HEBREW, "body": "visible"}
    assert "secret" not in ruled["data"]
    assert ruled["title"] == HEBREW

    rules = {"article": {"reader": {"read": ["body"], "write": ["body"]}}}
    response = client.patch("/api/project/permissions", headers=admin, json={"enabled": True, "fieldRules": rules})
    assert response.status_code == 200, response.text
    with app.state.db() as session:
        untitled = read_draft_snapshot(bearer, session, saved["id"])
    assert untitled["data"] == {"body": "visible"}
    assert untitled["title"] == "ruled"


def test_audit_keeps_entity_ids_and_redacts_issued_tokens(app, client, admin):
    define(client, admin)
    saved = entry(client, admin, data={"title": HEBREW, "body": HEBREW})["data"]["saveEntry"]
    request = as_request(app, admin, cookie=client.cookies.get("moss_session"))
    ids = {
        "entryId": saved["id"],
        "userId": str(uuid.uuid4()),
        "releaseId": str(uuid.uuid4()),
        "webhookId": str(uuid.uuid4()),
        "assetId": str(uuid.uuid4()),
    }
    with app.state.db.begin() as session:
        raw = issue_draft_token(session, context(request, session), name="Draft reader")
        audit(
            session,
            admin["x-moss-project"],
            "admin@example.com",
            "draft_token.ids",
            **ids,
            nested={"entryId": saved["id"], "note": raw},
            listed=[saved["id"], raw],
            note=raw,
            tokenId=digest(raw),
        )
    with app.state.db() as session:
        row = session.scalar(select(Audit).where(Audit.action == "draft_token.ids"))
        saves = session.scalars(select(Audit).where(Audit.action == "entry.save")).all()
    assert len(saved["id"]) == 36
    for key, value in ids.items():
        assert row.details[key] == value
    assert row.details["nested"] == {"entryId": saved["id"], "note": "[redacted]"}
    assert row.details["listed"] == [saved["id"], "[redacted]"]
    assert row.details["note"] == "[redacted]"
    assert row.details["tokenId"] == digest(raw)
    assert row.actor == "admin@example.com"
    assert raw not in json.dumps(row.details)
    assert [save.details["entryId"] for save in saves] == [saved["id"]]
