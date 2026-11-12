from datetime import timedelta

from sqlalchemy import select

from app.content import publish_due
from app.models import Entry, PublicationEvent, now
from conftest import define, entry, gql
from test_cms import delivery, invited


def review(client, headers, version=1, required=True):
    result = gql(
        client,
        headers,
        'mutation($version:Int!,$required:Boolean!){setReviewRequired(key:"article",required:$required,version:$version){key}}',
        {"version": version, "required": required},
    )
    assert "errors" not in result, result


def submit(client, headers, record, reviewer):
    result = gql(
        client,
        headers,
        "mutation($id:ID!,$version:Int!,$reviewer:ID!){submitForReview(id:$id,version:$version,reviewerId:$reviewer){id version reviewState}}",
        {"id": record["id"], "version": record["version"], "reviewer": reviewer},
    )
    assert "errors" not in result, result
    return result["data"]["submitForReview"]


def approve(client, headers, record):
    result = gql(
        client,
        headers,
        "mutation($id:ID!,$version:Int!){approveEntry(id:$id,version:$version){id version reviewState approvedRevision}}",
        record,
    )
    assert "errors" not in result, result
    return result["data"]["approveEntry"]


def test_review_stays_off_until_a_type_opts_in(client, admin):
    defined = define(client, admin)
    published = entry(client, admin, status="published")
    assert "errors" not in published, published
    review(client, admin, defined["version"])
    blocked = entry(client, admin, "second", status="published")
    assert "approval" in blocked["errors"][0]["message"]
    assert gql(client, delivery(client, admin), "{entries{total}}", delivery=True)["data"]["entries"]["total"] == 1


def test_publish_schedule_and_worker_require_another_persons_approval(app, client, admin):
    defined = define(client, admin)
    review(client, admin, defined["version"])
    editor, editor_headers, editor_id = invited(app, client, admin)
    draft = entry(client, admin, "story", {"title": "Story", "body": "Live", "secret": "x"}, status="published")
    assert "approval" in draft["errors"][0]["message"]
    draft = entry(client, admin, "story", {"title": "Story", "body": "Live", "secret": "x"})["data"]["saveEntry"]
    me = client.get("/auth/me").json()["user"]["id"]
    own = gql(
        client,
        admin,
        "mutation($id:ID!,$version:Int!,$reviewer:ID!){submitForReview(id:$id,version:$version,reviewerId:$reviewer){id}}",
        {"id": draft["id"], "version": draft["version"], "reviewer": me},
    )
    assert "different reviewer" in own["errors"][0]["message"]
    submitted = submit(client, admin, draft, editor_id)
    approved = approve(editor, editor_headers, submitted)
    published = entry(
        client,
        admin,
        "story",
        {"title": "Story", "body": "Live", "secret": "x"},
        "published",
        id=approved["id"],
        version=approved["version"],
    )["data"]["saveEntry"]
    changed = entry(
        client,
        admin,
        "story",
        {"title": "Story", "body": "Changed", "secret": "x"},
        id=published["id"],
        version=published["version"],
    )["data"]["saveEntry"]
    assert (
        gql(client, admin, "query($id:ID!){entry(id:$id){reviewState}}", {"id": changed["id"]})["data"]["entry"][
            "reviewState"
        ]
        == "draft"
    )
    refused = entry(
        client,
        admin,
        "story",
        {"title": "Story", "body": "Changed", "secret": "x"},
        "scheduled",
        id=changed["id"],
        version=changed["version"],
        scheduledAt="2099-01-02T00:00:00Z",
    )
    assert "approval" in refused["errors"][0]["message"]
    submitted = submit(client, admin, changed, editor_id)
    approved = approve(editor, editor_headers, submitted)
    scheduled = entry(
        client,
        admin,
        "story",
        {"title": "Story", "body": "Changed", "secret": "x"},
        "scheduled",
        id=approved["id"],
        version=approved["version"],
        scheduledAt="2099-01-02T00:00:00Z",
    )["data"]["saveEntry"]
    newer = entry(
        client,
        admin,
        "story",
        {"title": "Story", "body": "Newer", "secret": "x"},
        id=scheduled["id"],
        version=scheduled["version"],
    )["data"]["saveEntry"]
    with app.state.db.begin() as session:
        session.get(Entry, newer["id"]).scheduled_at = now() - timedelta(seconds=1)
    publish_due(app.state.db)
    with app.state.db() as session:
        record = session.get(Entry, newer["id"])
        assert record.published_data["body"] == "Live"
        assert "no longer approved" in record.schedule_error["message"]
        assert "Live content was preserved" in record.schedule_error["message"]
    token = delivery(client, admin)
    assert gql(client, token, "{allCmsArticle{body}}", delivery=True)["data"]["allCmsArticle"][0]["body"] == "Live"


