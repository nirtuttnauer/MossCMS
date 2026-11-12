"""Delivery REST reads match delivery GraphQL and keep its auth and cache rules."""

import json
import urllib.parse
from datetime import timedelta
from unittest.mock import patch

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.config import Settings
from app.content import publish_due
from app.delivery_rest import MAX_FILTERS_BYTES, delivery_etag
from app.main import create_app
from app.models import Asset, Entry, now
from conftest import define, entry, gql
from test_cms import delivery

ENTRY_FIELDS = (
    "id typeKey slug title data status version updatedAt scheduledAt isLive "
    "hasUnpublishedChanges publishedAt publishedRevision scheduledRevision scheduleError "
    "publishedData publishedSlug publishedTitle publishedSnapshot"
)
ENTRIES = (
    "query($typeKey:String,$search:String,$sort:String,$first:Int!,$after:String,$filters:JSON,"
    "$orderBy:EntryOrderBy){entries(typeKey:$typeKey,search:$search,sort:$sort,first:$first,after:$after,"
    f"filters:$filters,orderBy:$orderBy){{nodes{{{ENTRY_FIELDS}}} endCursor hasNextPage}}}}"
)
ENTRIES_TOTAL = ENTRIES.replace("hasNextPage}}", "hasNextPage total}}")
ARTICLE = [
    {"name": "title", "type": "text", "required": True},
    {"name": "body", "type": "richText"},
    {"name": "rank", "type": "number"},
    {"name": "featured", "type": "boolean"},
    {
        "name": "address",
        "type": "object",
        "fields": [
            {"name": "city", "type": "text"},
            {"name": "internal", "type": "text", "private": True},
        ],
    },
    {"name": "secret", "type": "text", "private": True},
]
DESIGN_ROUTES = {
    "/delivery/types",
    "/delivery/types/{typeKey}",
    "/delivery/entries",
    "/delivery/entries/{id}",
    "/delivery/entries/{id}/resolved-assets",
    "/delivery/website/redirects",
    "/delivery/website/reserved-paths",
}


def delivery_rest_gets(app):
    """REST GET routes registered on the app. GraphQL stays POST-only."""
    return sorted(
        (
            route
            for route in app.routes
            if isinstance(route, APIRoute) and "GET" in route.methods and route.path.startswith("/delivery/")
        ),
        key=lambda route: route.path,
    )


def concrete_path(route, samples):
    path = route.path
    for name in route.param_convertors:
        if name not in samples:
            raise AssertionError(f"no sample value for {{{name}}} on {route.path}")
        path = path.replace("{" + name + "}", samples[name])
    return path


def raw_get(client, path, query: bytes, headers):
    """Send query_string bytes without letting the HTTP client encode them again."""
    captured = {}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
            captured["headers"] = {key.decode().lower(): value.decode() for key, value in message["headers"]}
            captured["body"] = b""
        elif message["type"] == "http.response.body":
            captured["body"] += message.get("body", b"")

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": query,
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "state": {},
        "extensions": {"http.response.debug": {}},
    }

    async def run():
        await client.app(scope, receive, send)

    client.portal.call(run)
    return captured


def filters_json(size: int) -> bytes:
    prefix, suffix = b'{"body":"', b'"}'
    filler = size - len(prefix) - len(suffix)
    assert filler >= 0
    return prefix + b"a" * filler + suffix


def assert_same_entries(client, token, *, total=False, order_by=None, **params):
    query_params = {}
    for key, value in params.items():
        if value is not None:
            query_params[key] = json.dumps(value, separators=(",", ":")) if key == "filters" else value
    if order_by:
        query_params["orderBy"] = order_by["field"]
        query_params["direction"] = order_by["direction"]
    if total:
        query_params["total"] = "true"
    rest = client.get("/delivery/entries", headers=token, params=query_params)
    assert rest.status_code == 200, rest.text
    variables = {
        "typeKey": params.get("typeKey"),
        "search": params.get("search") or "",
        "sort": params.get("sort") or "updated_desc",
        "first": int(params["first"]) if params.get("first") else 20,
        "after": params.get("after"),
        "filters": params.get("filters"),
        "orderBy": {"field": order_by["field"], "direction": order_by["direction"].upper()} if order_by else None,
    }
    result = gql(client, token, ENTRIES_TOTAL if total else ENTRIES, variables, delivery=True)
    assert "errors" not in result, result
    assert rest.json() == result["data"]["entries"]
    return rest


