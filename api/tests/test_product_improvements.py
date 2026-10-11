from datetime import timedelta

import pytest
from sqlalchemy import MetaData, Table, create_engine, select

from app.content import publish_due
from app.migrate import migrate
from app.models import Entry, WebsitePath, now
from conftest import define, entry, gql
from test_cms import delivery, invited


def test_validation_extensions_locate_nested_list_and_locale_without_changing_values(client, admin):
    fields = [
        {
            "name": "items",
            "type": "list",
            "item": {
                "type": "object",
                "fields": [
                    {"name": "label", "type": "text", "required": True, "localized": True},
                    {"name": "enabled", "type": "boolean", "required": True},
                    {"name": "score", "type": "number", "required": True},
                ],
            },
        }
    ]
    define(client, admin, fields=fields)
    result = entry(client, admin, data={"items": [{"label": {"he": None}, "enabled": False, "score": 0}]})
    error = result["errors"][0]
    assert error["message"] == "data.items[0].label.he is required."
    assert error["extensions"]["fieldPath"] == ["data", "items", 0, "label", "he"]
    assert error["extensions"]["reason"] == "required"
    assert error["extensions"]["code"] == "VALIDATION"
    assert error["extensions"]["requestId"]
    assert gql(client, admin, "{entries{total}}")["data"]["entries"]["total"] == 0
    valid = entry(client, admin, data={"items": [{"label": {"he": ""}, "enabled": False, "score": 0}]})
    assert "errors" not in valid
    slug_error = entry(client, admin, slug="!!!", data={"items": []})["errors"][0]
    assert slug_error["extensions"]["fieldPath"] == ["slug"]
    assert slug_error["extensions"]["reason"] == "invalid_slug"


def test_workspace_locales_are_validated_scoped_admin_only_and_preserve_maps(app, client, admin):
    project_id = admin["x-moss-project"]
    assert client.get("/auth/me").json()["projects"][0]["locales"] == ["en"]
    define(client, admin, fields=[{"name": "title", "type": "text", "localized": True}])
    saved = entry(client, admin, data={"title": {"en": "English", "he": "עברית", "ar": "عربي"}})["data"]["saveEntry"]
    url = f"/api/projects/{project_id}"
    for body in [
        {"defaultLocale": "he", "locales": ["en"]},
        {"defaultLocale": "he", "locales": ["he", "he"]},
        {"defaultLocale": "invalid", "locales": ["invalid"]},
        {"defaultLocale": "en-US", "locales": ["en-US", "en-us"]},
    ]:
        assert client.patch(url, headers=admin, json=body).status_code == 422
    settings = {"defaultLocale": "he", "locales": ["he", "en"]}
    assert client.patch(url, headers=admin, json=settings).status_code == 200
    project = client.get("/auth/me").json()["projects"][0]
    assert project["defaultLocale"] == "he" and project["locales"] == ["he", "en"]
    stored = gql(client, admin, "query($id:ID!){entry(id:$id){data}}", saved)["data"]["entry"]
    assert stored["data"]["title"]["ar"] == "عربي"
    fresh = entry(client, admin, slug="fresh", data={"title": {"en": "English", "he": "עברית"}})["data"]["saveEntry"]
    assert gql(client, admin, "query($id:ID!){entry(id:$id){title}}", fresh)["data"]["entry"]["title"] == "עברית"
    other = client.post("/api/projects", headers=admin, json={"name": "Other"}).json()["id"]
    assert client.patch(f"/api/projects/{other}", headers=admin, json=settings).status_code == 403
    assert next(p for p in client.get("/auth/me").json()["projects"] if p["id"] == other)["defaultLocale"] == "en"
    reader, headers, _ = invited(app, client, admin, "reader", "locale-reader@example.com")
    assert reader.patch(url, headers=headers, json=settings).status_code == 403
    assert client.patch(url, headers={"x-moss-project": project_id}, json=settings).status_code == 403


def save_site(client, admin, key, slug, **extra):
    return entry(client, admin, key=key, slug=slug, data={"title": slug}, **extra)


