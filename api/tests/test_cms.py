import json
from datetime import timedelta
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from app.config import Settings
from app.content import publish_due
from app.migrate import migrate
from app.models import Entry, User, now
from app.security import issue_token
from conftest import define, entry, gql


def delivery(client, admin, scopes=None):
    result = client.post("/api/tokens", headers=admin, json={"name": "Website", "scopes": scopes or [], "days": 1})
    assert result.status_code == 200, result.text
    return {"Authorization": "Bearer " + result.json()["token"]}


def invited(app, client, admin, role="editor", email="editor@example.com"):
    response = client.post("/api/team/invitations", headers=admin, json={"email": email, "role": role})
    assert response.status_code == 200, response.text
    raw = response.json()["url"].split("/")[-1]
    other = TestClient(app)
    response = other.post(
        "/auth/accept", json={"token": raw, "email": email, "password": "secure-member-password", "name": role}
    )
    assert response.status_code == 200, response.text
    account = other.get("/auth/me").json()
    return other, {"x-moss-project": admin["x-moss-project"], "x-moss-csrf": account["csrf"]}, account["user"]["id"]


def test_bootstrap_required_and_no_demo_content(client, admin):
    assert (
        client.post(
            "/auth/setup",
            json={"token": "t" * 30, "email": "other@example.com", "password": "secure-test-password", "name": "Other"},
        ).status_code
        == 409
    )
    assert gql(client, admin, "{contentTypes{key} entries{total}}")["data"] == {
        "contentTypes": [],
        "entries": {"total": 0},
    }


def test_authentication_and_csrf(client, admin):
    define(client, admin)
    no_csrf = {"x-moss-project": admin["x-moss-project"]}
    assert (
        gql(client, no_csrf, 'mutation {deleteContentType(key:"article")}')["errors"][0]["extensions"]["code"]
        == "FORBIDDEN"
    )
    client.cookies.clear()
    assert client.post("/graphql", json={"query": "{contentTypes{key}}"}, headers=admin).status_code == 401
    assert client.post("/auth/login", json={"email": "admin@example.com", "password": "wrong"}).status_code == 401


def test_roles_and_team_management(app, client, admin):
    define(client, admin)
    reader, reader_headers, reader_id = invited(app, client, admin, "reader", "reader@example.com")
    assert "errors" not in gql(reader, reader_headers, "{entries{total}}")
    assert entry(reader, reader_headers)["errors"][0]["extensions"]["code"] == "FORBIDDEN"
    assert (
        reader.post("/api/team/invitations", headers=reader_headers, json={"email": "new@example.com"}).status_code
        == 403
    )
    editor, editor_headers, _ = invited(app, client, admin)
    assert "errors" not in entry(editor, editor_headers)
    assert (
        gql(editor, editor_headers, 'mutation{saveContentType(key:"wrong",name:"Wrong",fields:[]){key}}')["errors"][0][
            "extensions"
        ]["code"]
        == "FORBIDDEN"
    )
    assert client.patch("/api/team/" + reader_id, headers=admin, json={"role": "editor"}).status_code == 200
    assert client.delete("/api/team/" + reader_id, headers=admin).status_code == 200
    assert reader.post("/graphql", headers=reader_headers, json={"query": "{entries{total}}"}).status_code == 403
    own_id = client.get("/auth/me").json()["user"]["id"]
    assert client.delete("/api/team/" + own_id, headers=admin).status_code == 409
    assert client.patch("/api/team/" + own_id, headers=admin, json={"role": "reader"}).status_code == 409


