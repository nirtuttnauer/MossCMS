from conftest import define, entry, gql
from test_cms import delivery


def public(
    client,
    token,
    query='{entries(sort:"title_asc"){nodes{id slug title data version updatedAt}} allCmsArticle{slug title body}}',
):
    result = gql(client, token, query, delivery=True)
    assert "errors" not in result, result
    return result["data"]


def test_draft_restore_and_conflict_leave_complete_live_snapshot(client, admin):
    define(client, admin)
    original = entry(
        client, admin, "old-url", {"title": "Old title", "body": "Old body", "secret": "hidden"}, "published"
    )["data"]["saveEntry"]
    token = delivery(client, admin)
    before = public(client, token)
    edited = entry(
        client,
        admin,
        "new-url",
        {"title": "New title", "body": "New body"},
        id=original["id"],
        version=original["version"],
    )["data"]["saveEntry"]
    assert public(client, token) == before
    assert public(client, token, '{entries(search:"New title"){total}}')["entries"]["total"] == 0
    assert public(client, token, '{entries(search:"old-url"){total}}')["entries"]["total"] == 1
    restored = gql(
        client,
        admin,
        "mutation($id:ID!,$version:Int!){restoreEntry(id:$id,version:$version,number:1){id version}}",
        edited,
    )["data"]["restoreEntry"]
    assert public(client, token) == before
    assert "errors" in entry(
        client, admin, "new-url", status="published", id=original["id"], version=original["version"]
    )
    assert public(client, token) == before
    published = entry(
        client,
        admin,
        "new-url",
        {"title": "New title", "body": "New body"},
        "published",
        id=original["id"],
        version=restored["version"],
    )
    assert "errors" not in published, published
    after = public(client, token)
    assert after["entries"]["nodes"][0]["slug"] == "new-url"
    assert after["allCmsArticle"][0]["body"] == "New body"
    assert "secret" not in before["entries"]["nodes"][0]["data"]


def test_live_slug_collision_rolls_back_entire_publish(client, admin):
    define(client, admin)
    first = entry(client, admin, "claimed", status="published")["data"]["saveEntry"]
    entry(client, admin, "working", id=first["id"], version=first["version"])
    second = entry(client, admin, "claimed")["data"]["saveEntry"]
    token = delivery(client, admin)
    before = public(client, token)
    result = entry(client, admin, "claimed", status="published", id=second["id"], version=second["version"])
    assert result["errors"][0]["extensions"]["code"] == "CONFLICT"
    assert public(client, token) == before
