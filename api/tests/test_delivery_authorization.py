"""REST delivery authorization and workspace isolation.

Collected in both required runs: no postgres marker and no runtime skip.
SQLite uses the temporary database. PostgreSQL uses MOSS_TEST_DATABASE_URL.
"""

import os
import urllib.parse
from datetime import timedelta

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import Asset, Token, now
from app.security import digest
from conftest import database_url, define, drop_test_database, entry, gql
from test_cms import invited

FIELDS = [
    {"name": "title", "type": "text", "required": True},
    {"name": "body", "type": "richText"},
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
UNPUBLISHED = (
    "moss033-draft-title",
    "moss033-draft-body",
    "moss033-draft-slug",
    "moss033-draft-secret",
    "moss033-draft-asset",
    "moss033-sched-title",
    "moss033-sched-body",
    "moss033-sched-slug",
    "moss033-sched-secret",
    "moss033-overlay-draft",
    "moss033-overlay-sched",
    "moss033-trashed-title",
    "moss033-trashed-body",
    "moss033-unpublished-title",
    "moss033-unpublished-body",
    "moss033-draft-post",
    "moss033-draft-post-slug",
    "moss033-sched-post",
    "moss033-draft-page",
    "moss033-b-draft-title",
    "moss033-b-draft-body",
    "moss033-b-sched-title",
    "moss033-b-sched-body",
    "moss033-a-secret",
    "moss033-b-secret",
    "private-asset-name",
)
DENIED = {"detail": "A valid delivery token is required."}


def assert_run_database(app):
    configured = os.environ.get("MOSS_TEST_DATABASE_URL", "")
    expected = "postgresql" if configured.startswith("postgres") else "sqlite"
    assert app.state.engine.dialect.name == expected


def delivery_routes(app):
    routes = [
        route
        for route in app.routes
        if isinstance(route, APIRoute) and "GET" in route.methods and route.path.startswith("/delivery/")
    ]
    assert {route.path for route in routes} == DESIGN_ROUTES
    return sorted(routes, key=lambda route: route.path)


def concrete_path(route, samples):
    path = route.path
    for name in route.param_convertors:
        path = path.replace("{" + name + "}", samples[name])
    return path


def issue(client, headers, scopes=None, name="Website"):
    result = client.post("/api/tokens", headers=headers, json={"name": name, "scopes": scopes or [], "days": 1})
    assert result.status_code == 200, result.text
    raw = result.json()["token"]
    return raw, {"Authorization": "Bearer " + raw}


def expire(app, raw):
    with app.state.db.begin() as session:
        session.get(Token, digest(raw)).expires_at = now() - timedelta(seconds=30)


def revoke(client, headers, raw):
    assert client.delete("/api/tokens/" + digest(raw), headers=headers).status_code == 200


def saved(client, headers, slug, data, status="draft", key="article", **extra):
    result = entry(client, headers, slug, data, status, key, **extra)
    assert "errors" not in result, result
    return result["data"]["saveEntry"]


def later():
    return (now() + timedelta(days=3)).isoformat()


def assert_unpublished(response, extra=()):
    text = response.text
    for marker in (*UNPUBLISHED, *extra):
        assert marker not in text, (marker, response.status_code, response.request.url.path)


def assert_denied(response, method, label=""):
    where = f"{label} {method} {response.request.url.path}".strip()
    assert response.status_code == 401, (where, response.status_code, response.text)
    assert response.headers["cache-control"] == "no-store", where
    assert "etag" not in response.headers, where
    assert response.headers["x-request-id"], where
    if method == "GET":
        assert response.json() == DENIED, where
    assert_unpublished(response)


def hit(probe, method, path, *, cookie=None, headers=None, query=None):
    probe.cookies.clear()
    if cookie:
        probe.cookies.set("moss_session", cookie)
    target = path if query is None else path + "?" + query
    return probe.request(method, target, headers=headers)


def add_asset(session, project_id, asset_id, name):
    session.add(
        Asset(
            id=asset_id,
            project_id=project_id,
            name=name,
            key=asset_id,
            storage="local",
            mime="image/png",
            size=4,
            width=640,
            height=480,
            variants=[{"width": 320, "height": 240, "size": 2}],
        )
    )


def build(app, client, admin):
    define(client, admin, fields=FIELDS)
    define(client, admin, "sitePost", fields=FIELDS)
    define(client, admin, "sitePage", fields=FIELDS)
    onlya = define(client, admin, "onlya", fields=FIELDS)
    project_b = client.post("/api/projects", headers=admin, json={"name": "Other workspace"}).json()
    other = {**admin, "x-moss-project": project_b["id"]}
    article_b = define(client, other, fields=FIELDS)
    define(client, other, "sitePost", fields=FIELDS)
    with app.state.db.begin() as session:
        add_asset(session, admin["x-moss-project"], "moss033-a-cover", "a-cover-name")
        add_asset(session, admin["x-moss-project"], "moss033-private-asset", "private-asset-name")
        add_asset(session, admin["x-moss-project"], "moss033-draft-asset", "draft-asset-name")
        add_asset(session, project_b["id"], "moss033-b-cover", "b-cover-private-name")
    live = saved(
        client,
        admin,
        "a-live",
        {
            "title": "A Live Title",
            "body": "moss033-a-live ![Cover](asset:moss033-a-cover) ![Foreign](asset:moss033-b-cover)",
            "secret": "moss033-a-secret ![Hidden](asset:moss033-private-asset)",
        },
        "published",
    )
    draft = saved(
        client,
        admin,
        "moss033-draft-slug",
        {
            "title": "moss033-draft-title",
            "body": "moss033-draft-body ![Draft](asset:moss033-draft-asset)",
            "secret": "moss033-draft-secret",
        },
    )
    scheduled = saved(
        client,
        admin,
        "moss033-sched-slug",
        {"title": "moss033-sched-title", "body": "moss033-sched-body", "secret": "moss033-sched-secret"},
        "scheduled",
        scheduledAt=later(),
    )
    overlay = saved(
        client,
        admin,
        "a-overlay",
        {"title": "Overlay Live", "body": "moss033-overlay-live", "secret": "overlay-secret"},
        "published",
    )
    overlay = saved(
        client,
        admin,
        "a-overlay",
        {"title": "moss033-overlay-draft", "body": "moss033-overlay-draft", "secret": "overlay-secret"},
        id=overlay["id"],
        version=overlay["version"],
    )
    overlay = saved(
        client,
        admin,
        "a-overlay",
        {"title": "moss033-overlay-sched", "body": "moss033-overlay-sched", "secret": "overlay-secret"},
        "scheduled",
        id=overlay["id"],
        version=overlay["version"],
        scheduledAt=later(),
    )
    trashed = saved(
        client,
        admin,
        "trashed-slug",
        {"title": "moss033-trashed-title", "body": "moss033-trashed-body", "secret": "trashed-secret"},
        "published",
    )
    assert (
        gql(
            client,
            admin,
            "mutation($id:ID!,$version:Int!){deleteEntry(id:$id,version:$version)}",
            {"id": trashed["id"], "version": trashed["version"]},
        )["data"]["deleteEntry"]
        is True
    )
    unpublished = saved(
        client,
        admin,
        "unpublished-slug",
        {"title": "moss033-unpublished-title", "body": "moss033-unpublished-body", "secret": "unpublished-secret"},
        "published",
    )
    assert "errors" not in gql(
        client,
        admin,
        "mutation($id:ID!,$version:Int!){unpublishEntry(id:$id,version:$version){id}}",
        {"id": unpublished["id"], "version": unpublished["version"]},
    )
    post = saved(
        client,
        admin,
        "a-live-post",
        {"title": "A Post", "body": "moss033-a-post", "secret": "post-secret"},
        "published",
        key="sitePost",
    )
    post = saved(
        client,
        admin,
        "a-renamed-post",
        {"title": "A Post", "body": "moss033-a-post", "secret": "post-secret"},
        "published",
        key="sitePost",
        id=post["id"],
        version=post["version"],
    )
    post = saved(
        client,
        admin,
        "moss033-draft-post-slug",
        {"title": "moss033-draft-post", "body": "moss033-draft-post", "secret": "post-secret"},
        key="sitePost",
        id=post["id"],
        version=post["version"],
    )
    page = saved(
        client,
        admin,
        "about",
        {"title": "About", "body": "moss033-about", "secret": "page-secret"},
        "published",
        key="sitePage",
    )
    draft_post = saved(
        client,
        admin,
        "moss033-draft-post",
        {"title": "moss033-draft-post", "body": "moss033-draft-post", "secret": "draft-post-secret"},
        key="sitePost",
    )
    scheduled_post = saved(
        client,
        admin,
        "moss033-sched-post",
        {"title": "moss033-sched-post", "body": "moss033-sched-post", "secret": "sched-post-secret"},
        "scheduled",
        key="sitePost",
        scheduledAt=later(),
    )
    draft_page = saved(
        client,
        admin,
        "moss033-draft-page",
        {"title": "moss033-draft-page", "body": "moss033-draft-page", "secret": "draft-page-secret"},
        key="sitePage",
    )
    other_live = saved(
        client,
        other,
        "b-live",
        {
            "title": "B Live Title",
            "body": "moss033-b-live ![Cover](asset:moss033-b-cover)",
            "secret": "moss033-b-secret",
        },
        "published",
    )
    other_draft = saved(
        client,
        other,
        "b-draft",
        {"title": "moss033-b-draft-title", "body": "moss033-b-draft-body", "secret": "moss033-b-secret"},
    )
    other_scheduled = saved(
        client,
        other,
        "b-scheduled",
        {"title": "moss033-b-sched-title", "body": "moss033-b-sched-body", "secret": "moss033-b-secret"},
        "scheduled",
        scheduledAt=later(),
    )
    other_post = saved(
        client,
        other,
        "b-live-post",
        {"title": "B Post", "body": "moss033-b-post", "secret": "b-post-secret"},
        "published",
        key="sitePost",
    )
    tokens = {
        "a-open": issue(client, admin, name="A open")[1],
        "a-article": issue(client, admin, ["article"], "A article")[1],
        "a-site": issue(client, admin, ["sitePost"], "A site")[1],
        "a-onlya": issue(client, admin, ["onlya"], "A onlya")[1],
        "b-open": issue(client, other, name="B open")[1],
        "b-article": issue(client, other, ["article"], "B article")[1],
    }
    raw_expired, expired = issue(client, admin, name="A expired")
    expire(app, raw_expired)
    raw_revoked, revoked = issue(client, admin, name="A revoked")
    revoke(client, admin, raw_revoked)
    tokens["expired"] = expired
    tokens["revoked"] = revoked
    hidden = {
        draft["id"],
        scheduled["id"],
        trashed["id"],
        unpublished["id"],
        draft_post["id"],
        scheduled_post["id"],
        draft_page["id"],
        other_draft["id"],
        other_scheduled["id"],
    }
    return {
        "project_a": admin["x-moss-project"],
        "project_b": project_b["id"],
        "onlya_id": onlya["id"],
        "article_b_id": article_b["id"],
        "article_a_id": client.get("/delivery/types/article", headers=tokens["a-open"]).json()["id"],
        "live": live["id"],
        "overlay": overlay["id"],
        "post": post["id"],
        "page": page["id"],
        "other_live": other_live["id"],
        "other_post": other_post["id"],
        "hidden": hidden,
        "tokens": tokens,
        "a_visible": {live["id"], overlay["id"], post["id"], page["id"]},
        "b_visible": {other_live["id"], other_post["id"]},
    }


def route_paths(app, live_id):
    samples = {"typeKey": "article", "id": live_id}
    paths = [(route.path, concrete_path(route, samples)) for route in delivery_routes(app)]
    assert {path for _, path in paths} == {
        "/delivery/types",
        "/delivery/types/article",
        "/delivery/entries",
        "/delivery/entries/" + live_id,
        "/delivery/entries/" + live_id + "/resolved-assets",
        "/delivery/website/redirects",
        "/delivery/website/reserved-paths",
    }
    return paths


def test_unauthenticated_and_unprivileged_tokens_are_rejected_on_every_route(app, client, admin):
    assert_run_database(app)
    define(client, admin, fields=FIELDS)
    live = saved(
        client,
        admin,
        "auth-live",
        {"title": "Auth Live", "body": "moss033-auth-body", "secret": "moss033-auth-secret"},
        "published",
    )
    raw_open, _ = issue(client, admin, name="open")
    raw_expired, expired = issue(client, admin, name="expired")
    expire(app, raw_expired)
    raw_revoked, revoked = issue(client, admin, name="revoked")
    revoke(client, admin, raw_revoked)
    reader, _, _ = invited(app, client, admin, "reader", "reader-moss033@example.com")
    editor, _, _ = invited(app, client, admin, "editor", "editor-moss033@example.com")
    admin_cookie = client.cookies.get("moss_session")
    reader_cookie = reader.cookies.get("moss_session")
    editor_cookie = editor.cookies.get("moss_session")
    assert admin_cookie and reader_cookie and editor_cookie
    cases = [
        ("no-credential", None, None, None),
        ("admin-cookie", admin_cookie, None, None),
        ("reader-cookie", reader_cookie, None, None),
        ("editor-cookie", editor_cookie, None, None),
        ("admin-bearer", None, {"Authorization": "Bearer " + admin_cookie}, None),
        ("reader-bearer", None, {"Authorization": "Bearer " + reader_cookie}, None),
        ("editor-bearer", None, {"Authorization": "Bearer " + editor_cookie}, None),
        ("expired-bearer", None, expired, None),
        ("revoked-bearer", None, revoked, None),
        ("garbage-bearer", None, {"Authorization": "Bearer not-a-real-token"}, None),
        ("empty-bearer", None, {"Authorization": "Bearer "}, None),
        ("raw-without-scheme", None, {"Authorization": raw_open}, None),
        ("query-token", None, None, urllib.parse.urlencode({"token": raw_open})),
        ("query-access-token", None, None, urllib.parse.urlencode({"access_token": raw_open})),
        ("query-moss-session", None, None, urllib.parse.urlencode({"moss_session": raw_open})),
    ]
    paths = route_paths(app, live["id"])
    probe = TestClient(app)
    for label, cookie, headers, query in cases:
        for template, path in paths:
            for method in ("GET", "HEAD"):
                response = hit(probe, method, path, cookie=cookie, headers=headers, query=query)
                sent = response.request.headers.get("authorization")
                assert sent == (None if headers is None else headers["Authorization"]), label
                assert_denied(response, method, label + " " + template)
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                response = hit(probe, method, path, cookie=cookie, headers=headers, query=query)
                assert response.status_code in {401, 405}, (label, method, template, response.status_code)
                assert "moss033-auth-secret" not in response.text
                assert "moss033-auth-body" not in response.text


def ids_of(response):
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["hasNextPage"] is False
    return {node["id"] for node in body["nodes"]}


def assert_missing(response, detail):
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == detail
    assert response.json()["code"] == "NOT_FOUND"
    assert "etag" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    assert_unpublished(response)


def test_wrong_project_and_scoped_tokens_stay_inside_their_workspace(app, client, admin):
    assert_run_database(app)
    world = build(app, client, admin)
    tokens = world["tokens"]
    paths = dict(route_paths(app, world["live"]))
    probe = TestClient(app)
    a_forbidden = ("moss033-b-live", "moss033-b-post", "b-cover-private-name", world["article_b_id"])
    b_forbidden = (
        "moss033-a-live",
        "moss033-overlay-live",
        "moss033-a-post",
        "moss033-about",
        "a-cover-name",
        world["article_a_id"],
        world["onlya_id"],
    )

    def get(token, path, **headers):
        return hit(probe, "GET", path, headers={**token, **headers})

    for name in ("a-open", "a-article"):
        listed = get(tokens[name], paths["/delivery/entries"])
        assert ids_of(listed) == (world["a_visible"] if name == "a-open" else {world["live"], world["overlay"]})
        assert_unpublished(listed, a_forbidden)
    assert ids_of(get(tokens["a-site"], paths["/delivery/entries"])) == {world["post"]}
    assert ids_of(get(tokens["a-onlya"], paths["/delivery/entries"])) == set()
    for name in ("b-open", "b-article"):
        listed = get(tokens[name], paths["/delivery/entries"])
        expected = world["b_visible"] if name == "b-open" else {world["other_live"]}
        assert ids_of(listed) == expected
        assert_unpublished(listed, b_forbidden)

    for name in ("a-open", "a-article"):
        document = get(tokens[name], paths["/delivery/entries/{id}"])
        assert document.status_code == 200, document.text
        assert document.json()["status"] == "published"
        assert document.json()["data"]["body"].startswith("moss033-a-live")
        assert document.json()["scheduledAt"] is None
        assert document.json()["hasUnpublishedChanges"] is False
        assert "secret" not in document.json()["data"]
        assert_unpublished(document, a_forbidden)
        assets = get(tokens[name], paths["/delivery/entries/{id}/resolved-assets"])
        assert assets.status_code == 200, assets.text
        assert [row["id"] for row in assets.json()] == ["moss033-a-cover"]
        assert assets.headers["cache-control"] == "no-store"
        assert "etag" not in assets.headers
        assert_unpublished(assets, ("b-cover-private-name", "private-asset-name", "draft-asset-name"))
    for name in ("a-site", "a-onlya", "b-open", "b-article"):
        detail = "Entry not found." if name.startswith("b-") else "Content type not found."
        assert_missing(get(tokens[name], paths["/delivery/entries/{id}"]), detail)
        assert_missing(get(tokens[name], paths["/delivery/entries/{id}/resolved-assets"]), detail)

    overlay = get(tokens["a-open"], "/delivery/entries/" + world["overlay"])
    assert overlay.status_code == 200, overlay.text
    assert overlay.json()["data"]["body"] == "moss033-overlay-live"
    assert overlay.json()["title"] == "Overlay Live"
    assert overlay.json()["status"] == "published"
    assert overlay.json()["scheduledAt"] is None
    assert_unpublished(overlay, a_forbidden)

    expected_keys = {
        "a-open": {"article", "onlya", "sitePage", "sitePost"},
        "a-article": {"article"},
        "a-site": {"sitePost"},
        "a-onlya": {"onlya"},
        "b-open": {"article", "sitePost"},
        "b-article": {"article"},
    }
    for name, keys in expected_keys.items():
        types = get(tokens[name], paths["/delivery/types"])
        assert types.status_code == 200, types.text
        assert {row["key"] for row in types.json()} == keys
        forbidden = b_forbidden if name.startswith("b-") else a_forbidden
        assert_unpublished(types, forbidden)
        if name.startswith("a-"):
            assert world["article_b_id"] not in {row["id"] for row in types.json()}
        else:
            assert world["article_a_id"] not in {row["id"] for row in types.json()}
    for name in ("a-open", "a-article"):
        one = get(tokens[name], paths["/delivery/types/{typeKey}"])
        assert one.status_code == 200 and one.json()["id"] == world["article_a_id"]
    for name in ("b-open", "b-article"):
        one = get(tokens[name], paths["/delivery/types/{typeKey}"])
        assert one.status_code == 200 and one.json()["id"] == world["article_b_id"]
        assert_unpublished(one, b_forbidden)
    for name in ("a-site", "a-onlya"):
        assert_missing(get(tokens[name], paths["/delivery/types/{typeKey}"]), "Content type not found.")
    onlya_path = "/delivery/types/onlya"
    for name in ("a-open", "a-onlya"):
        assert get(tokens[name], onlya_path).json()["id"] == world["onlya_id"]
    for name in ("a-article", "a-site", "b-open", "b-article"):
        assert_missing(get(tokens[name], onlya_path), "Content type not found.")

    a_redirects = get(tokens["a-open"], paths["/delivery/website/redirects"])
    assert a_redirects.json() == [{"from": "/blog/a-live-post", "to": "/blog/a-renamed-post", "entryId": world["post"]}]
    assert_unpublished(a_redirects, a_forbidden)
    assert get(tokens["a-site"], paths["/delivery/website/redirects"]).json() == a_redirects.json()
    for name in ("a-article", "a-onlya"):
        assert get(tokens[name], paths["/delivery/website/redirects"]).json() == []
    b_redirects = get(tokens["b-open"], paths["/delivery/website/redirects"])
    assert b_redirects.json() == []
    assert_unpublished(b_redirects, b_forbidden)
    reserved = get(tokens["a-open"], paths["/delivery/website/reserved-paths"])
    assert reserved.json() == ["/about", "/blog/a-live-post", "/blog/a-renamed-post"]
    assert_unpublished(reserved, a_forbidden)
    assert get(tokens["a-site"], paths["/delivery/website/reserved-paths"]).json() == [
        "/blog/a-live-post",
        "/blog/a-renamed-post",
    ]
    assert get(tokens["a-article"], paths["/delivery/website/reserved-paths"]).json() == []
    assert get(tokens["a-onlya"], paths["/delivery/website/reserved-paths"]).json() == []
    assert get(tokens["b-open"], paths["/delivery/website/reserved-paths"]).json() == ["/blog/b-live-post"]

    for template, path in route_paths(app, world["live"]):
        for method in ("GET", "HEAD"):
            own = hit(probe, method, path, headers=tokens["b-open"])
            retargeted = hit(probe, method, path, headers={**tokens["b-open"], "x-moss-project": world["project_a"]})
            assert retargeted.status_code == own.status_code, template
            if "resolved-assets" not in template and method == "GET":
                assert retargeted.json() == own.json(), template
            home = hit(probe, method, path, headers=tokens["a-open"])
            swapped = hit(probe, method, path, headers={**tokens["a-open"], "x-moss-project": world["project_b"]})
            assert swapped.status_code == home.status_code, template
            if "resolved-assets" not in template and method == "GET":
                assert swapped.json() == home.json(), template
            if method == "GET":
                assert_unpublished(retargeted, b_forbidden)
                assert_unpublished(swapped, a_forbidden)
            else:
                assert_unpublished(retargeted)
                assert_unpublished(swapped)


def test_drafts_and_scheduled_items_are_hidden_from_every_delivery_token(app, client, admin):
    assert_run_database(app)
    world = build(app, client, admin)
    tokens = world["tokens"]
    probe = TestClient(app)
    live_tokens = ["a-open", "a-article", "a-site", "a-onlya", "b-open", "b-article"]
    for name in live_tokens:
        for entry_id in world["hidden"]:
            for suffix in ("", "/resolved-assets"):
                response = hit(probe, "GET", "/delivery/entries/" + entry_id + suffix, headers=tokens[name])
                assert_missing(response, "Entry not found.")
                head = hit(probe, "HEAD", "/delivery/entries/" + entry_id + suffix, headers=tokens[name])
                assert head.status_code == 404
                assert_unpublished(head)
        listed = hit(probe, "GET", "/delivery/entries", headers=tokens[name])
        assert world["hidden"].isdisjoint(ids_of(listed))
        assert_unpublished(listed)
        for marker in (
            "moss033-draft-title",
            "moss033-sched-title",
            "moss033-overlay-draft",
            "moss033-overlay-sched",
            "moss033-trashed-title",
            "moss033-unpublished-title",
            "moss033-draft-post-slug",
            "moss033-b-draft-title",
            "moss033-b-sched-title",
        ):
            found = hit(
                probe,
                "GET",
                "/delivery/entries",
                headers=tokens[name],
                query=urllib.parse.urlencode({"search": marker}),
            )
            if found.status_code == 200:
                assert found.json()["nodes"] == []
            else:
                assert found.status_code == 404
            assert_unpublished(found)
        for param in ("status", "snapshot", "scheduledAt"):
            rejected = hit(
                probe,
                "GET",
                "/delivery/entries",
                headers=tokens[name],
                query=urllib.parse.urlencode({param: "draft" if param == "status" else "scheduled"}),
            )
            assert rejected.status_code == 422, (name, param, rejected.text)
            assert rejected.json()["detail"] == "Unknown delivery parameter."
            assert_unpublished(rejected)
    for name in ("expired", "revoked"):
        response = hit(probe, "GET", "/delivery/entries/" + next(iter(world["hidden"])), headers=tokens[name])
        assert_denied(response, "GET")
        listed = hit(probe, "GET", "/delivery/entries", headers=tokens[name])
        assert_denied(listed, "GET")


def test_skip_auth_still_requires_a_delivery_token_on_every_route(tmp_path):
    url = database_url(tmp_path)
    try:
        application = create_app(
            Settings(
                skip_auth=True,
                secret="s" * 40,
                setup_token="t" * 30,
                database_url=url,
                storage_dir=tmp_path / "media",
            )
        )
        assert_run_database(application)
        with TestClient(application) as local:
            account = local.get("/auth/me").json()
            headers = {"x-moss-project": account["projects"][0]["id"], "x-moss-csrf": account["csrf"]}
            define(local, headers, fields=FIELDS)
            marker = "moss033-skip-" + "field"
            live = saved(
                local,
                headers,
                "skip-live",
                {"title": "Skip Live", "body": "moss033-skip-live", "secret": marker},
                "published",
            )
            draft = saved(
                local,
                headers,
                "moss033-skip-draft",
                {"title": "moss033-skip-draft", "body": "moss033-skip-draft", "secret": marker},
            )
            _, token = issue(local, headers, name="skip")
            samples = {"typeKey": "article", "id": live["id"]}
            for route in delivery_routes(application):
                path = concrete_path(route, samples)
                for method in ("GET", "HEAD"):
                    rejected = hit(local, method, path)
                    assert_denied(rejected, method)
                    assert marker not in rejected.text
                    accepted = hit(local, method, path, headers=token)
                    assert accepted.status_code == 200, (method, path, accepted.text)
            hidden = hit(local, "GET", "/delivery/entries/" + draft["id"], headers=token)
            assert_missing(hidden, "Entry not found.")
            listed = hit(local, "GET", "/delivery/entries", headers=token)
            assert ids_of(listed) == {live["id"]}
            assert_unpublished(listed, ("moss033-skip-draft", marker))
    finally:
        drop_test_database(url)