@pytest.mark.parametrize("key,prefix", [("sitePost", "/blog/"), ("siteProject", "/projects/"), ("sitePage", "/")])
def test_published_url_history_direct_mapping_drafts_unpublish_restore_and_collisions(app, client, admin, key, prefix):
    define(client, admin, key, [{"name": "title", "type": "text"}])
    saved = save_site(client, admin, key, "a", status="published")["data"]["saveEntry"]
    token = delivery(client, admin)
    query = "{websiteRedirects}"
    assert gql(client, token, query, delivery=True)["data"]["websiteRedirects"] == []
    draft = save_site(client, admin, key, "draft-only", id=saved["id"], version=saved["version"])["data"]["saveEntry"]
    assert gql(client, token, query, delivery=True)["data"]["websiteRedirects"] == []
    for slug in ["b", "c"]:
        draft = save_site(client, admin, key, slug, status="published", id=draft["id"], version=draft["version"])[
            "data"
        ]["saveEntry"]
    mappings = gql(client, token, query, delivery=True)["data"]["websiteRedirects"]
    assert mappings == [{"from": prefix + slug, "to": prefix + "c", "entryId": saved["id"]} for slug in ["a", "b"]]
    conflict = save_site(client, admin, key, "a", status="published")
    assert conflict["errors"][0]["extensions"]["reason"] == "website_path_conflict"
    assert conflict["errors"][0]["extensions"]["fieldPath"] == ["slug"]
    assert gql(client, token, query, delivery=True)["data"]["websiteRedirects"] == mappings
    unpublished = gql(
        client, admin, "mutation($id:ID!,$version:Int!){unpublishEntry(id:$id,version:$version){id version}}", draft
    )["data"]["unpublishEntry"]
    assert gql(client, token, query, delivery=True)["data"]["websiteRedirects"] == []
    reserved = gql(client, token, "{websiteReservedPaths}", delivery=True)["data"]["websiteReservedPaths"]
    assert reserved == [prefix + slug for slug in ["a", "b", "c"]]
    assert "draft-only" not in str(reserved)
    assert "errors" in save_site(client, admin, key, "a", status="published")
    live = save_site(client, admin, key, "d", status="published", **unpublished)["data"]["saveEntry"]
    assert all(
        row["to"] == prefix + "d" for row in gql(client, token, query, delivery=True)["data"]["websiteRedirects"]
    )
    gql(client, admin, "mutation($id:ID!,$version:Int!){deleteEntry(id:$id,version:$version)}", live)
    assert gql(client, token, query, delivery=True)["data"]["websiteRedirects"] == []
    with app.state.db() as session:
        paths = session.scalars(select(WebsitePath.path)).all()
        assert prefix + "draft-only" not in paths


def test_scheduler_and_cross_type_home_collision(app, client, admin):
    define(client, admin, "sitePost", [{"name": "title", "type": "text"}])
    define(client, admin, "sitePage", [{"name": "title", "type": "text"}, {"name": "kind", "type": "text"}])
    home = entry(
        client, admin, key="sitePage", slug="welcome", data={"title": "Welcome", "kind": "home"}, status="published"
    )["data"]["saveEntry"]
    assert "errors" in save_site(client, admin, "sitePage", "home", status="published")
    post = save_site(client, admin, "sitePost", "before", status="published")["data"]["saveEntry"]
    scheduled = save_site(
        client,
        admin,
        "sitePost",
        "after",
        status="scheduled",
        scheduledAt=(now() + timedelta(hours=1)).isoformat(),
        id=post["id"],
        version=post["version"],
    )["data"]["saveEntry"]
    with app.state.db.begin() as session:
        session.get(Entry, scheduled["id"]).scheduled_at = now() - timedelta(seconds=1)
    publish_due(app.state.db)
    token = delivery(client, admin)
    assert gql(client, token, "{websiteRedirects}", delivery=True)["data"]["websiteRedirects"] == [
        {"from": "/blog/before", "to": "/blog/after", "entryId": post["id"]}
    ]
    assert home["id"]


def test_editorial_snapshot_is_never_exposed_to_delivery(client, admin):
    define(client, admin)
    live = entry(client, admin, status="published")["data"]["saveEntry"]
    token = delivery(client, admin)
    query = "query($id:ID!){entry(id:$id){publishedSnapshot publishedData publishedTitle publishedSlug}}"
    snapshot = gql(client, admin, query, live)["data"]["entry"]["publishedSnapshot"]
    assert snapshot["data"]["secret"] == "hidden" and snapshot["revision"] == 1
    assert snapshot["schemaVersion"] == 1 and snapshot["publishedAt"]
    assert gql(client, token, query, live, delivery=True)["data"]["entry"] == {
        "publishedSnapshot": None,
        "publishedData": None,
        "publishedTitle": None,
        "publishedSlug": None,
    }