def test_rest_returns_the_same_data_as_delivery_graphql(app, client, admin):
    define(client, admin, fields=ARTICLE)
    define(
        client,
        admin,
        "sitePost",
        fields=[{"name": "title", "type": "text", "required": True}, {"name": "body", "type": "richText"}],
    )
    with app.state.db.begin() as session:
        for asset_id in ("visible", "private"):
            session.add(
                Asset(
                    id=asset_id,
                    project_id=admin["x-moss-project"],
                    name=asset_id,
                    key=asset_id,
                    storage="local",
                    mime="image/png",
                    size=4,
                    width=640,
                    height=480,
                    variants=[{"width": 320, "height": 240, "size": 2}],
                )
            )
    alpha = {
        "title": "Alpha",
        "body": "![Cover](asset:visible)",
        "rank": 2,
        "featured": True,
        "address": {"city": "Tel Aviv", "internal": "hidden"},
        "secret": "![Hidden](asset:private)",
    }
    published = entry(client, admin, "alpha", alpha, "published")["data"]["saveEntry"]
    entry(client, admin, "beta", {**alpha, "title": "Beta", "rank": 1, "featured": False}, "published")
    post = entry(client, admin, "old-post", {"title": "Old", "body": "text"}, "published", key="sitePost")["data"][
        "saveEntry"
    ]
    assert "errors" not in entry(
        client,
        admin,
        "new-post",
        {"title": "New", "body": "text"},
        "published",
        key="sitePost",
        id=post["id"],
        version=post["version"],
    )
    token = delivery(client, admin)
    types = client.get("/delivery/types", headers=token)
    assert types.status_code == 200, types.text
    graphql_types = gql(client, token, "{contentTypes{id key name fields version}}", delivery=True)
    assert types.json() == graphql_types["data"]["contentTypes"]
    one = client.get("/delivery/types/article", headers=token)
    assert one.status_code == 200, one.text
    assert one.json() == next(row for row in types.json() if row["key"] == "article")
    assert "internal" not in json.dumps(one.json()["fields"])
    listed = assert_same_entries(client, token, total=True)
    assert listed.json()["total"] == 3
    article = next(node for node in listed.json()["nodes"] if node["typeKey"] == "article" and node["slug"] == "alpha")
    assert "secret" not in article["data"]
    assert article["data"]["address"] == {"city": "Tel Aviv"}
    assert "signature=" not in listed.text and "expires=" not in listed.text
    assert "signature=" not in types.text
    assert_same_entries(client, token, typeKey="article", search="Alpha", total=True)
    assert_same_entries(client, token, typeKey="article", sort="title_asc", first="2")
    assert_same_entries(client, token, typeKey="article", filters={"rank": 2, "featured": True})
    ordered = assert_same_entries(client, token, typeKey="article", order_by={"field": "rank", "direction": "asc"})
    assert [node["slug"] for node in ordered.json()["nodes"]] == ["beta", "alpha"]
    page = assert_same_entries(client, token, typeKey="article", sort="title_asc", first="1")
    assert page.json()["hasNextPage"] is True
    assert_same_entries(client, token, typeKey="article", sort="title_asc", first="1", after=page.json()["endCursor"])
    single = client.get("/delivery/entries/" + published["id"], headers=token)
    assert single.status_code == 200, single.text
    result = gql(
        client,
        token,
        f"query($id:ID!){{entry(id:$id){{{ENTRY_FIELDS}}}}}",
        {"id": published["id"]},
        delivery=True,
    )
    assert single.json() == result["data"]["entry"]
    assert single.headers["etag"] == delivery_etag(single.json())
    graphql_response = client.post("/delivery/graphql", json={"query": "{contentTypes{key}}"}, headers=token)
    assert graphql_response.headers["etag"] == delivery_etag(graphql_response.json())
    website = gql(client, token, "{websiteRedirects websiteReservedPaths}", delivery=True)["data"]
    assert client.get("/delivery/website/redirects", headers=token).json() == website["websiteRedirects"]
    assert client.get("/delivery/website/reserved-paths", headers=token).json() == website["websiteReservedPaths"]
    assert website["websiteRedirects"] == [{"from": "/blog/old-post", "to": "/blog/new-post", "entryId": post["id"]}]
    with patch("app.media_links.time.time", return_value=1_700_000_000):
        assets = client.get(f"/delivery/entries/{published['id']}/resolved-assets", headers=token)
        query = "query($id:ID!){entry(id:$id){resolvedAssets{id name mime size url width height variants}}}"
        expected = gql(client, token, query, {"id": published["id"]}, delivery=True)["data"]["entry"]["resolvedAssets"]
    assert assets.status_code == 200, assets.text
    assert assets.json() == expected
    assert assets.json()[0]["id"] == "visible" and "signature=" in assets.json()[0]["url"]
    assert "etag" not in assets.headers
    assert assets.headers["cache-control"] == "no-store"
    again = client.get(
        f"/delivery/entries/{published['id']}/resolved-assets",
        headers={**token, "if-none-match": '"anything"'},
    )
    assert again.status_code == 200 and "etag" not in again.headers


