from datetime import timedelta

from sqlalchemy import select

from app.content import publish_due
from app.models import Entry, PublicationEvent, now
from conftest import define, entry, gql
from test_cms import delivery, invited


def release(client, headers, name="Launch"):
    result = gql(client, headers, "mutation($name:String!){createRelease(name:$name)}", {"name": name})
    assert "errors" not in result, result
    return result["data"]["createRelease"]


def add(client, headers, bundle, record, action="publish"):
    result = gql(
        client,
        headers,
        "mutation($id:ID!,$entry:ID!,$action:String!,$version:Int!){addReleaseEntry(id:$id,entryId:$entry,action:$action,version:$version)}",
        {"id": bundle["id"], "entry": record["id"], "action": action, "version": bundle["version"]},
    )
    return result


def publish(client, headers, bundle):
    return gql(
        client,
        headers,
        "mutation($id:ID!,$version:Int!){publishRelease(id:$id,version:$version)}",
        {"id": bundle["id"], "version": bundle["version"]},
    )


def test_release_commits_every_captured_revision_or_none(app, client, admin):
    define(client, admin)
    client.patch("/api/project/permissions", headers=admin, json={"enabled": True, "fieldRules": {}})
    author, author_headers, _ = invited(app, client, admin, "author", "author@example.com")
    denied = gql(author, author_headers, 'mutation{createRelease(name:"Nope")}')
    assert denied["errors"][0]["extensions"]["code"] == "FORBIDDEN"
    first = entry(client, admin, "one", {"title": "One", "body": "captured", "secret": "x"})["data"]["saveEntry"]
    second = entry(client, admin, "two", {"title": "Two", "body": "captured", "secret": "x"})["data"]["saveEntry"]
    bundle = release(client, admin)
    bundle = add(client, admin, bundle, first)["data"]["addReleaseEntry"]
    edited = entry(
        client, admin, "one", {"title": "One", "body": "later", "secret": "x"}, id=first["id"], version=first["version"]
    )["data"]["saveEntry"]
    bundle = add(client, admin, bundle, second)["data"]["addReleaseEntry"]
    published = publish(client, admin, bundle)
    assert "errors" not in published, published
    token = delivery(client, admin)
    live = gql(client, token, '{entries(sort:"title_asc"){nodes{slug data}}}', delivery=True)["data"]["entries"][
        "nodes"
    ]
    assert [item["slug"] for item in live] == ["one", "two"]
    assert live[0]["data"]["body"] == "captured"
    assert edited["data"]["body"] == "later"
    again = publish(client, admin, published["data"]["publishRelease"])
    assert again["errors"]
    with app.state.db() as session:
        events = [
            row.payload
            for row in session.scalars(
                select(PublicationEvent).where(PublicationEvent.project_id == admin["x-moss-project"])
            )
            if row.payload.get("event") == "release.published"
        ]
    assert len(events) == 1
    assert set(events[0]["entryIds"]) == {first["id"], second["id"]}


def test_conflicting_release_preserves_every_live_snapshot(client, admin):
    define(client, admin)
    claimed = entry(client, admin, "claimed", status="published")["data"]["saveEntry"]
    entry(client, admin, "moved", id=claimed["id"], version=claimed["version"])
    colliding = entry(client, admin, "claimed")["data"]["saveEntry"]
    fresh = entry(client, admin, "fresh")["data"]["saveEntry"]
    before = gql(client, delivery(client, admin), "{entries{nodes{slug data}}}", delivery=True)["data"]
    bundle = release(client, admin, "Conflict")
    added = add(client, admin, bundle, colliding)
    assert "errors" not in added, added
    bundle = added["data"]["addReleaseEntry"]
    bundle = add(client, admin, bundle, fresh)["data"]["addReleaseEntry"]
    failed = publish(client, admin, bundle)
    assert "errors" not in failed, failed
    assert failed["data"]["publishRelease"]["status"] == "failed"
    assert "Nothing was published" in failed["data"]["publishRelease"]["error"]["message"]
    assert gql(client, delivery(client, admin), "{entries{nodes{slug data}}}", delivery=True)["data"] == before


def test_schedules_and_open_releases_do_not_overlap(app, client, admin):
    define(client, admin)
    scheduled = entry(client, admin, "queued", status="scheduled", scheduledAt="2099-03-01T00:00:00Z")["data"][
        "saveEntry"
    ]
    bundle = release(client, admin)
    refused = add(client, admin, bundle, scheduled)
    assert "individual schedule" in refused["errors"][0]["message"]
    draft = entry(client, admin, "grouped")["data"]["saveEntry"]
    bundle = add(client, admin, bundle, draft)["data"]["addReleaseEntry"]
    separate = entry(
        client,
        admin,
        "grouped",
        status="scheduled",
        id=draft["id"],
        version=draft["version"],
        scheduledAt="2099-04-01T00:00:00Z",
    )
    assert "open release" in separate["errors"][0]["message"]
    due = entry(client, admin, "due", status="scheduled", scheduledAt="2099-05-01T00:00:00Z")["data"]["saveEntry"]
    with app.state.db.begin() as session:
        session.get(Entry, due["id"]).scheduled_at = now() - timedelta(seconds=1)
    grouped = release(client, admin, "Due together")
    grouped = add(client, admin, grouped, draft)
    assert grouped["errors"]
    scheduled_release = gql(
        client,
        admin,
        "mutation($id:ID!,$version:Int!,$at:String!){scheduleRelease(id:$id,version:$version,scheduledAt:$at)}",
        {"id": bundle["id"], "version": bundle["version"], "at": "2099-06-01T00:00:00Z"},
    )
    assert "errors" not in scheduled_release, scheduled_release
    with app.state.db.begin() as session:
        from app.models import Release

        session.get(Release, bundle["id"]).scheduled_at = now() - timedelta(seconds=1)
    publish_due(app.state.db)
    live = gql(client, delivery(client, admin), "{entries{nodes{slug}}}", delivery=True)
    assert "grouped" in [item["slug"] for item in live["data"]["entries"]["nodes"]]
