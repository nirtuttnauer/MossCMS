"""Stdio MCP reads published entries for a delivery token."""

import io
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import mcp
from app.models import Token, now
from app.security import digest
from conftest import define, entry

API_DIR = Path(__file__).resolve().parents[1]
FIELDS = [
    {"name": "title", "type": "text", "required": True},
    {"name": "body", "type": "richText"},
    {"name": "secret", "type": "text", "private": True},
]
PUBLISHED_TITLE = "שָׁלוֹם עוֹלָם"
PUBLISHED_BODY = "בְּרֵאשִׁית\nבָּרָא אֱלֹהִים"
DRAFT_TITLE = "טְיוּטָה נִסְתֶּרֶת"
DRAFT_BODY = "לֹא לְפַרְסֵם"
SCHEDULED_TITLE = "מְתֻזְמָן נִסְתָּר"
SCHEDULED_BODY = "עֲתִידִי נִסְתָּר"
LIVE_TITLE = "שָׁלוֹם קַיָּם"
LIVE_BODY = "גּוּף מְפֻרְסָם"
OVERLAY_DRAFT_TITLE = "טְיוּטָה מְאוּחֶרֶת"
OVERLAY_DRAFT_BODY = "גּוּף טְיוּטָה"
OVERLAY_SCHED_TITLE = "תִּזְמוּן מְאוּחָר"
OVERLAY_SCHED_BODY = "גּוּף מְתֻזְמָן"
SECOND_TITLE = "אַלְפָּא"
SECOND_BODY = "עַמּוּד"
OTHER_TITLE = "פּרוֹיֶקְט אַחֵר"
OTHER_BODY = "תּוֹכֶן אַחֵר"
NOTE_TITLE = "הֶעָרָה"
NOTE_BODY = "גּוּף הֶעָרָה"
SECRET = "סוֹד-פרטי-שלא-יוצא"
HIDDEN = (
    DRAFT_TITLE,
    DRAFT_BODY,
    SCHEDULED_TITLE,
    SCHEDULED_BODY,
    OVERLAY_DRAFT_TITLE,
    OVERLAY_DRAFT_BODY,
    OVERLAY_SCHED_TITLE,
    OVERLAY_SCHED_BODY,
    SECRET,
)


def later():
    return (now() + timedelta(days=3)).isoformat()


def article(title, body):
    return {"title": title, "body": body, "secret": SECRET}


def saved(client, headers, slug, data, status="draft", key="article", **extra):
    result = entry(client, headers, slug, data, status, key, **extra)
    if "errors" in result:
        raise AssertionError("entry save failed")
    return result["data"]["saveEntry"]


def issue(client, headers, scopes=None):
    result = client.post("/api/tokens", headers=headers, json={"name": "Website", "scopes": scopes or [], "days": 1})
    if result.status_code != 200:
        raise AssertionError(f"token create failed with status {result.status_code}")
    body = result.json()
    if "token" not in body:
        raise AssertionError(f"token create failed with status {result.status_code}")
    return body["token"]


def assert_token_absent(blob, secret):
    if secret and secret in blob:
        raise AssertionError("raw delivery token appeared in MCP output")


def assert_unpublished(blob):
    for marker in HIDDEN:
        if marker in blob:
            raise AssertionError("unpublished entry text was returned")


def point_at(monkeypatch, app, token="", project=None, skip_auth=False):
    monkeypatch.setenv("DATABASE_URL", app.state.settings.database_url)
    monkeypatch.setenv("MOSS_USE_SQLITE", "false")
    monkeypatch.setenv("MOSS_ENV", "development")
    monkeypatch.setenv("MOSS_SKIP_AUTH", "true" if skip_auth else "false")
    monkeypatch.setenv("MOSS_DELIVERY_TOKEN", token)
    if project is None:
        monkeypatch.delenv("MOSS_PROJECT", raising=False)
    else:
        monkeypatch.setenv("MOSS_PROJECT", project)


def speak(monkeypatch, app, messages, token="", project=None, skip_auth=False):
    point_at(monkeypatch, app, token, project, skip_auth)
    raw_in = "".join(json.dumps(message, ensure_ascii=False) + "\n" for message in messages)
    stdout = io.StringIO()
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr)
    mcp.serve(io.StringIO(raw_in), stdout)
    text = stdout.getvalue()
    err = stderr.getvalue()
    assert_token_absent(text, token)
    assert_token_absent(err, token)
    parsed = [json.loads(line) for line in text.splitlines() if line.strip()]
    return parsed, text, err


