"""REST list paging, filters, and locales match delivery GraphQL."""

import json

from app.delivery_rest import delivery_etag
from app.models import Asset
from conftest import define, entry, gql
from test_cms import delivery
from test_delivery_rest import ENTRY_FIELDS, assert_same_entries

PAGE_FIELDS = [
    {"name": "title", "type": "text", "required": True},
    {"name": "body", "type": "richText"},
    {"name": "rank", "type": "number"},
    {"name": "featured", "type": "boolean"},
    {"name": "released", "type": "date"},
    {"name": "category", "type": "enum", "options": ["news", "guide"]},
    {"name": "translated", "type": "text", "localized": True},
    {"name": "secret", "type": "text", "private": True},
    *[{"name": f"extra{index}", "type": "text"} for index in range(6)],
]
LOCALE_FIELDS = [
    {"name": "title", "type": "text", "required": True, "localized": True},
    {"name": "body", "type": "richText", "localized": True},
    {"name": "rank", "type": "number"},
    {"name": "tags", "type": "list", "item": {"type": "enum", "options": ["One", "Two"], "localized": True}},
    {"name": "notes", "type": "list", "item": {"type": "text", "localized": True}},
    {"name": "labels", "type": "list", "localized": True, "item": {"type": "text"}},
    {
        "name": "address",
        "type": "object",
        "localized": True,
        "fields": [
            {"name": "city", "type": "text"},
            {"name": "internal", "type": "text", "private": True},
        ],
    },
    {
        "name": "meta",
        "type": "object",
        "fields": [
            {"name": "caption", "type": "text", "localized": True},
            {"name": "secret", "type": "text", "private": True},
        ],
    },
    {"name": "cover", "type": "asset", "localized": True},
    {"name": "author", "type": "reference", "localized": True},
    {"name": "secret", "type": "text", "private": True, "localized": True},
]


def filters_param(value):
    """Compact JSON. Query encoding leaves '+' unchanged, so the value cannot contain spaces."""
    return json.dumps(value, separators=(",", ":"))


def assert_same_failure(client, token, params, query, variables=None):
    rest = client.get("/delivery/entries", headers=token, params=params)
    result = gql(client, token, query, variables, delivery=True)
    assert rest.status_code == 422, rest.text
    assert result.get("errors"), result
    assert rest.json()["detail"] == result["errors"][0]["message"]
    assert rest.json()["code"] == result["errors"][0]["extensions"]["code"]


def walk(client, token, **params):
    after = None
    ids = []
    cursors = []
    for _ in range(8):
        page = assert_same_entries(client, token, after=after, **params)
        body = page.json()
        ids.extend(node["id"] for node in body["nodes"])
        if not body["hasNextPage"]:
            assert body["nodes"] and body["endCursor"]
            return ids
        assert body["endCursor"] and body["endCursor"] not in cursors
        cursors.append(body["endCursor"])
        after = body["endCursor"]
    raise AssertionError("pagination did not finish")


