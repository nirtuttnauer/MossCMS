import json

from conftest import define, entry, gql
from test_cms import delivery, invited


def enable(client, admin, rules=None):
    response = client.patch(
        "/api/project/permissions", headers=admin, json={"enabled": True, "fieldRules": rules or {}}
    )
    assert response.status_code == 200, response.text


def test_classic_editor_publishes_until_custom_roles_are_enabled(app, client, admin):
    define(client, admin)
    editor, editor_headers, _ = invited(app, client, admin)
    published = entry(editor, editor_headers, status="published")
    assert "errors" not in published, published
    denied = client.post("/api/team/invitations", headers=admin, json={"email": "author@example.com", "role": "author"})
    assert denied.status_code == 422
    assert "custom permissions" in denied.json()["detail"]
    enable(client, admin)
    author, author_headers, _ = invited(app, client, admin, "author", "author@example.com")
    blocked = entry(author, author_headers, "author-draft", status="published")
    assert blocked["errors"][0]["extensions"]["code"] == "FORBIDDEN"
    assert "errors" not in entry(author, author_headers, "author-draft")
    still = client.patch("/api/project/permissions", headers=admin, json={"enabled": False, "fieldRules": {}})
    assert still.status_code == 409


def test_author_cannot_publish_schedule_unpublish_or_trash_live_content(app, client, admin):
    define(client, admin)
    enable(client, admin)
    author, author_headers, _ = invited(app, client, admin, "author", "author@example.com")
    live = entry(client, admin, "live", status="published")["data"]["saveEntry"]
    future = "2099-01-01T00:00:00Z"
    for status, extra in (("published", {}), ("scheduled", {"scheduledAt": future})):
        result = entry(author, author_headers, "live", status=status, id=live["id"], version=live["version"], **extra)
        assert result["errors"][0]["extensions"]["code"] == "FORBIDDEN", result
    unpublish = gql(
        author,
        author_headers,
        "mutation($id:ID!,$version:Int!){unpublishEntry(id:$id,version:$version){id}}",
        live,
    )
    trash = gql(
        author,
        author_headers,
        "mutation($id:ID!,$version:Int!){deleteEntry(id:$id,version:$version)}",
        live,
    )
    assert unpublish["errors"][0]["extensions"]["code"] == "FORBIDDEN"
    assert trash["errors"][0]["extensions"]["code"] == "FORBIDDEN"
    assert gql(client, delivery(client, admin), "{entries{nodes{slug}}}", delivery=True)["data"]["entries"][
        "nodes"
    ] == [{"slug": "live"}]


def test_partial_save_preserves_fields_the_author_cannot_write(app, client, admin):
    fields = [
        {"name": "title", "type": "text", "required": True},
        {"name": "body", "type": "richText"},
        {"name": "note", "type": "text"},
    ]
    define(client, admin, fields=fields)
    enable(client, admin, {"article": {"author": {"read": ["title", "body", "note"], "write": ["title", "body"]}}})
    author, author_headers, _ = invited(app, client, admin, "author", "writer@example.com")
    created = entry(client, admin, "kept", {"title": "Kept", "body": "one", "note": "stored"})["data"]["saveEntry"]
    saved = entry(
        author,
        author_headers,
        "kept",
        {"title": "Kept", "body": "two", "note": None},
        id=created["id"],
        version=created["version"],
    )
    assert "errors" not in saved, saved
    assert saved["data"]["saveEntry"]["data"]["note"] == "stored"
    assert saved["data"]["saveEntry"]["data"]["body"] == "two"


def test_hidden_fields_cannot_be_inferred_from_lists_filters_or_history(app, client, admin):
    fields = [
        {"name": "title", "type": "text", "required": True},
        {"name": "body", "type": "richText"},
        {"name": "related", "type": "reference", "target": "article"},
    ]
    define(client, admin, fields=fields)
    enable(client, admin, {"article": {"author": {"read": ["body"], "write": ["body"]}}})
    author, author_headers, _ = invited(app, client, admin, "author", "limited@example.com")
    secret = "SENTINEL-TITLE"
    created = entry(client, admin, "visible-slug", {"title": secret, "body": "public", "related": None})["data"][
        "saveEntry"
    ]
    visible = gql(
        author,
        author_headers,
        "query($id:ID!){entry(id:$id){title data} revisions(id:$id){snapshot}}",
        {"id": created["id"]},
    )["data"]
    assert visible["entry"]["title"] == "visible-slug"
    assert "title" not in visible["entry"]["data"]
    assert "related" not in visible["entry"]["data"]
    assert secret not in json.dumps(visible)
    listed = gql(author, author_headers, '{entries(typeKey:"article",search:"SENTINEL-TITLE"){total nodes{title}}}')
    assert listed["data"]["entries"]["total"] == 0
    assert secret not in json.dumps(listed)
    filtered = gql(
        author,
        author_headers,
        'query($filters:JSON){entries(typeKey:"article",filters:$filters){total}}',
        {"filters": {"title": secret}},
    )
    ordered = gql(
        author,
        author_headers,
        '{entries(typeKey:"article",orderBy:{field:"title",direction:ASC}){nodes{id}}}',
    )
    assert filtered["errors"][0]["message"] == "Filter on a visible scalar field."
    assert ordered["errors"][0]["message"] == "Filter on a visible scalar field."
    assert secret not in json.dumps(filtered) and secret not in json.dumps(ordered)
    admin_view = gql(client, admin, "query($id:ID!){entry(id:$id){title data}}", {"id": created["id"]})["data"]["entry"]
    assert admin_view["title"] == secret
    assert admin_view["data"]["title"] == secret


def test_field_rules_reject_admin_removal_and_write_without_read(client, admin):
    removed = client.patch(
        "/api/project/permissions",
        headers=admin,
        json={"enabled": True, "fieldRules": {"article": {"admin": {"read": ["title"]}}}},
    )
    unreadable = client.patch(
        "/api/project/permissions",
        headers=admin,
        json={"enabled": True, "fieldRules": {"article": {"author": {"read": ["body"], "write": ["title"]}}}},
    )
    assert removed.status_code == 422 and "administrator" in removed.json()["detail"]
    assert unreadable.status_code == 422 and "readable" in unreadable.json()["detail"]
