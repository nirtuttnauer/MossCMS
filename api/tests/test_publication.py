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


def test_scheduler_publishes_captured_revision_and_keeps_newer_draft(app, client, admin):
    from datetime import timedelta
    from app.models import Entry, now
    from app.content import publish_due

    define(client, admin)
    scheduled = entry(
        client,
        admin,
        "queued",
        {"title": "Queued", "body": "captured"},
        "scheduled",
        scheduledAt=(now() + timedelta(hours=1)).isoformat(),
    )["data"]["saveEntry"]
    later = entry(
        client, admin, "later", {"title": "Later", "body": "draft"}, id=scheduled["id"], version=scheduled["version"]
    )["data"]["saveEntry"]
    with app.state.db.begin() as s:
        s.get(Entry, scheduled["id"]).scheduled_at = now() - timedelta(seconds=1)
    publish_due(app.state.db)
    token = delivery(client, admin)
    node = public(client, token)["entries"]["nodes"][0]
    assert (node["slug"], node["data"]["body"], node["version"]) == ("queued", "captured", scheduled["version"])
    draft = gql(
        client,
        admin,
        "query($id:ID!){entry(id:$id){slug data version scheduledAt hasUnpublishedChanges}}",
        {"id": later["id"]},
    )["data"]["entry"]
    assert draft["slug"] == "later" and draft["data"]["body"] == "draft"
    assert draft["scheduledAt"] is None and draft["hasUnpublishedChanges"]
    publish_due(app.state.db)
    assert public(client, token)["entries"]["nodes"][0] == node


def test_schedule_slug_failure_preserves_live_and_does_not_retry(app, client, admin):
    from datetime import timedelta
    from app.models import Entry, now
    from app.content import publish_due

    define(client, admin)
    live = entry(client, admin, "live", status="published")["data"]["saveEntry"]
    scheduled = entry(
        client,
        admin,
        "collision",
        {"title": "Future"},
        "scheduled",
        id=live["id"],
        version=live["version"],
        scheduledAt=(now() + timedelta(hours=1)).isoformat(),
    )["data"]["saveEntry"]
    entry(client, admin, "moved", id=live["id"], version=scheduled["version"])
    entry(client, admin, "collision", status="published")
    token = delivery(client, admin)
    before = public(client, token)
    with app.state.db.begin() as s:
        s.get(Entry, live["id"]).scheduled_at = now() - timedelta(seconds=1)
    publish_due(app.state.db)
    assert public(client, token) == before
    query = "query($id:ID!){entry(id:$id){version scheduleError scheduledRevision scheduledAt}}"
    failed = gql(client, admin, query, {"id": live["id"]})["data"]["entry"]
    assert failed["scheduleError"]["code"] == "CONFLICT"
    assert failed["scheduleError"]["revision"] == scheduled["version"]
    assert failed["scheduledAt"] is None
    publish_due(app.state.db)
    assert gql(client, admin, query, {"id": live["id"]})["data"]["entry"] == failed


def test_cancel_unpublish_permissions_versions_and_trash(app, client, admin):
    from datetime import timedelta
    from app.models import now
    from test_cms import invited

    define(client, admin)
    live = entry(client, admin, status="published")["data"]["saveEntry"]
    scheduled = entry(
        client,
        admin,
        status="scheduled",
        id=live["id"],
        version=live["version"],
        scheduledAt=(now() + timedelta(hours=1)).isoformat(),
    )["data"]["saveEntry"]
    token = delivery(client, admin)
    before = public(client, token)
    cancel = "mutation($id:ID!,$version:Int!){cancelSchedule(id:$id,version:$version){id version scheduledAt isLive}}"
    unpublish = "mutation($id:ID!,$version:Int!){unpublishEntry(id:$id,version:$version){id version isLive data}}"
    reader, headers, _ = invited(app, client, admin, "reader", "reader@example.com")
    args = {"id": live["id"], "version": scheduled["version"]}
    assert gql(reader, headers, cancel, args)["errors"][0]["extensions"]["code"] == "FORBIDDEN"
    assert "errors" in gql(client, token, unpublish, args, delivery=True)
    assert gql(client, admin, cancel, {**args, "version": 1})["errors"][0]["extensions"]["code"] == "CONFLICT"
    cancelled = gql(client, admin, cancel, args)["data"]["cancelSchedule"]
    assert cancelled["isLive"] and cancelled["scheduledAt"] is None
    assert public(client, token) == before
    unpublished = gql(client, admin, unpublish, {"id": live["id"], "version": cancelled["version"]})["data"][
        "unpublishEntry"
    ]
    assert not unpublished["isLive"] and unpublished["data"]["title"] == "hello"
    assert public(client, token)["entries"]["nodes"] == []
    gql(
        client,
        admin,
        "mutation($id:ID!,$version:Int!){deleteEntry(id:$id,version:$version)}",
        {"id": live["id"], "version": unpublished["version"]},
    )
    trashed = gql(client, admin, "query($id:ID!){entry(id:$id){version}}", {"id": live["id"]})["data"]["entry"]
    assert "errors" in entry(client, admin, id=live["id"], version=trashed["version"])
    restored = gql(
        client,
        admin,
        "mutation($id:ID!,$version:Int!){restoreEntry(id:$id,version:$version,number:1){isLive status}}",
        {"id": live["id"], "version": trashed["version"]},
    )
    assert restored["data"]["restoreEntry"] == {"isLive": False, "status": "draft"}


def test_markdown_assets_resolve_only_visible_scoped_published_content(app, client, admin):
    from app.models import Asset

    define(client, admin)
    with app.state.db.begin() as s:
        for id in ["visible", "private"]:
            s.add(
                Asset(
                    id=id,
                    project_id=admin["x-moss-project"],
                    name=id,
                    key=id,
                    storage="local",
                    mime="image/png",
                    size=1,
                )
            )
    live = entry(
        client,
        admin,
        data={"title": "Post", "body": "![Cover](asset:visible)", "secret": "![Hidden](asset:private)"},
        status="published",
    )["data"]["saveEntry"]
    token = delivery(client, admin)
    query = "{entries{nodes{resolvedAssets{id mime url}}}}"
    assets = public(client, token, query)["entries"]["nodes"][0]["resolvedAssets"]
    assert len(assets) == 1 and assets[0]["id"] == "visible" and "signature=" in assets[0]["url"]
    entry(
        client, admin, data={"title": "Post", "body": "![New](asset:private)"}, id=live["id"], version=live["version"]
    )
    assert public(client, token, query)["entries"]["nodes"][0]["resolvedAssets"][0]["id"] == "visible"