def test_paging_and_filters_match_delivery_graphql(client, admin):
    define(client, admin, fields=PAGE_FIELDS)
    define(client, admin, "note", fields=[{"name": "title", "type": "text", "required": True}])
    rows = [
        ("echo", "Alpha", 2, True, "2026-01-02", "news", "alpha", {"en": "Hello", "he": "שלום"}),
        ("delta", "Bravo", 2, False, "2026-01-03", "news", "bravo", None),
        ("charlie", "Charlie", 1, True, "2026-01-01", "guide", "alpha", None),
        ("bravo", "Delta", 4, False, "2026-01-04", "guide", "delta", None),
        ("alpha", "Echo", 5, True, "2026-01-05", "news", "echo", None),
    ]
    for slug, title, rank, featured, released, category, body, translated in rows:
        data = {
            "title": title,
            "body": body,
            "rank": rank,
            "featured": featured,
            "released": released,
            "category": category,
            "secret": "hidden",
        }
        if translated:
            data["translated"] = translated
        saved = entry(client, admin, slug, data, "published")
        assert "errors" not in saved, saved
    assert "errors" not in entry(client, admin, "aside", {"title": "Aside"}, "published", key="note")
    token = delivery(client, admin)

    for sort in ("updated_desc", "updated_asc", "title_asc", "title_desc"):
        assert len(set(walk(client, token, typeKey="article", sort=sort, first="2"))) == 5
    title_order = walk(client, token, typeKey="article", sort="title_asc", first="2")
    listed = assert_same_entries(client, token, typeKey="article", sort="title_asc", first="5")
    assert [node["title"] for node in listed.json()["nodes"]] == ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]
    assert [node["id"] for node in listed.json()["nodes"]] == title_order
    assert listed.json()["nodes"][0]["data"]["translated"] == {"en": "Hello", "he": "שלום"}
    assert "secret" not in listed.json()["nodes"][0]["data"]
    assert len(walk(client, token, first="2", total=True)) == 6
    for direction in ("asc", "desc"):
        assert (
            len(walk(client, token, typeKey="article", order_by={"field": "rank", "direction": direction}, first="2"))
            == 5
        )
    ranks = assert_same_entries(client, token, typeKey="article", order_by={"field": "rank", "direction": "asc"})
    assert [node["data"]["rank"] for node in ranks.json()["nodes"]] == [1, 2, 2, 4, 5]
    rest = client.get("/delivery/entries", headers=token, params={"typeKey": "article", "orderBy": "rank"})
    result = gql(
        client,
        token,
        '{entries(typeKey:"article",orderBy:{field:"rank"}){nodes{id data} endCursor hasNextPage}}',
        delivery=True,
    )
    assert rest.status_code == 200, rest.text
    assert rest.json()["nodes"]
    assert [node["id"] for node in rest.json()["nodes"]] == [node["id"] for node in result["data"]["entries"]["nodes"]]
    assert [node["data"]["rank"] for node in rest.json()["nodes"]] == [1, 2, 2, 4, 5]
    assert rest.json()["endCursor"] == result["data"]["entries"]["endCursor"]
    assert rest.json()["hasNextPage"] == result["data"]["entries"]["hasNextPage"]

    assert_same_entries(client, token, typeKey="article", filters={"rank": 2, "category": "news"}, total=True)
    assert_same_entries(
        client, token, typeKey="article", filters={"featured": False, "released": "2026-01-04"}, total=True
    )
    assert_same_entries(client, token, typeKey="article", filters={"body": "alpha"}, total=True)
    empty = assert_same_entries(client, token, typeKey="article", filters={"rank": 9}, total=True)
    assert empty.json()["nodes"] == [] and empty.json()["endCursor"] is None and empty.json()["total"] == 0
    assert len(walk(client, token, typeKey="article", filters={"category": "news"}, first="1", total=True)) == 3
    assert_same_entries(client, token, typeKey="article", search="Alpha", sort="title_asc", total=True)
    assert assert_same_entries(client, token, typeKey="article", search="שלום", total=True).json()["total"] == 0
    assert assert_same_entries(client, token, typeKey="article", search="Hello", total=True).json()["total"] == 0

    cursor = assert_same_entries(client, token, typeKey="article", sort="title_asc", first="1").json()["endCursor"]
    assert_same_failure(
        client,
        token,
        {"typeKey": "article", "sort": "updated_desc", "after": cursor},
        'query($after:String){entries(typeKey:"article",sort:"updated_desc",after:$after){nodes{id}}}',
        {"after": cursor},
    )
    assert_same_failure(
        client,
        token,
        {"after": "x" * 1001},
        "query($after:String){entries(after:$after){nodes{id}}}",
        {"after": "x" * 1001},
    )
    assert_same_failure(
        client, token, {"first": "0"}, "query($first:Int!){entries(first:$first){nodes{id}}}", {"first": 0}
    )
    assert_same_failure(
        client, token, {"first": "101"}, "query($first:Int!){entries(first:$first){nodes{id}}}", {"first": 101}
    )
    assert_same_failure(client, token, {"sort": "rank"}, '{entries(sort:"rank"){nodes{id}}}')
    assert_same_failure(
        client,
        token,
        {"typeKey": "article", "filters": filters_param({"translated": "Hello"})},
        'query($filters:JSON){entries(typeKey:"article",filters:$filters){nodes{id}}}',
        {"filters": {"translated": "Hello"}},
    )
    assert_same_failure(
        client,
        token,
        {"typeKey": "article", "filters": filters_param({"secret": "hidden"})},
        'query($filters:JSON){entries(typeKey:"article",filters:$filters){nodes{id}}}',
        {"filters": {"secret": "hidden"}},
    )
    too_many = {"body": "alpha", "rank": 2, "featured": True, "released": "2026-01-02", "category": "news"}
    too_many.update({f"extra{index}": "x" for index in range(6)})
    assert len(too_many) == 11
    assert_same_failure(
        client,
        token,
        {"typeKey": "article", "filters": filters_param(too_many)},
        'query($filters:JSON){entries(typeKey:"article",filters:$filters){nodes{id}}}',
        {"filters": too_many},
    )
    assert_same_failure(
        client,
        token,
        {"filters": filters_param({"body": "alpha"})},
        "query($filters:JSON){entries(filters:$filters){nodes{id}}}",
        {"filters": {"body": "alpha"}},
    )
    assert_same_failure(
        client,
        token,
        {"typeKey": "article", "orderBy": "translated"},
        '{entries(typeKey:"article",orderBy:{field:"translated"}){nodes{id}}}',
    )
    assert_same_failure(
        client,
        token,
        {"typeKey": "article", "orderBy": "secret"},
        '{entries(typeKey:"article",orderBy:{field:"secret"}){nodes{id}}}',
    )
    assert_same_failure(
        client,
        token,
        {"typeKey": "article", "sort": "title_asc", "orderBy": "rank", "direction": "asc"},
        '{entries(typeKey:"article",sort:"title_asc",orderBy:{field:"rank",direction:ASC}){nodes{id}}}',
    )
    assert_same_failure(
        client,
        token,
        {"typeKey": "article", "orderBy": "rank", "after": "abc"},
        '{entries(typeKey:"article",orderBy:{field:"rank"},after:"abc"){nodes{id}}}',
    )