def test_project_isolation(app, client, admin):
    define(client, admin)
    first = entry(client, admin)["data"]["saveEntry"]
    new = client.post("/api/projects", headers=admin, json={"name": "Separate"}).json()
    headers = {**admin, "x-moss-project": new["id"]}
    assert gql(client, headers, "{contentTypes{key} entries{total}}")["data"]["entries"]["total"] == 0
    assert (
        gql(client, headers, "query($id:ID!){entry(id:$id){id}}", {"id": first["id"]})["errors"][0]["extensions"][
            "code"
        ]
        == "NOT_FOUND"
    )
    outsider, outsider_headers, _ = invited(app, client, admin)
    assert (
        outsider.post(
            "/graphql", json={"query": "{entries{total}}"}, headers={**outsider_headers, "x-moss-project": new["id"]}
        ).status_code
        == 403
    )


def test_delivery_scopes_drafts_private_fields_cache_and_revocation(client, admin):
    define(client, admin)
    define(client, admin, "other")
    entry(client, admin)
    live = entry(client, admin, "live", status="published")["data"]["saveEntry"]
    entry(client, admin, "outside-scope", key="other", status="published")
    token = delivery(client, admin, ["article"])
    query = "{entries{total nodes{slug data}} allCmsArticle{title body}}"
    result = gql(client, token, query, delivery=True)
    assert result["data"]["entries"]["total"] == 1
    assert result["data"]["entries"]["nodes"][0]["data"] == {"title": "live", "body": "text"}
    assert "errors" in gql(client, token, "{allCmsArticle{secret}}", delivery=True)
    assert "errors" in gql(client, token, 'mutation{deleteEntry(id:"x",version:1)}', delivery=True)
    assert "errors" in gql(client, token, '{revisions(id:"' + live["id"] + '"){number}}', delivery=True)
    draft = gql(client, admin, '{entries(status:"draft"){nodes{id}}}')["data"]["entries"]["nodes"][0]["id"]
    assert "errors" in gql(client, token, '{entry(id:"' + draft + '"){id}}', delivery=True)
    assert "errors" in gql(client, token, '{entries(typeKey:"other"){total}}', delivery=True)
    response = client.post("/delivery/graphql", json={"query": query}, headers=token)
    assert (
        client.post(
            "/delivery/graphql", json={"query": query}, headers={**token, "if-none-match": response.headers["etag"]}
        ).status_code
        == 304
    )
    record = client.get("/api/tokens", headers=admin).json()[0]
    assert client.delete("/api/tokens/" + record["id"], headers=admin).status_code == 200
    assert client.post("/delivery/graphql", json={"query": query}, headers=token).status_code == 401


def test_validation_conflicts_and_recoverable_delete(client, admin):
    define(client, admin)
    assert "errors" in entry(client, admin, data={"body": "missing required title"})
    assert "errors" in entry(client, admin, data={"title": "A", "unknown": True})
    first = entry(client, admin)["data"]["saveEntry"]
    assert entry(client, admin)["errors"][0]["extensions"]["code"] == "CONFLICT"
    assert entry(client, admin, id="missing", version=1)["errors"][0]["extensions"]["code"] == "NOT_FOUND"
    updated = entry(client, admin, id=first["id"], version=1, data={"title": "Changed"})["data"]["saveEntry"]
    assert updated["version"] == 2
    assert entry(client, admin, id=first["id"], version=1)["errors"][0]["extensions"]["code"] == "CONFLICT"
    assert gql(client, admin, "mutation($id:ID!){deleteEntry(id:$id,version:2)}", {"id": first["id"]})["data"][
        "deleteEntry"
    ]
    assert gql(client, admin, "{entries{total}}")["data"]["entries"]["total"] == 0
    archived = gql(client, admin, '{entries(status:"deleted"){nodes{id version}}}')["data"]["entries"]["nodes"][0]
    restored = gql(
        client,
        admin,
        "mutation($id:ID!,$version:Int!){restoreEntry(id:$id,number:1,version:$version){data status version}}",
        archived,
    )
    assert restored["data"]["restoreEntry"]["status"] == "draft"
    assert restored["data"]["restoreEntry"]["data"]["title"] == "hello"