def test_forward_migration_defaults_without_fabricated_history(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/upgrade.db")
    migrate(engine, "0008")
    projects = Table("projects", MetaData(), autoload_with=engine)
    with engine.begin() as connection:
        connection.execute(projects.insert(), {"id": "old", "name": "Existing", "created_at": now()})
    migrate(engine)
    projects = Table("projects", MetaData(), autoload_with=engine)
    paths = Table("website_paths", MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        project = connection.execute(select(projects)).mappings().one()
        assert project["default_locale"] == "en" and project["locales"] == ["en"]
        assert connection.execute(select(paths)).all() == []
    engine.dispose()


def test_image_only_upload_enforced_before_storage(client, admin):
    response = client.post(
        "/api/assets", headers=admin, data={"imagesOnly": "true"}, files={"file": ("notes.txt", b"text", "text/plain")}
    )
    assert response.status_code == 422
    assert gql(client, admin, "{assets{id}}")["data"]["assets"] == []


def test_redirect_reads_respect_delivery_type_scopes_and_workspace(client, admin):
    define(client, admin, "sitePost", [{"name": "title", "type": "text"}])
    define(client, admin, "siteProject", [{"name": "title", "type": "text"}])
    original = save_site(client, admin, "sitePost", "old", status="published")["data"]["saveEntry"]
    save_site(client, admin, "sitePost", "new", status="published", id=original["id"], version=original["version"])
    token = client.post("/api/tokens", headers=admin, json={"name": "Project-only", "scopes": ["siteProject"]}).json()[
        "token"
    ]
    scoped = {"Authorization": "Bearer " + token}
    assert gql(client, scoped, "{websiteRedirects websiteReservedPaths}", delivery=True)["data"] == {
        "websiteRedirects": [],
        "websiteReservedPaths": [],
    }
    other = client.post("/api/projects", headers=admin, json={"name": "Other"}).json()["id"]
    assert gql(client, {**admin, "x-moss-project": other}, "{websiteRedirects websiteReservedPaths}")["data"] == {
        "websiteRedirects": [],
        "websiteReservedPaths": [],
    }


def test_schedule_historical_path_conflict_rolls_back_publication(app, client, admin):
    define(client, admin, "sitePost", [{"name": "title", "type": "text"}])
    original = save_site(client, admin, "sitePost", "old", status="published")["data"]["saveEntry"]
    moved = save_site(
        client, admin, "sitePost", "new", status="published", id=original["id"], version=original["version"]
    )["data"]["saveEntry"]
    scheduled = save_site(
        client, admin, "sitePost", "old", status="scheduled", scheduledAt=(now() + timedelta(hours=1)).isoformat()
    )["data"]["saveEntry"]
    with app.state.db.begin() as session:
        session.get(Entry, scheduled["id"]).scheduled_at = now() - timedelta(seconds=1)
    publish_due(app.state.db)
    failed = gql(client, admin, "query($id:ID!){entry(id:$id){scheduleError isLive}}", scheduled)["data"]["entry"]
    assert failed["scheduleError"]["code"] == "CONFLICT" and not failed["isLive"]
    token = delivery(client, admin)
    assert gql(client, token, "{websiteRedirects}", delivery=True)["data"]["websiteRedirects"] == [
        {"from": "/blog/old", "to": "/blog/new", "entryId": moved["id"]}
    ]


def test_concurrent_home_publications_claim_one_path_and_rollback_losing_entry(client, admin, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from app import content

    define(client, admin, "sitePage", [{"name": "title", "type": "text"}, {"name": "kind", "type": "text"}])
    simultaneous = Barrier(2)
    reserve = content.reserve_website_paths

    def race_claim(*args, **kwargs):
        reserve(*args, **kwargs)
        simultaneous.wait(timeout=10)

    monkeypatch.setattr(content, "reserve_website_paths", race_claim)

    def publish(slug):
        return entry(client, admin, key="sitePage", slug=slug, data={"title": slug, "kind": "home"}, status="published")

    with ThreadPoolExecutor(2) as workers:
        results = list(workers.map(publish, ["first-home", "second-home"]))
    succeeded = [result for result in results if "errors" not in result]
    failed = [result for result in results if "errors" in result]
    assert len(succeeded) == len(failed) == 1
    conflict = failed[0]["errors"][0]["extensions"]
    assert conflict["code"] == "CONFLICT"
    assert conflict["reason"] == "website_path_conflict"
    assert conflict["fieldPath"] == ["slug"]
    assert gql(client, admin, "{entries{total} websiteReservedPaths}")["data"] == {
        "entries": {"total": 1},
        "websiteReservedPaths": ["/"],
    }
    token = delivery(client, admin)
    delivered = gql(client, token, "{entries{nodes{id slug}}}", delivery=True)["data"]["entries"]["nodes"]
    assert len(delivered) == 1 and delivered[0]["id"] == succeeded[0]["data"]["saveEntry"]["id"]