def locale_selection(locale):
    return f"""{{
      allCmsArticle(first: 20) {{
        id
        title(locale: "{locale}")
        body(locale: "{locale}")
        tags(locale: "{locale}")
        notes(locale: "{locale}")
        labels(locale: "{locale}")
        address(locale: "{locale}") {{ city }}
        meta {{ caption(locale: "{locale}") }}
        cover(locale: "{locale}") {{ id }}
        author(locale: "{locale}") {{ id }}
      }}
    }}"""


def assert_locale_match(nodes, plain_nodes, selected):
    plain = {node["id"]: node for node in plain_nodes}
    for node in nodes:
        original = plain[node["id"]]
        chosen = selected[node["id"]]
        data = node["data"]
        assert data["title"] == chosen["title"]
        assert data["body"] == chosen["body"]
        assert data["tags"] == chosen["tags"]
        assert data["notes"] == chosen["notes"]
        assert data["labels"] == chosen["labels"]
        assert data["address"] == chosen["address"]
        assert data["meta"]["caption"] == chosen["meta"]["caption"]
        assert "secret" not in data["meta"]
        assert data["cover"] == (chosen["cover"]["id"] if chosen["cover"] else None)
        assert data["author"] == (chosen["author"]["id"] if chosen["author"] else None)
        assert "secret" not in data
        assert data["rank"] == original["data"]["rank"]
        assert node["title"] == original["title"]
        assert set(data) == set(original["data"])