def test_schema_versions_migrations_and_generated_nested_types(client, admin):
    fields = [
        {"name": "title", "type": "text", "localized": True},
        {"name": "rating", "type": "number"},
        {"name": "featured", "type": "boolean"},
        {"name": "released", "type": "date"},
        {"name": "category", "type": "enum", "options": ["news", "guide"]},
        {
            "name": "address",
            "type": "object",
            "fields": [{"name": "city", "type": "text"}, {"name": "internal", "type": "text", "private": True}],
        },
        {"name": "tags", "type": "list", "item": {"type": "text"}},
    ]
    define(client, admin, fields=fields)
    data = {
        "title": {"en": "Hello", "he": "שלום"},
        "rating": 3.5,
        "featured": True,
        "released": "2026-10-05",
        "category": "guide",
        "address": {"city": "Tel Aviv", "internal": "hidden"},
        "tags": ["a", "b"],
    }
    assert "errors" not in entry(client, admin, data=data, status="published")
    token = delivery(client, admin)
    result = gql(
        client,
        token,
        '{allCmsArticle{title(locale:"he") rating featured released category address{city} tags}}',
        delivery=True,
    )
    assert result["data"]["allCmsArticle"][0]["title"] == "שלום"
    assert result["data"]["allCmsArticle"][0]["address"] == {"city": "Tel Aviv"}
    new_fields = [*fields, {"name": "requiredField", "type": "text", "required": True}]
    mutation = 'mutation($fields:JSON!,$migration:JSON){saveContentType(key:"article",name:"Article",fields:$fields,version:1,migration:$migration){version}}'
    assert "errors" in gql(client, admin, mutation, {"fields": new_fields})
    assert (
        gql(client, admin, mutation, {"fields": new_fields, "migration": {"defaults": {"requiredField": "default"}}})[
            "data"
        ]["saveContentType"]["version"]
        == 2
    )
    assert len(gql(client, admin, '{schemaHistory(key:"article")}')["data"]["schemaHistory"]) == 2


def test_assets_references_and_cross_project_validation(app, client, admin):
    define(client, admin)
    target = entry(client, admin, status="published")["data"]["saveEntry"]
    uploaded = client.post("/api/assets", headers=admin, files={"file": ("image.txt", b"hello", "text/plain")})
    assert uploaded.status_code == 200, uploaded.text
    asset = uploaded.json()
    assert client.get(asset["url"]).content == b"hello"
    assert client.get(asset["url"].replace("signature=", "signature=invalid")).status_code == 403
    fields = [
        {"name": "title", "type": "text"},
        {"name": "parent", "type": "reference", "target": "article"},
        {"name": "file", "type": "asset"},
    ]
    define(client, admin, "page", fields)
    assert "errors" not in entry(
        client,
        admin,
        key="page",
        data={"title": "Page", "parent": target["id"], "file": asset["id"]},
        status="published",
    )
    token = delivery(client, admin)
    result = gql(client, token, "{allCmsPage{parent{entry{slug}} file{name url}}}", delivery=True)
    assert result["data"]["allCmsPage"][0]["parent"]["entry"]["slug"] == "hello"
    new = client.post("/api/projects", headers=admin, json={"name": "Other"}).json()
    other = {**admin, "x-moss-project": new["id"]}
    define(client, other, "page", fields)
    assert "errors" in entry(client, other, key="page", data={"title": "Wrong", "file": asset["id"]})


def test_scheduled_publishing(app, client, admin):
    define(client, admin)
    scheduled = entry(client, admin, status="scheduled", scheduledAt=(now() + timedelta(hours=1)).isoformat())["data"][
        "saveEntry"
    ]
    assert gql(client, delivery(client, admin), "{entries{total}}", delivery=True)["data"]["entries"]["total"] == 0
    with app.state.db.begin() as session:
        session.get(Entry, scheduled["id"]).scheduled_at = now() - timedelta(seconds=1)
    publish_due(app.state.db)
    assert gql(client, delivery(client, admin), "{entries{total}}", delivery=True)["data"]["entries"]["total"] == 1