def test_session_cookie_without_bearer_is_401_on_every_delivery_rest_get(client, admin):
    define(client, admin)
    published = entry(client, admin, status="published")["data"]["saveEntry"]
    token = delivery(client, admin)
    routes = delivery_rest_gets(client.app)
    assert [route.path for route in routes] == sorted(DESIGN_ROUTES)
    assert client.cookies.get("moss_session")
    me = client.get("/auth/me")
    assert me.status_code == 200 and me.json()["user"]["email"] == "admin@example.com"
    session = client.cookies.get("moss_session")
    client.cookies.clear()
    assert client.get("/auth/me").status_code == 401
    client.cookies.set("moss_session", session)
    assert client.get("/auth/me").status_code == 200
    assert client.get("/api/tokens", headers=admin).status_code == 200
    samples = {"typeKey": "article", "id": published["id"]}
    for route in routes:
        path = concrete_path(route, samples)
        rejected = client.get(path)
        assert rejected.request.headers.get("authorization") is None
        assert rejected.status_code == 401
        assert rejected.json() == {"detail": "A valid delivery token is required."}
        assert rejected.headers["cache-control"] == "no-store"
        assert "etag" not in rejected.headers
        assert rejected.headers["x-request-id"]
        accepted = client.get(path, headers=token)
        assert accepted.request.headers["authorization"].startswith("Bearer ")
        assert accepted.status_code == 200, path + " " + accepted.text


def test_filters_limit_uses_raw_bytes_before_decoding_and_parsing(client, admin, monkeypatch):
    import app.delivery_rest as delivery_rest

    define(client, admin)
    entry(client, admin, status="published")
    token = delivery(client, admin)
    assert MAX_FILTERS_BYTES == 4096
    parsed, measured = [], []
    original_parse = delivery_rest.parse_filters
    original_length = delivery_rest.filters_measured_length

    def spy_parse(value):
        parsed.append(value)
        return original_parse(value)

    def spy_length(raw):
        measured.append(bytes(raw))
        return original_length(raw)

    monkeypatch.setattr(delivery_rest, "parse_filters", spy_parse)
    monkeypatch.setattr(delivery_rest, "filters_measured_length", spy_length)

    def send(raw: bytes):
        parsed.clear()
        measured.clear()
        response = raw_get(client, "/delivery/entries", b"typeKey=article&filters=" + raw, token)
        return response

    exact = filters_json(4096)
    assert len(exact) == 4096
    allowed = send(exact)
    assert allowed["status"] == 200, allowed["body"]
    assert parsed == [exact.decode()]
    assert json.loads(allowed["body"])["nodes"] == []
    allowed_measured = list(measured)

    oversized = filters_json(4097)
    assert len(oversized) == 4097
    rejected = send(oversized)
    assert rejected["status"] == 422, (rejected["body"], parsed)
    assert parsed == []
    rejected_measured = list(measured)

    decoded = filters_json(1366)
    encoded = b"".join(b"%%%02X" % byte for byte in decoded)
    assert len(encoded) == 4098
    assert len(urllib.parse.unquote_to_bytes(encoded)) == 1366
    assert 1366 < 4096 < len(encoded)
    hidden = send(encoded)
    assert hidden["status"] == 422, hidden["body"]
    assert parsed == []
    assert json.loads(hidden["body"])["detail"] == "Filters value is too long."
    hidden_measured = list(measured)

    assert allowed_measured == [exact]
    assert rejected_measured == [oversized]
    assert hidden_measured == [encoded]