def test_locale_projection_matches_graphql_fields(app, client, admin):
    define(client, admin, "person", fields=[{"name": "title", "type": "text", "required": True}])
    define(client, admin, fields=LOCALE_FIELDS)
    with app.state.db.begin() as session:
        for asset_id in ("cover-en", "cover-he"):
            session.add(
                Asset(
                    id=asset_id,
                    project_id=admin["x-moss-project"],
                    name=asset_id,
                    key=asset_id,
                    storage="local",
                    mime="image/png",
                    size=4,
                )
            )
    ada = entry(client, admin, "ada", {"title": "Ada"}, "published", key="person")
    grace = entry(client, admin, "grace", {"title": "Grace"}, "published", key="person")
    assert "errors" not in ada and "errors" not in grace
    ada_id = ada["data"]["saveEntry"]["id"]
    grace_id = grace["data"]["saveEntry"]["id"]

    def payload(title_en, title_he, rank):
        return {
            "title": {"en": title_en, "he": title_he, "en-US": title_en + " US"},
            "body": {"en": "English body", "he": "גוף"},
            "rank": rank,
            "tags": [{"en": "One", "he": "Two"}, {"en": "One"}],
            "notes": [{"en": "Note", "he": "הערה"}, {"en": "Only"}],
            "labels": {"en": ["Alpha"], "he": ["אלף"]},
            "address": {
                "en": {"city": "Tel Aviv", "internal": "hidden-en"},
                "he": {"city": "חיפה", "internal": "hidden-he"},
            },
            "meta": {"caption": {"en": "Caption", "he": "כיתוב"}, "secret": "hidden"},
            "cover": {"en": "cover-en", "he": "cover-he"},
            "author": {"en": ada_id, "he": grace_id},
            "secret": {"en": "nope", "he": "לא"},
        }

    first_data = payload("Alpha", "אלף", 1)
    first = entry(client, admin, "first", first_data, "published")
    second = entry(client, admin, "second", payload("Bravo", "בית", 2), "published")
    assert "errors" not in first and "errors" not in second, (first, second)
    first = first["data"]["saveEntry"]
    token = delivery(client, admin)

    plain = assert_same_entries(client, token, typeKey="article", sort="title_asc", total=True)
    assert plain.json()["nodes"][0]["data"]["title"] == {"en": "Alpha", "he": "אלף", "en-US": "Alpha US"}
    assert plain.json()["nodes"][0]["data"]["address"]["he"] == {"city": "חיפה"}
    assert "secret" not in plain.json()["nodes"][0]["data"]
    assert plain.json()["nodes"][0]["title"] == "Alpha"

    projected = client.get(
        "/delivery/entries",
        headers=token,
        params={"typeKey": "article", "sort": "title_asc", "locale": "he", "total": "true"},
    )
    assert projected.status_code == 200, projected.text
    hebrew = projected.json()
    assert hebrew["total"] == plain.json()["total"] == 2
    assert [node["id"] for node in hebrew["nodes"]] == [node["id"] for node in plain.json()["nodes"]]
    assert hebrew["endCursor"] == plain.json()["endCursor"] and hebrew["hasNextPage"] is False
    assert projected.headers["etag"] == delivery_etag(hebrew)
    assert projected.headers["etag"] != plain.headers["etag"]
    selected = gql(client, token, locale_selection("he"), delivery=True)
    assert "errors" not in selected, selected
    assert_locale_match(
        hebrew["nodes"], plain.json()["nodes"], {row["id"]: row for row in selected["data"]["allCmsArticle"]}
    )
    assert hebrew["nodes"][0]["data"]["title"] == "אלף"
    assert hebrew["nodes"][0]["data"]["tags"] == ["Two", None]
    assert hebrew["nodes"][0]["data"]["notes"] == ["הערה", None]
    assert hebrew["nodes"][0]["data"]["labels"] == ["אלף"]
    assert hebrew["nodes"][0]["data"]["cover"] == "cover-he"
    assert hebrew["nodes"][0]["data"]["author"] == grace_id
    assert hebrew["nodes"][0]["title"] == "Alpha"

    english = client.get(
        "/delivery/entries", headers=token, params={"typeKey": "article", "sort": "title_asc", "locale": "en"}
    )
    assert english.status_code == 200, english.text
    defaults = gql(
        client,
        token,
        "{allCmsArticle(first:20){id title body tags notes labels address{city} meta{caption} cover{id} author{id}}}",
        delivery=True,
    )
    assert "errors" not in defaults, defaults
    assert_locale_match(
        english.json()["nodes"], plain.json()["nodes"], {row["id"]: row for row in defaults["data"]["allCmsArticle"]}
    )
    explicit = gql(client, token, locale_selection("en"), delivery=True)
    assert_locale_match(
        english.json()["nodes"], plain.json()["nodes"], {row["id"]: row for row in explicit["data"]["allCmsArticle"]}
    )

    regional = client.get(
        "/delivery/entries", headers=token, params={"typeKey": "article", "sort": "title_asc", "locale": "en-US"}
    )
    assert regional.status_code == 200, regional.text
    chosen = gql(client, token, locale_selection("en-US"), delivery=True)
    assert "errors" not in chosen, chosen
    assert_locale_match(
        regional.json()["nodes"], plain.json()["nodes"], {row["id"]: row for row in chosen["data"]["allCmsArticle"]}
    )
    assert regional.json()["nodes"][0]["data"]["title"] == "Alpha US"
    assert regional.json()["nodes"][0]["data"]["labels"] is None
    assert regional.json()["nodes"][0]["data"]["tags"] == [None, None]

    missing = client.get(
        "/delivery/entries", headers=token, params={"typeKey": "article", "sort": "title_asc", "locale": "de"}
    )
    assert missing.status_code == 200, missing.text
    absent = gql(client, token, locale_selection("de"), delivery=True)
    assert "errors" not in absent, absent
    assert_locale_match(
        missing.json()["nodes"], plain.json()["nodes"], {row["id"]: row for row in absent["data"]["allCmsArticle"]}
    )
    assert missing.json()["nodes"][0]["data"]["title"] is None
    assert missing.json()["nodes"][0]["data"]["rank"] == 1

    first_page = assert_same_entries(client, token, typeKey="article", sort="title_asc", first="1")
    localized_page = client.get(
        "/delivery/entries",
        headers=token,
        params={"typeKey": "article", "sort": "title_asc", "first": "1", "locale": "he"},
    )
    assert localized_page.status_code == 200, localized_page.text
    assert localized_page.json()["endCursor"] == first_page.json()["endCursor"]
    assert localized_page.json()["hasNextPage"] is True
    assert [node["id"] for node in localized_page.json()["nodes"]] == [
        node["id"] for node in first_page.json()["nodes"]
    ]
    assert localized_page.json()["nodes"][0]["data"]["title"] == "אלף"
    second_page = assert_same_entries(
        client, token, typeKey="article", sort="title_asc", first="1", after=first_page.json()["endCursor"]
    )
    localized_second = client.get(
        "/delivery/entries",
        headers=token,
        params={
            "typeKey": "article",
            "sort": "title_asc",
            "first": "1",
            "locale": "he",
            "after": first_page.json()["endCursor"],
        },
    )
    assert [node["id"] for node in localized_second.json()["nodes"]] == [
        node["id"] for node in second_page.json()["nodes"]
    ]
    assert localized_second.json()["endCursor"] == second_page.json()["endCursor"]
    assert localized_second.json()["hasNextPage"] is False
    assert localized_second.json()["nodes"][0]["data"]["title"] == "בית"

    filtered = client.get(
        "/delivery/entries",
        headers=token,
        params={"typeKey": "article", "filters": filters_param({"rank": 1}), "locale": "he", "total": "true"},
    )
    matched = assert_same_entries(client, token, typeKey="article", filters={"rank": 1}, total=True)
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["total"] == matched.json()["total"] == 1
    assert filtered.json()["nodes"][0]["id"] == matched.json()["nodes"][0]["id"] == first["id"]
    assert filtered.json()["endCursor"] == matched.json()["endCursor"]
    assert filtered.json()["nodes"][0]["data"]["title"] == "אלף"
    assert filtered.json()["nodes"][0]["data"]["rank"] == 1
    assert assert_same_entries(client, token, typeKey="article", search="Alpha", total=True).json()["total"] == 1
    assert assert_same_entries(client, token, typeKey="article", search="אלף", total=True).json()["total"] == 0

    item = client.get("/delivery/entries/" + first["id"], headers=token, params={"locale": "he"})
    assert item.status_code == 200, item.text
    assert item.json()["data"] == hebrew["nodes"][0]["data"]
    assert item.json()["title"] == "Alpha"
    assert item.headers["etag"] == delivery_etag(item.json())
    bare = client.get("/delivery/entries/" + first["id"], headers=token)
    graphql_entry = gql(
        client,
        token,
        f"query($id:ID!){{entry(id:$id){{{ENTRY_FIELDS}}}}}",
        {"id": first["id"]},
        delivery=True,
    )
    assert bare.json() == graphql_entry["data"]["entry"]
    assert bare.json()["data"]["title"]["he"] == "אלף"
    assert item.headers["etag"] != bare.headers["etag"]
    cached = client.get(
        "/delivery/entries/" + first["id"],
        headers={**token, "if-none-match": item.headers["etag"]},
        params={"locale": "he"},
    )
    assert cached.status_code == 304 and cached.content == b""
    other = client.get(
        "/delivery/entries/" + first["id"],
        headers={**token, "if-none-match": item.headers["etag"]},
        params={"locale": "en"},
    )
    assert other.status_code == 200 and other.json()["data"]["title"] == "Alpha"
    head = client.head(
        "/delivery/entries",
        headers=token,
        params={"typeKey": "article", "locale": "he", "sort": "title_asc", "total": "true"},
    )
    assert head.status_code == 200 and head.headers["etag"] == projected.headers["etag"]

    mixed = client.get("/delivery/entries", headers=token, params={"locale": "he"})
    assert mixed.status_code == 200, mixed.text
    people = [node for node in mixed.json()["nodes"] if node["typeKey"] == "person"]
    articles = [node for node in mixed.json()["nodes"] if node["typeKey"] == "article"]
    assert {node["data"]["title"] for node in people} == {"Ada", "Grace"}
    assert {node["data"]["title"] for node in articles} == {"אלף", "בית"}

    changed = {**first_data, "title": {**first_data["title"], "he": "שונה"}}
    edited = entry(client, admin, "first", changed, id=first["id"], version=first["version"])
    assert "errors" not in edited, edited
    again = client.get(
        "/delivery/entries",
        headers=token,
        params={"typeKey": "article", "sort": "title_asc", "locale": "he", "total": "true"},
    )
    assert again.json() == hebrew
    assert again.headers["etag"] == projected.headers["etag"]

    for bad in ("EN", "he_IL", "", "x", "a" * 41):
        response = client.get("/delivery/entries", headers=token, params={"locale": bad})
        assert response.status_code == 422, (bad, response.text)
        assert response.json() == {"detail": "Use a valid locale code.", "code": "VALIDATION"}
    assert client.get("/delivery/types", headers=token, params={"locale": "en"}).status_code == 422
    assets = client.get(f"/delivery/entries/{first['id']}/resolved-assets", headers=token, params={"locale": "en"})
    assert assets.status_code == 422
    assert assets.json()["detail"] == "Unknown delivery parameter."
    assert_same_failure(
        client,
        token,
        {"typeKey": "article", "locale": "he", "filters": filters_param({"title": "Alpha"})},
        'query($filters:JSON){entries(typeKey:"article",filters:$filters){nodes{id}}}',
        {"filters": {"title": "Alpha"}},
    )
    assert_same_failure(
        client,
        token,
        {"typeKey": "article", "orderBy": "title"},
        '{entries(typeKey:"article",orderBy:{field:"title"}){nodes{id}}}',
    )
    assert second["data"]["saveEntry"]["id"] != first["id"]