def test_cursor_filters_and_query_limits(client, admin):
    define(client, admin)
    for i in range(5):
        entry(client, admin, str(i), data={"title": f"Title {i}"})
    first = gql(client, admin, '{entries(first:2,sort:"title_asc"){nodes{slug} endCursor total hasNextPage}}')["data"][
        "entries"
    ]
    second = gql(
        client,
        admin,
        'query($after:String){entries(first:2,sort:"title_asc",after:$after){nodes{slug}}}',
        {"after": first["endCursor"]},
    )["data"]["entries"]
    assert first["total"] == 5 and first["hasNextPage"]
    assert not {n["slug"] for n in first["nodes"]} & {n["slug"] for n in second["nodes"]}
    assert (
        gql(client, admin, '{entries(typeKey:"article",filters:{title:"Title 3"}){total}}')["data"]["entries"]["total"]
        == 1
    )
    assert "errors" in gql(client, admin, "{entries(first:1000){total}}")
    query = "{" + " ".join(f"q{i}: entries {{ total }}" for i in range(101)) + "}"
    assert gql(client, admin, query)["errors"][0]["extensions"]["code"] == "QUERY_LIMIT"


def test_recovery_revokes_sessions_and_tokens_are_one_time(app, client, admin):
    me = client.get("/auth/me").json()
    with app.state.db.begin() as session:
        raw, _ = issue_token(session, "reset", days=1, user_id=me["user"]["id"], email=me["user"]["email"])
    other = TestClient(app)
    body = {"token": raw, "name": "Admin", "email": me["user"]["email"], "password": "new-secure-password"}
    assert other.post("/auth/accept", json=body).status_code == 200
    assert client.get("/auth/me").status_code == 401
    assert other.post("/auth/accept", json=body).status_code == 400
    assert (
        other.post("/auth/login", json={"email": me["user"]["email"], "password": "new-secure-password"}).status_code
        == 200
    )


def test_existing_account_invitation_requires_account_login(app, client, admin):
    member, headers, _ = invited(app, client, admin)
    second = client.post("/api/projects", headers=admin, json={"name": "Another"}).json()
    admin2 = {**admin, "x-moss-project": second["id"]}
    url = client.post(
        "/api/team/invitations", headers=admin2, json={"email": "editor@example.com", "role": "reader"}
    ).json()["url"]
    body = {"token": url.split("/")[-1], "email": "editor@example.com", "password": "not-used-value", "name": "Editor"}
    outsider = TestClient(app)
    assert outsider.post("/auth/accept", json=body).status_code == 401
    assert member.post("/auth/accept", json=body, headers=headers).status_code == 200
    assert len(member.get("/auth/me").json()["projects"]) == 2


def test_oidc_verified_email_and_explicit_linking(app, client, admin, monkeypatch):
    app.state.oauth_providers = [{"id": "oidc", "name": "Test OIDC"}]
    fake = type("Client", (), {})()
    fake.authorize_access_token = AsyncMock(
        return_value={"userinfo": {"sub": "subject", "email": "admin@example.com", "email_verified": True}}
    )
    monkeypatch.setattr(app.state.oauth, "create_client", lambda _: fake)
    response = client.get("/auth/oauth/oidc/callback", follow_redirects=False)
    assert "existing%20account" in response.headers["location"]
    fake.authorize_access_token.return_value = {
        "userinfo": {"sub": "subject", "email": "unverified@example.com", "email_verified": False}
    }
    assert "verified" in client.get("/auth/oauth/oidc/callback", follow_redirects=False).headers["location"]
    assert client.get("/auth/oauth/unknown/start").status_code == 404


def test_oauth_missing_state_does_not_create_account(app, client, admin):
    app.state.oauth_providers = [{"id": "oidc", "name": "Test OIDC"}]
    app.state.oauth.register(
        "oidc",
        client_id="test",
        client_secret="test",
        server_metadata_url="https://invalid.example/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email"},
    )
    response = client.get("/auth/oauth/oidc/callback?code=invalid&state=missing", follow_redirects=False)
    assert response.status_code == 303 and "error=" in response.headers["location"]
    with app.state.db() as session:
        assert len(session.scalars(select(User)).all()) == 1