def test_skip_auth_still_requires_a_delivery_token(tmp_path):
    application = create_app(
        Settings(
            skip_auth=True,
            secret="s" * 40,
            setup_token="t" * 30,
            database_url=f"sqlite:///{tmp_path}/skip.db",
            storage_dir=tmp_path / "media",
        )
    )
    with TestClient(application) as local:
        assert local.get("/auth/me").status_code == 200
        assert local.get("/delivery/entries").status_code == 401
        account = local.get("/auth/me").json()
        headers = {"x-moss-project": account["projects"][0]["id"], "x-moss-csrf": account["csrf"]}
        define(local, headers)
        entry(local, headers, status="published")
        token = delivery(local, headers)
        assert local.get("/delivery/entries", headers=token).status_code == 200
        assert local.get("/delivery/entries").status_code == 401


def test_scopes_drafts_and_scheduled_entries_follow_delivery_rules(client, admin):
    define(client, admin)
    define(client, admin, "other")
    draft = entry(client, admin, "draft-only")["data"]["saveEntry"]
    live = entry(client, admin, "live", status="published")["data"]["saveEntry"]
    scheduled = entry(
        client,
        admin,
        "later",
        status="scheduled",
        scheduledAt=(now() + timedelta(days=1)).isoformat(),
    )["data"]["saveEntry"]
    outside = entry(client, admin, "outside", key="other", status="published")["data"]["saveEntry"]
    scoped = delivery(client, admin, ["article"])
    open_token = delivery(client, admin)
    assert_same_entries(client, scoped, total=True)
    assert [node["id"] for node in client.get("/delivery/entries", headers=scoped).json()["nodes"]] == [live["id"]]
    assert client.get("/delivery/entries/" + draft["id"], headers=scoped).status_code == 404
    assert client.get("/delivery/entries/" + scheduled["id"], headers=scoped).status_code == 404
    hidden = client.get("/delivery/entries/" + outside["id"], headers=scoped)
    assert hidden.status_code == 404
    assert hidden.json()["detail"] == "Content type not found."
    assert hidden.json()["code"] == "NOT_FOUND"
    assert "etag" not in hidden.headers
    assert [row["key"] for row in client.get("/delivery/types", headers=scoped).json()] == ["article"]
    assert {row["key"] for row in client.get("/delivery/types", headers=open_token).json()} == {"article", "other"}
    missing_type = client.get("/delivery/entries", headers=scoped, params={"typeKey": "other"})
    assert missing_type.status_code == 404
    assert missing_type.json()["detail"] == "Content type not found."
    listed = client.get("/delivery/entries", headers=open_token).json()
    assert {node["id"] for node in listed["nodes"]} == {live["id"], outside["id"]}
    assert client.get("/delivery/entries/" + live["id"], headers=scoped).json()["status"] == "published"


