from types import SimpleNamespace

from sqlalchemy import event, inspect

from app.graphql import cached_generated_schema, generated_schema
from conftest import define, entry, gql


def token(client, headers):
    response = client.post(
        "/api/tokens", headers=headers, json={"name": "cache-test", "scopes": ["article"], "days": 1}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_cached_schema_uses_current_workspace_and_token_scope(client, admin):
    define(client, admin)
    first = entry(client, admin, "first", status="published")["data"]["saveEntry"]
    first_token = token(client, admin)
    result = gql(client, first_token, "{allCmsArticle{ id title }}", delivery=True)
    assert [record["id"] for record in result["data"]["allCmsArticle"]] == [first["id"]]
    project = client.post("/api/projects", headers=admin, json={"name": "Second"}).json()
    second_headers = {**admin, "x-moss-project": project["id"]}
    define(client, second_headers)
    second = entry(client, second_headers, "second", status="published")["data"]["saveEntry"]
    second_token = token(client, second_headers)
    result = gql(client, second_token, "{allCmsArticle{ id title }}", delivery=True)
    assert [record["id"] for record in result["data"]["allCmsArticle"]] == [second["id"]]
    define(client, second_headers, key="restricted", fields=[{"name": "title", "type": "text"}])
    result = gql(client, second_token, "{allCmsRestricted{ id }}", delivery=True)
    assert result.get("errors")
    result = gql(client, first_token, "{allCmsArticle{ secret }}", delivery=True)
    assert result.get("errors")


def test_shape_change_invalidates_cache_even_when_keys_and_versions_match():
    definition = SimpleNamespace(key="article", version=1, fields=[{"name": "title", "type": "text"}])
    first = generated_schema([definition], delivery=True)
    definition.fields = [{"name": "title", "type": "number"}]
    second = generated_schema([definition], delivery=True)
    assert first is not second
    assert 'title(locale: String! = "en"): String' in first.as_str()
    assert 'title(locale: String! = "en"): Float' in second.as_str()
    definition.fields[0]["private"] = True
    third = generated_schema([definition], delivery=True)
    assert "title(locale:" not in third.as_str()
    assert "title(locale:" in generated_schema([definition]).as_str()
    assert cached_generated_schema.cache_info().maxsize == 128


def test_delivery_index_is_migrated_without_including_private_drafts(client, admin):
    define(client, admin)
    published = entry(client, admin, "live", status="published")["data"]["saveEntry"]
    entry(client, admin, "draft", status="draft")
    indexes = {item["name"]: item for item in inspect(client.app.state.engine).get_indexes("entries")}
    assert indexes["ix_entries_delivery_page"]["column_names"] == ["project_id", "type_id", "published_at", "id"]
    assert indexes["ix_entries_due_schedule"]["column_names"] == ["scheduled_at"]
    result = gql(client, token(client, admin), '{entries(typeKey:"article",first:1){nodes{id} total}}', delivery=True)
    assert result["data"]["entries"]["total"] == 1
    assert result["data"]["entries"]["nodes"] == [{"id": published["id"]}]


def test_delivery_string_filters_match_live_values_and_preserve_scalar_semantics(client, admin):
    define(
        client,
        admin,
        fields=[
            {"name": "title", "type": "text"},
            {"name": "category", "type": "enum", "options": ["news", "guide"]},
            {"name": "price", "type": "number"},
            {"name": "enabled", "type": "boolean"},
            {"name": "optional", "type": "text"},
            {"name": "secret", "type": "text", "private": True},
        ],
    )
    saved = entry(
        client,
        admin,
        "published",
        data={"title": "Live", "category": "news", "price": 2, "enabled": True, "secret": "private"},
        status="published",
    )["data"]["saveEntry"]
    entry(
        client,
        admin,
        "published",
        data={"title": "Draft", "category": "guide", "price": 9, "enabled": False},
        id=saved["id"],
        version=saved["version"],
    )
    delivery = token(client, admin)
    query = 'query($filters:JSON!){entries(typeKey:"article",filters:$filters){nodes{id} total}}'
    for filters, expected in [
        ({"category": "news"}, 1),
        ({"category": "guide"}, 0),
        ({"title": "Live"}, 1),
        ({"title": "Draft"}, 0),
        ({"price": 2}, 1),
        ({"price": "2"}, 1),
        ({"enabled": True}, 1),
        ({"optional": None}, 1),
        ({"optional": ""}, 0),
    ]:
        result = gql(client, delivery, query, {"filters": filters}, delivery=True)
        assert not result.get("errors"), result
        assert result["data"]["entries"]["total"] == expected
    result = gql(client, delivery, query, {"filters": {"secret": "private"}}, delivery=True)
    assert result.get("errors")


def test_query_indexes_preserve_preexisting_json_string_storage(client, admin):
    define(client, admin)
    result = entry(
        client, admin, "unicode", data={"title": "Valid title", "body": "Before\u0000after"}, status="published"
    )
    assert not result.get("errors"), result
    delivery = gql(client, token(client, admin), '{entries(typeKey:"article"){nodes{data}}}', delivery=True)
    assert delivery["data"]["entries"]["nodes"][0]["data"]["body"] == "Before\u0000after"


def test_generated_queries_reuse_references_and_assets_only_within_request(app, client, admin):
    from test_images import png

    define(
        client,
        admin,
        fields=[
            {"name": "title", "type": "text"},
            {"name": "related", "type": "reference", "target": "article"},
            {"name": "cover", "type": "asset"},
        ],
    )
    target = entry(client, admin, "target", data={"title": "Original"}, status="published")["data"]["saveEntry"]
    asset = client.post("/api/assets", headers=admin, files={"file": ("shared.png", png(32, 32), "image/png")}).json()[
        "id"
    ]
    for i in range(6):
        result = entry(
            client,
            admin,
            f"row-{i}",
            data={"title": str(i), "related": target["id"], "cover": asset},
            status="published",
        )
        assert not result.get("errors"), result
    headers = token(client, admin)
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT"):
            statements.append(statement)

    event.listen(app.state.engine, "before_cursor_execute", capture)
    try:
        query = "{allCmsArticle(first:20){id related{entry{id title}} cover{id}}}"
        result = gql(client, headers, query, delivery=True)
        assert not result.get("errors"), result
        related = [row["related"] for row in result["data"]["allCmsArticle"] if row["related"]]
        assert len(related) == 6 and all(row["entry"]["title"] == "Original" for row in related)
        assert sum("FROM assets" in sql for sql in statements) == 1
        assert sum(sql.startswith("SELECT content_types.") for sql in statements) == 1
        assert sum("FROM entries" in sql for sql in statements) <= 2
        updated = entry(
            client,
            admin,
            "target",
            data={"title": "Updated"},
            id=target["id"],
            version=target["version"],
            status="published",
        )
        assert not updated.get("errors"), updated
        result = gql(client, headers, query, delivery=True)
        assert all(
            row["related"]["entry"]["title"] == "Updated" for row in result["data"]["allCmsArticle"] if row["related"]
        )
    finally:
        event.remove(app.state.engine, "before_cursor_execute", capture)