def test_migration_preserves_legacy_articles(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "legacy.db"))
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE articles (id INTEGER PRIMARY KEY, title TEXT, slug TEXT, body TEXT, status TEXT)")
        )
        conn.execute(text("INSERT INTO articles VALUES (1,'Original','original','Keep me','published')"))
    migrate(engine)
    migrate(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM articles")).scalar() == 1
        assert json.loads(conn.execute(text("SELECT data FROM entries")).scalar())["body"] == "Keep me"
        assert conn.execute(text("SELECT count(*) FROM revisions")).scalar() == 1


def test_production_config_rejects_unsafe_defaults(tmp_path):
    import pytest

    with pytest.raises(RuntimeError):
        Settings(
            environment="production",
            secret="s" * 40,
            setup_token="t" * 30,
            database_url="postgresql://x:change-me@db/cms",
            storage_dir=tmp_path,
        ).validate()


def test_health_and_unknown_routes(client):
    assert client.get("/ready").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/not-an-admin-route").status_code == 404
    assert client.get("/assets/missing.js").status_code == 404


def test_private_fields_in_list_objects_are_hidden(client, admin):
    fields = [
        {
            "name": "cards",
            "type": "list",
            "item": {
                "type": "object",
                "fields": [{"name": "caption", "type": "text"}, {"name": "secret", "type": "text", "private": True}],
            },
        }
    ]
    define(client, admin, fields=fields)
    entry(client, admin, data={"cards": [{"caption": "Visible", "secret": "Hidden"}]}, status="published")
    result = gql(
        client,
        delivery(client, admin),
        "{contentTypes{fields} entries{nodes{data}} allCmsArticle{cards{caption}}}",
        delivery=True,
    )
    assert "errors" not in result
    assert "secret" not in json.dumps(result["data"])
    assert result["data"]["allCmsArticle"][0]["cards"] == [{"caption": "Visible"}]


def test_oauth_invitation_and_account_linking(app, client, admin, monkeypatch):
    from fastapi.responses import RedirectResponse

    app.state.oauth_providers = [{"id": "oidc", "name": "Test OIDC"}]
    fake = type("Client", (), {})()
    fake.authorize_redirect = AsyncMock(return_value=RedirectResponse("https://provider.example/authorize"))
    fake.authorize_access_token = AsyncMock(
        return_value={
            "userinfo": {
                "sub": "member-subject",
                "email": "oauth@example.com",
                "email_verified": True,
                "name": "OAuth Member",
            }
        }
    )
    monkeypatch.setattr(app.state.oauth, "create_client", lambda _: fake)
    url = client.post("/api/team/invitations", headers=admin, json={"email": "oauth@example.com"}).json()["url"]
    member = TestClient(app)
    member.get("/auth/oauth/oidc/start", params={"invite": url.split("/")[-1]}, follow_redirects=False)
    assert member.get("/auth/oauth/oidc/callback", follow_redirects=False).headers["location"] == "/#content"
    account = member.get("/auth/me").json()
    assert account["user"]["email"] == "oauth@example.com" and account["projects"][0]["role"] == "editor"
    assert client.get("/api/team", headers=admin).json()["invitations"] == []
    fake.authorize_access_token.return_value = {
        "userinfo": {"sub": "admin-subject", "email": "admin@example.com", "email_verified": True}
    }
    assert client.post("/auth/oauth/oidc/link", headers=admin).status_code == 200
    assert client.get("/auth/oauth/oidc/callback", follow_redirects=False).headers["location"] == "/#content"
    assert client.get("/auth/me").json()["providers"] == ["oidc"]


def test_s3_upload_and_signed_download(app, client, admin, monkeypatch):
    from unittest.mock import MagicMock
    import app.storage as storage

    fake = MagicMock()
    fake.generate_presigned_url.return_value = "https://storage.example/signed-object"
    monkeypatch.setattr(storage.boto3, "client", lambda *args, **kwargs: fake)
    app.state.settings.s3_bucket = "private-bucket"
    asset = client.post("/api/assets", headers=admin, files={"file": ("image.txt", b"content", "text/plain")}).json()
    assert fake.put_object.call_args.kwargs["Bucket"] == "private-bucket"
    assert fake.put_object.call_args.kwargs["Body"] == b"content"
    response = client.get(asset["url"], follow_redirects=False)
    assert response.status_code == 307 and response.headers["location"] == "https://storage.example/signed-object"
    assert fake.generate_presigned_url.call_args.kwargs["Params"]["ResponseContentDisposition"] == "attachment"


def test_empty_type_deletion_and_malformed_schema_validation(client, admin):
    define(client, admin)
    assert gql(client, admin, 'mutation{deleteContentType(key:"article")}')["data"]["deleteContentType"] is True
    for fields in [[{"name": None, "type": "text"}], [{"name": "field", "type": []}]]:
        result = gql(
            client,
            admin,
            'mutation($fields:JSON!){saveContentType(key:"article",name:"Article",fields:$fields){key}}',
            {"fields": fields},
        )
        assert result["errors"][0]["extensions"]["code"] == "VALIDATION"
    define(client, admin)
    result = gql(
        client,
        admin,
        'mutation{saveContentType(key:"article",name:"Article",fields:[{name:"title",type:"text"}],version:1,migration:{rename:[]}){key}}',
    )
    assert result["errors"][0]["extensions"]["code"] == "VALIDATION"


def test_generated_delivery_signatures_and_localized_list_items(client, admin):
    fields = [
        {"name": "title", "type": "text", "localized": True},
        {"name": "tags", "type": "list", "item": {"type": "enum", "options": ["One", "Two"], "localized": True}},
        {
            "name": "group",
            "type": "object",
            "fields": [{"name": "private", "type": "text", "private": True}, {"name": "image", "type": "asset"}],
        },
        {"name": "author", "type": "reference"},
        {"name": "when", "type": "date"},
    ]
    define(client, admin, fields=fields)
    entry(
        client,
        admin,
        data={"title": {"en": "Title", "fr": "Titre"}, "tags": [{"en": "One", "fr": "Two"}]},
        status="published",
    )
    token = delivery(client, admin)
    result = gql(client, token, '{allCmsArticle{title(locale:"fr") tags(locale:"fr")}}', delivery=True)
    assert result["data"]["allCmsArticle"] == [{"title": "Titre", "tags": ["Two"]}]
    from app.graphql import generated_schema
    from types import SimpleNamespace

    schema = generated_schema([SimpleNamespace(key="sample", fields=fields)], delivery=True).as_str()
    for signature in [
        'tags(locale: String! = "en"): [CmsSampleTagsItemEnum]',
        'image(locale: String! = "en"): AssetNode',
        'author(locale: String! = "en"): ReferenceNode',
    ]:
        assert signature in schema
    assert "private(locale:" not in schema


def test_reference_targets_counts_and_self_reference_are_explicit(client, admin):
    invalid = gql(
        client,
        admin,
        'mutation{saveContentType(key:"article",name:"Articles",fields:[{name:"author",type:"reference",target:"unknown"}]){id}}',
    )
    assert "errors" in invalid
    valid = define(
        client,
        admin,
        fields=[{"name": "parent", "type": "reference", "target": "article"}, {"name": "title", "type": "text"}],
    )
    assert "errors" not in valid
    assert gql(client, admin, "{contentTypes{key entryCount}}")["data"]["contentTypes"] == [
        {"key": "article", "entryCount": 0}
    ]
    assert "errors" not in entry(client, admin, data={"title":"Counted"})
    assert gql(client, admin, "{contentTypes{entryCount}}")["data"]["contentTypes"][0]["entryCount"] == 1