def test_draft_edits_and_failed_schedules_do_not_change_the_etag(app, client, admin):
    define(client, admin)
    live = entry(client, admin, "live", {"title": "Live", "body": "published", "secret": "hidden"}, "published")[
        "data"
    ]["saveEntry"]
    token = delivery(client, admin)
    before = client.get("/delivery/entries/" + live["id"], headers=token)
    list_before = client.get("/delivery/entries", headers=token)
    edited = entry(
        client,
        admin,
        "changed",
        {"title": "Changed", "body": "draft"},
        id=live["id"],
        version=live["version"],
    )["data"]["saveEntry"]
    after = client.get("/delivery/entries/" + live["id"], headers=token)
    assert after.json() == before.json()
    assert after.headers["etag"] == before.headers["etag"]
    assert client.get("/delivery/entries", headers=token).headers["etag"] == list_before.headers["etag"]
    scheduled = entry(
        client,
        admin,
        "collision",
        {"title": "Future"},
        "scheduled",
        id=live["id"],
        version=edited["version"],
        scheduledAt=(now() + timedelta(hours=1)).isoformat(),
    )["data"]["saveEntry"]
    entry(client, admin, "moved", id=live["id"], version=scheduled["version"])
    entry(client, admin, "collision", status="published")
    with app.state.db.begin() as session:
        session.get(Entry, live["id"]).scheduled_at = now() - timedelta(seconds=1)
    publish_due(app.state.db)
    failed = client.get("/delivery/entries/" + live["id"], headers=token)
    assert failed.json() == before.json()
    assert failed.headers["etag"] == before.headers["etag"]
    assert failed.json()["scheduleError"] is None
    assert failed.json()["hasUnpublishedChanges"] is False


def test_private_title_and_nested_fields_match_graphql(client, admin):
    define(
        client,
        admin,
        "note",
        fields=[
            {"name": "title", "type": "text", "required": True, "private": True},
            {"name": "body", "type": "richText"},
            {
                "name": "address",
                "type": "object",
                "fields": [
                    {"name": "city", "type": "text"},
                    {"name": "internal", "type": "text", "private": True},
                ],
            },
        ],
    )
    saved = entry(
        client,
        admin,
        "visible-slug",
        {"title": "Hidden Title", "body": "shown", "address": {"city": "Haifa", "internal": "secret"}},
        "published",
        key="note",
    )["data"]["saveEntry"]
    token = delivery(client, admin)
    document = client.get("/delivery/entries/" + saved["id"], headers=token)
    result = gql(
        client,
        token,
        f"query($id:ID!){{entry(id:$id){{{ENTRY_FIELDS}}}}}",
        {"id": saved["id"]},
        delivery=True,
    )
    assert document.json() == result["data"]["entry"]
    assert document.json()["title"] == "visible-slug"
    assert "title" not in document.json()["data"]
    assert document.json()["data"]["address"] == {"city": "Haifa"}
    hidden = assert_same_entries(client, token, typeKey="note", search="Hidden", total=True)
    assert hidden.json()["total"] == 0
    assert_same_entries(client, token, typeKey="note", search="visible-slug", sort="title_asc", total=True)


def test_cursors_order_and_totals_use_the_published_index(client, admin):
    define(client, admin, fields=ARTICLE)
    first = entry(client, admin, "low", {"title": "Low", "rank": 1, "body": "a"}, "published")["data"]["saveEntry"]
    second = entry(client, admin, "high", {"title": "High", "rank": 2, "body": "b"}, "published")["data"]["saveEntry"]
    token = delivery(client, admin)
    ordered = assert_same_entries(client, token, typeKey="article", order_by={"field": "rank", "direction": "desc"})
    assert [node["id"] for node in ordered.json()["nodes"]] == [second["id"], first["id"]]
    entry(
        client,
        admin,
        "low",
        {"title": "Low", "rank": 9, "body": "a"},
        id=first["id"],
        version=first["version"],
    )
    assert_same_entries(client, token, typeKey="article", order_by={"field": "rank", "direction": "desc"})
    plain = client.get("/delivery/entries", headers=token, params={"typeKey": "article"})
    assert "total" not in plain.json() and "totalQuery" not in plain.json()
    counted = client.get("/delivery/entries", headers=token, params={"typeKey": "article", "total": "true"})
    assert counted.json()["total"] == 2
    long_cursor = "x" * 1001
    rejected = client.get("/delivery/entries", headers=token, params={"after": long_cursor})
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == "Invalid page cursor."
    huge = b"x" * (1024 * 1024 + 1)
    ordered_cursor = raw_get(client, "/delivery/entries", b"typeKey=article&orderBy=rank&after=" + huge, token)
    assert ordered_cursor["status"] == 422
    assert json.loads(ordered_cursor["body"])["detail"] == "Invalid page cursor."