def test_schema_change_clears_approval_and_author_cannot_restore_live(app, client, admin):
    defined = define(client, admin)
    review(client, admin, defined["version"])
    editor, editor_headers, editor_id = invited(app, client, admin)
    client.patch("/api/project/permissions", headers=admin, json={"enabled": True, "fieldRules": {}})
    author, author_headers, _ = invited(app, client, admin, "author", "author@example.com")
    draft = entry(author, author_headers, "restore-me")["data"]["saveEntry"]
    submitted = submit(author, author_headers, draft, editor_id)
    approved = approve(editor, editor_headers, submitted)
    migrated = gql(
        client,
        admin,
        'mutation($fields:JSON!,$version:Int!){saveContentType(key:"article",name:"article",fields:$fields,version:$version){version}}',
        {
            "fields": [
                {"name": "title", "type": "text", "required": True},
                {"name": "body", "type": "richText"},
                {"name": "secret", "type": "text", "private": True},
                {"name": "note", "type": "text"},
            ],
            "version": defined["version"],
        },
    )
    assert "errors" not in migrated, migrated
    current = gql(client, admin, "query($id:ID!){entry(id:$id){version reviewState}}", {"id": approved["id"]})["data"][
        "entry"
    ]
    assert current["reviewState"] == "draft"
    blocked = entry(
        client,
        admin,
        "restore-me",
        {"title": "restore-me", "body": "text", "secret": "hidden", "note": ""},
        "published",
        id=approved["id"],
        version=current["version"],
    )
    assert "approval" in blocked["errors"][0]["message"]
    restored = gql(
        author,
        author_headers,
        "mutation($id:ID!,$version:Int!){restoreEntry(id:$id,version:$version,number:1){status}}",
        {"id": approved["id"], "version": current["version"]},
    )
    assert "errors" not in restored, restored
    assert restored["data"]["restoreEntry"]["status"] == "draft"
    assert gql(client, delivery(client, admin), "{entries{total}}", delivery=True)["data"]["entries"]["total"] == 0


def test_author_cannot_import_and_imported_entries_stay_unapproved(app, client, admin):
    defined = define(client, admin)
    review(client, admin, defined["version"])
    entry(client, admin, "imported-source", status="draft")
    client.patch("/api/project/permissions", headers=admin, json={"enabled": True, "fieldRules": {}})
    author, author_headers, _ = invited(app, client, admin, "author", "importer@example.com")
    denied = author.post("/api/migration/export", headers=author_headers)
    assert denied.status_code == 403
    exported = client.post("/api/migration/export", headers=admin, data={"history": "true", "includePrivate": "true"})
    assert exported.status_code == 200, exported.text
    created = client.post("/api/projects", headers=admin, json={"name": "Import target"})
    assert created.status_code == 200, created.text
    target = {**admin, "x-moss-project": created.json()["id"]}
    archive = ("workspace.zip", exported.content, "application/zip")
    checked = client.post(
        "/api/migration/import",
        headers=target,
        files={"file": archive},
        data={"apply": "false", "pipeline": "{}"},
    )
    assert checked.status_code == 200, checked.text
    applied = client.post(
        "/api/migration/import",
        headers=target,
        files={"file": ("workspace.zip", exported.content, "application/zip")},
        data={"apply": "true", "pipeline": "{}", "validation": checked.json()["validation"]},
    )
    assert applied.status_code == 200, applied.text
    rows = gql(client, target, "{entries{nodes{status reviewState approvedRevision}}}")["data"]["entries"]["nodes"]
    assert rows and all(row["status"] == "draft" and row["approvedRevision"] is None for row in rows)
    with app.state.db() as session:
        stored = session.scalars(select(Entry).where(Entry.project_id == target["x-moss-project"])).all()
        assert stored and all(record.review_state == "draft" and record.approved_revision is None for record in stored)
        assert (
            session.scalars(
                select(PublicationEvent).where(PublicationEvent.project_id == target["x-moss-project"])
            ).all()
            == []
        )