def handshake(protocol="2025-06-18"):
    return [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": protocol,
                "capabilities": {},
                "clientInfo": {"name": "moss-test", "version": "0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]


def call(name, arguments=None, request_id=3):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }


def decoded(message):
    result = message["result"]
    text = result["content"][0]["text"]
    if result.get("isError"):
        assert "structuredContent" not in result
        return text
    parsed = json.loads(text)
    assert parsed == result["structuredContent"]
    return parsed


def bearer(token):
    return {"Authorization": "Bearer " + token}


def build(client, admin):
    define(client, admin, fields=FIELDS)
    define(client, admin, "note", fields=FIELDS)
    published = saved(client, admin, "shalom", article(PUBLISHED_TITLE, PUBLISHED_BODY), "published")
    saved(client, admin, "draft-hidden", article(DRAFT_TITLE, DRAFT_BODY))
    saved(client, admin, "sched-hidden", article(SCHEDULED_TITLE, SCHEDULED_BODY), "scheduled", scheduledAt=later())
    overlay = saved(client, admin, "overlay", article(LIVE_TITLE, LIVE_BODY), "published")
    overlay = saved(
        client,
        admin,
        "overlay",
        article(OVERLAY_DRAFT_TITLE, OVERLAY_DRAFT_BODY),
        id=overlay["id"],
        version=overlay["version"],
    )
    overlay = saved(
        client,
        admin,
        "overlay",
        article(OVERLAY_SCHED_TITLE, OVERLAY_SCHED_BODY),
        "scheduled",
        id=overlay["id"],
        version=overlay["version"],
        scheduledAt=later(),
    )
    second = saved(client, admin, "alpha", article(SECOND_TITLE, SECOND_BODY), "published")
    saved(client, admin, "note-hidden", article(NOTE_TITLE, NOTE_BODY), "published", key="note")
    other = client.post("/api/projects", headers=admin, json={"name": "Other"}).json()
    other_headers = {**admin, "x-moss-project": other["id"]}
    define(client, other_headers, fields=FIELDS)
    foreign = saved(client, other_headers, "foreign", article(OTHER_TITLE, OTHER_BODY), "published")
    token = issue(client, admin)
    scoped = issue(client, admin, ["article"])
    foreign_token = issue(client, other_headers)
    session_token = client.cookies.get("moss_session")
    if not session_token:
        raise AssertionError("session cookie was not set")
    return {
        "published": published,
        "overlay": overlay,
        "second": second,
        "foreign": foreign,
        "other_project": other["id"],
        "token": token,
        "scoped": scoped,
        "foreign_token": foreign_token,
        "session_token": session_token,
    }


def test_lists_and_gets_published_entries_with_hebrew_intact(monkeypatch, app, client, admin):
    built = build(client, admin)
    token = built["token"]
    messages = [
        *handshake("2024-11-05"),
        call(mcp.LIST_TOOL, {}, 3),
        call(mcp.GET_TOOL, {"id": built["published"]["id"]}, 4),
        call(mcp.GET_TOOL, {"id": built["overlay"]["id"]}, 5),
        call(mcp.GET_TOOL, {"id": built["published"]["id"] + "-missing"}, 6),
        call(mcp.LIST_TOOL, {"first": 1, "typeKey": "article"}, 7),
        call(mcp.LIST_TOOL, {"search": "shalom", "sort": "title_asc"}, 8),
        call(mcp.LIST_TOOL, {"projectId": admin["x-moss-project"]}, 9),
    ]
    parsed, text, _err = speak(monkeypatch, app, messages, token)
    assert [item["id"] for item in parsed] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert parsed[0]["result"]["protocolVersion"] == "2024-11-05"
    names = [tool["name"] for tool in parsed[1]["result"]["tools"]]
    assert names == [mcp.LIST_TOOL, mcp.GET_TOOL]
    assert all(tool["annotations"]["readOnlyHint"] is True for tool in parsed[1]["result"]["tools"])
    listed = decoded(parsed[2])
    rest = client.get("/delivery/entries", headers=bearer(token))
    assert rest.status_code == 200
    assert listed == rest.json()
    titles = {node["title"] for node in listed["nodes"]}
    assert titles == {PUBLISHED_TITLE, LIVE_TITLE, SECOND_TITLE, NOTE_TITLE}
    published = next(node for node in listed["nodes"] if node["id"] == built["published"]["id"])
    assert published["title"] == PUBLISHED_TITLE
    assert published["data"]["body"] == PUBLISHED_BODY
    assert published["data"]["title"] == PUBLISHED_TITLE
    assert "secret" not in published["data"]
    assert published["status"] == "published"
    assert published["scheduledAt"] is None
    got = decoded(parsed[3])
    single = client.get("/delivery/entries/" + built["published"]["id"], headers=bearer(token))
    assert single.status_code == 200
    assert got == single.json()
    assert got["title"] == PUBLISHED_TITLE
    assert got["data"]["body"] == PUBLISHED_BODY
    live = decoded(parsed[4])
    assert live["title"] == LIVE_TITLE
    assert live["data"]["body"] == LIVE_BODY
    assert live["status"] == "published"
    assert decoded(parsed[5]) == "Entry not found."
    page = decoded(parsed[6])
    rest_page = client.get("/delivery/entries", headers=bearer(token), params={"first": 1, "typeKey": "article"})
    assert rest_page.status_code == 200
    assert page == rest_page.json()
    assert page["hasNextPage"] is True
    assert len(page["nodes"]) == 1
    found = decoded(parsed[7])
    rest_found = client.get(
        "/delivery/entries", headers=bearer(token), params={"search": "shalom", "sort": "title_asc"}
    )
    assert found == rest_found.json()
    assert {node["title"] for node in found["nodes"]} == {PUBLISHED_TITLE}
    pinned = decoded(parsed[8])
    assert pinned == listed
    assert OTHER_TITLE not in text
    assert_unpublished(text)
    assert PUBLISHED_TITLE.encode("utf-8") in text.encode("utf-8")
    assert text.count("\n") == len(parsed)


def test_bad_tokens_fail_closed(monkeypatch, app, client, admin):
    built = build(client, admin)
    published_id = built["published"]["id"]
    foreign_id = built["foreign"]["id"]

    def attempt(token, project=None, skip_auth=False, arguments=None):
        parsed, text, err = speak(
            monkeypatch,
            app,
            [
                *handshake(),
                call(mcp.GET_TOOL, {"id": published_id, **(arguments or {})}, 3),
                call(mcp.LIST_TOOL, arguments or {}, 4),
            ],
            token,
            project,
            skip_auth,
        )
        assert decoded(parsed[2]) == mcp.AUTH_MESSAGE
        assert decoded(parsed[3]) == mcp.AUTH_MESSAGE
        assert parsed[2]["result"]["isError"] is True
        assert PUBLISHED_TITLE not in text
        assert OTHER_TITLE not in text
        assert_unpublished(text)
        assert_token_absent(err, token)
        return text

    attempt("")
    attempt("   ")
    attempt("x" * 5000)
    attempt(built["session_token"])
    attempt(built["token"], project=built["other_project"])
    attempt(built["foreign_token"], project=admin["x-moss-project"])
    attempt(built["token"], arguments={"projectId": built["other_project"]})
    attempt(built["token"], skip_auth=True, arguments={"projectId": built["other_project"]})
    attempt("", skip_auth=True)

    with app.state.db.begin() as session:
        session.get(Token, digest(built["scoped"])).expires_at = now() - timedelta(seconds=30)
    attempt(built["scoped"])

    with app.state.db.begin() as session:
        session.get(Token, digest(built["foreign_token"])).kind = "draft"
    attempt(built["foreign_token"])

    assert client.delete("/api/tokens/" + digest(built["token"]), headers=admin).status_code == 200
    attempt(built["token"])

    fresh = issue(client, admin)
    parsed, text, _err = speak(
        monkeypatch,
        app,
        [*handshake(), call(mcp.GET_TOOL, {"id": foreign_id}, 3), call(mcp.LIST_TOOL, {}, 4)],
        fresh,
    )
    assert decoded(parsed[2]) == "Entry not found."
    titles = {node["title"] for node in decoded(parsed[3])["nodes"]}
    assert OTHER_TITLE not in titles
    assert PUBLISHED_TITLE in titles
    assert_unpublished(text)

    skipped, skipped_text, _err = speak(
        monkeypatch,
        app,
        [*handshake(), call(mcp.LIST_TOOL, {}, 3)],
        fresh,
        skip_auth=True,
    )
    assert {node["title"] for node in decoded(skipped[2])["nodes"]} == titles
    assert_unpublished(skipped_text)


def test_scope_rejects_mutations_and_keeps_the_published_snapshot(monkeypatch, app, client, admin):
    built = build(client, admin)
    before = client.get("/delivery/entries/" + built["published"]["id"], headers=bearer(built["scoped"]))
    assert before.status_code == 200
    parsed, text, _err = speak(
        monkeypatch,
        app,
        [
            *handshake(),
            call(mcp.LIST_TOOL, {"typeKey": "note"}, 3),
            call(mcp.GET_TOOL, {"id": built["published"]["id"]}, 4),
            call("save_entry", {"id": built["published"]["id"], "data": article("changed", "changed")}, 5),
            call(mcp.LIST_TOOL, {"status": "draft"}, 6),
            call(mcp.LIST_TOOL, {"typeKey": "article"}, 7),
        ],
        built["scoped"],
    )
    assert decoded(parsed[2]) == "Content type not found."
    assert decoded(parsed[3])["title"] == PUBLISHED_TITLE
    assert decoded(parsed[3])["data"]["body"] == PUBLISHED_BODY
    assert SECRET not in text
    assert NOTE_TITLE not in text
    assert decoded(parsed[4]) == "Unknown tool."
    assert decoded(parsed[5]) == "Unknown parameter."
    scoped_titles = {node["title"] for node in decoded(parsed[6])["nodes"]}
    assert NOTE_TITLE not in scoped_titles
    assert PUBLISHED_TITLE in scoped_titles
    assert LIVE_TITLE in scoped_titles
    after = client.get("/delivery/entries/" + built["published"]["id"], headers=bearer(built["scoped"]))
    assert after.json() == before.json()
    assert_unpublished(text)


def test_reader_rejects_writes(monkeypatch, app):
    point_at(monkeypatch, app)
    engine, factory, url = mcp.connect()
    try:
        with pytest.raises(DBAPIError):
            with factory() as session:
                mcp.lock_reader(session, url)
                session.execute(text("CREATE TABLE mcp_probe (id INTEGER)"))
    finally:
        engine.dispose()


def test_log_line_redacts_the_raw_token():
    secret = "delivery-token-value-not-real"
    mcp.configure_logging(secret)
    buffer = io.StringIO()
    mcp.LOG.handlers[0].setStream(buffer)
    mcp.LOG.info("saw %s", secret)
    rendered = buffer.getvalue()
    assert secret not in rendered
    assert "[redacted]" in rendered
    assert mcp.redact(f"prefix {secret} suffix", secret) == "prefix [redacted] suffix"


def test_module_entry_and_rejected_argv(monkeypatch, app, client, admin):
    built = build(client, admin)
    token = built["token"]
    messages = handshake() + [call(mcp.GET_TOOL, {"id": built["published"]["id"]}, 3)]
    payload = "".join(json.dumps(message, ensure_ascii=False) + "\n" for message in messages)
    env = os.environ.copy()
    env["DATABASE_URL"] = app.state.settings.database_url
    env["MOSS_USE_SQLITE"] = "false"
    env["MOSS_ENV"] = "development"
    env["MOSS_SKIP_AUTH"] = "false"
    env["MOSS_DELIVERY_TOKEN"] = token
    env.pop("MOSS_PROJECT", None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(API_DIR)
    proc = subprocess.run(
        [sys.executable, "-m", "app.mcp"],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=API_DIR,
        env=env,
        timeout=30,
        check=False,
    )
    assert_token_absent(proc.stdout, token)
    assert_token_absent(proc.stderr, token)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr.replace(token, "[redacted]"))
    lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    assert decoded(lines[2])["title"] == PUBLISHED_TITLE
    assert decoded(lines[2])["data"]["body"] == PUBLISHED_BODY
    assert_unpublished(proc.stdout)
    assert "mcp method=tools/call tool=get_published_entry result=ok" in proc.stderr

    rejected = subprocess.run(
        [sys.executable, "-m", "app.mcp", "not-a-logged-token"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=API_DIR,
        env=env,
        timeout=20,
        check=False,
    )
    assert rejected.returncode == 2
    assert "not-a-logged-token" not in rejected.stdout
    assert "not-a-logged-token" not in rejected.stderr
    assert_token_absent(rejected.stdout, token)
    assert_token_absent(rejected.stderr, token)
    assert "MOSS_DELIVERY_TOKEN" in rejected.stderr


def test_handle_reports_protocol_and_unknown_methods():
    old = mcp.handle(
        {"jsonrpc": "2.0", "id": 7, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}},
        None,
        "",
        "",
        None,
    )
    assert old["result"]["protocolVersion"] == mcp.PROTOCOL_VERSIONS[0]
    listed = mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, None, "", "", None)
    assert [tool["name"] for tool in listed["result"]["tools"]] == [mcp.LIST_TOOL, mcp.GET_TOOL]
    assert mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, None, "", "", None) is None
    unknown = mcp.handle({"jsonrpc": "2.0", "id": 9, "method": "resources/list"}, None, "", "", None)
    assert unknown["error"]["code"] == -32601
    broken = mcp.handle(["batch"], None, "", "", None)
    assert broken["error"]["code"] == -32600
    down = mcp.handle(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": mcp.LIST_TOOL, "arguments": {}}},
        None,
        "",
        "",
        None,
    )
    assert down["result"]["isError"] is True