def test_cache_validation_errors_and_api_prefix(client, admin):
    define(client, admin)
    published = entry(client, admin, status="published")["data"]["saveEntry"]
    token = delivery(client, admin)
    listed = client.get("/delivery/entries", headers=token)
    graphql_listed = client.post("/delivery/graphql", json={"query": "{entries{nodes{id}}}"}, headers=token)
    assert listed.headers["cache-control"] == "private, no-cache"
    assert listed.headers["vary"] == graphql_listed.headers["vary"]
    assert "Authorization" in listed.headers["vary"] and "Origin" in listed.headers["vary"]
    assert listed.headers["etag"] == delivery_etag(listed.json())
    cached = client.get("/delivery/entries", headers={**token, "if-none-match": listed.headers["etag"]})
    assert cached.status_code == 304
    assert cached.content == b""
    assert "content-type" not in cached.headers
    assert cached.headers["etag"] == listed.headers["etag"]
    assert cached.headers["cache-control"] == "private, no-cache"
    assert cached.headers["x-request-id"]
    head = client.head("/delivery/entries", headers=token)
    assert head.status_code == 200
    assert head.content == b""
    assert head.headers["etag"] == listed.headers["etag"]
    head_cached = client.head("/delivery/entries", headers={**token, "if-none-match": listed.headers["etag"]})
    assert head_cached.status_code == 304 and head_cached.content == b""
    assert client.get("/delivery/entries", headers={**token, "if-none-match": "*"}).status_code == 200
    weak = "W/" + listed.headers["etag"]
    assert client.get("/delivery/entries", headers={**token, "if-none-match": weak}).status_code == 200
    item = client.get("/delivery/entries/" + published["id"], headers=token)
    item_cached = client.get(
        "/delivery/entries/" + published["id"], headers={**token, "if-none-match": item.headers["etag"]}
    )
    assert item_cached.status_code == 304 and item_cached.content == b""
    empty = client.get("/delivery/entries", headers=token, params={"search": "missing-title"})
    assert empty.status_code == 200 and empty.json()["nodes"] == [] and empty.headers["etag"]
    missing = client.get("/delivery/entries/missing", headers=token)
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Entry not found."
    assert "etag" not in missing.headers
    assert missing.headers["cache-control"] == "no-store"
    unknown = client.get("/delivery/types", headers=token, params={"resolvedAssets": "1"})
    assert unknown.status_code == 422
    assert unknown.json() == {"detail": "Unknown delivery parameter.", "code": "VALIDATION"}
    status = client.get("/delivery/entries", headers=token, params={"status": "draft"})
    assert status.status_code == 422 and status.json()["detail"] == "Unknown delivery parameter."
    page = client.get("/delivery/entries", headers=token, params={"first": "abc"})
    assert page.status_code == 422
    assert page.json()["detail"] == "Use a page size of 1–100 and a supported sort order."
    assert client.post("/delivery/entries", headers=token).status_code == 405
    assert client.delete("/delivery/entries/" + published["id"], headers=token).status_code == 405
    for route in client.app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api"):
            assert not path.startswith("/api/delivery")
            assert "resolved-assets" not in path
    assert client.get("/api/delivery/entries", headers=token).status_code == 404
    admin_list = client.get("/api/tokens", headers=admin)
    assert admin_list.headers["cache-control"] == "no-store"
    assert "etag" not in admin_list.headers
