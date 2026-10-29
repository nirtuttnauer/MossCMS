"""The committed OpenAPI document matches FastAPI, and the public route reuses delivery ETags."""

import difflib
import json

from pydantic import TypeAdapter

from app.delivery_rest import ENTRY_PARAMETERS, ITEM_PARAMETERS, delivery_etag
from app.models import Asset
from app.openapi_schema import (
    OPENAPI_PATH,
    AssetDocument,
    ContentTypeDocument,
    EntryDocument,
    EntryPage,
    ErrorBody,
    RedirectDocument,
    UnauthorizedBody,
    build_openapi,
    canonical_openapi,
)
from conftest import define, entry
from test_cms import delivery

TYPES = TypeAdapter(list[ContentTypeDocument])
ASSETS = TypeAdapter(list[AssetDocument])
REDIRECTS = TypeAdapter(list[RedirectDocument])
PATHS = TypeAdapter(list[str])
DELIVERY_PATHS = {
    "/delivery/types",
    "/delivery/types/{typeKey}",
    "/delivery/entries",
    "/delivery/entries/{id}",
    "/delivery/entries/{id}/resolved-assets",
    "/delivery/website/redirects",
    "/delivery/website/reserved-paths",
    "/delivery/graphql",
}


def _assert_committed(generated: str) -> None:
    committed = OPENAPI_PATH.read_text()
    if generated == committed:
        return
    diff = "".join(
        difflib.unified_diff(
            committed.splitlines(keepends=True),
            generated.splitlines(keepends=True),
            fromfile="api/openapi.json",
            tofile="generated",
        )
    )
    raise AssertionError("Committed OpenAPI document does not match the generated schema.\n" + diff)


def test_committed_openapi_matches_generated_schema(app):
    schema = build_openapi(app)
    text = canonical_openapi(schema)
    _assert_committed(text)
    parsed = json.loads(text)
    assert parsed == schema
    assert set(schema["paths"]) >= DELIVERY_PATHS
    assert "/openapi.json" not in schema["paths"]
    assert "/docs" not in schema["paths"]
    assert schema["components"]["securitySchemes"]["DeliveryBearer"]["scheme"] == "bearer"
    listed = schema["paths"]["/delivery/entries"]["get"]
    assert {item["name"] for item in listed["parameters"] if item["in"] == "query"} == ENTRY_PARAMETERS
    item = schema["paths"]["/delivery/entries/{id}"]["get"]
    assert {param["name"] for param in item["parameters"] if param["in"] == "query"} == ITEM_PARAMETERS
    assert listed["security"] == [{"DeliveryBearer": []}]
    assert "security" not in schema["paths"]["/health"]["get"]
    assert (
        schema["paths"]["/delivery/entries"]["get"]["operationId"]
        != schema["paths"]["/delivery/entries"]["head"]["operationId"]
    )
    assets = schema["paths"]["/delivery/entries/{id}/resolved-assets"]["get"]
    assert "ETag" not in assets["responses"]["200"].get("headers", {})
    assert assets["responses"]["200"]["headers"]["Cache-Control"]["schema"]["const"] == "no-store"
    assert "ETag" in listed["responses"]["200"]["headers"]
    assert "content" not in schema["paths"]["/delivery/entries"]["head"]["responses"]["200"]


def test_openapi_etag_and_docs_page(client):
    first = client.get("/openapi.json")
    assert first.status_code == 200, first.text
    assert first.headers["content-type"].startswith("application/json")
    denied = client.get("/delivery/entries")
    assert denied.status_code == 401
    UnauthorizedBody.model_validate(denied.json())
    assert first.headers["cache-control"] == "private, no-cache"
    assert first.headers["vary"] == denied.headers["vary"]
    assert first.headers["vary"].startswith("Authorization, Origin")
    assert first.headers["etag"] == delivery_etag(first.json())
    assert canonical_openapi(first.json()) == OPENAPI_PATH.read_text()
    assert first.headers["x-request-id"]
    again = client.get("/openapi.json")
    assert again.headers["etag"] == first.headers["etag"]
    cached = client.get("/openapi.json", headers={"if-none-match": first.headers["etag"]})
    assert cached.status_code == 304
    assert cached.content == b""
    assert "content-type" not in cached.headers
    assert cached.headers["etag"] == first.headers["etag"]
    assert cached.headers["cache-control"] == "private, no-cache"
    assert cached.headers["vary"] == first.headers["vary"]
    assert cached.headers["x-request-id"]
    assert client.get("/openapi.json", headers={"if-none-match": "*"}).status_code == 200
    assert client.get("/openapi.json", headers={"if-none-match": "W/" + first.headers["etag"]}).status_code == 200
    assert (
        client.get("/openapi.json", headers={"if-none-match": '"other", ' + first.headers["etag"]}).status_code == 200
    )
    assert client.get("/openapi.json", headers={"if-none-match": '"not-the-etag"'}).status_code == 200
    head = client.head("/openapi.json")
    assert head.status_code == 200
    assert head.content == b""
    assert head.headers["etag"] == first.headers["etag"]
    head_cached = client.head("/openapi.json", headers={"if-none-match": first.headers["etag"]})
    assert head_cached.status_code == 304 and head_cached.content == b""
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "text/html" in docs.headers["content-type"]
    assert "/openapi.json" in docs.text
    redoc = client.get("/redoc")
    assert redoc.status_code == 200
    assert "/openapi.json" in redoc.text


def test_delivery_payloads_match_the_openapi_models(app, client, admin):
    define(client, admin)
    define(
        client,
        admin,
        "sitePost",
        fields=[{"name": "title", "type": "text", "required": True}, {"name": "body", "type": "richText"}],
    )
    with app.state.db.begin() as session:
        session.add(
            Asset(
                id="visible",
                project_id=admin["x-moss-project"],
                name="visible",
                key="visible",
                storage="local",
                mime="image/png",
                size=4,
                width=640,
                height=480,
                variants=[{"width": 320, "height": 240, "size": 2}],
            )
        )
    published = entry(client, admin, "alpha", {"title": "Alpha", "body": "![Cover](asset:visible)"}, "published")[
        "data"
    ]["saveEntry"]
    post = entry(client, admin, "old-post", {"title": "Old", "body": "text"}, "published", key="sitePost")["data"][
        "saveEntry"
    ]
    moved = entry(
        client,
        admin,
        "new-post",
        {"title": "New", "body": "text"},
        "published",
        key="sitePost",
        id=post["id"],
        version=post["version"],
    )
    assert "errors" not in moved, moved
    token = delivery(client, admin)
    types = client.get("/delivery/types", headers=token)
    assert types.status_code == 200, types.text
    TYPES.validate_python(types.json())
    ContentTypeDocument.model_validate(client.get("/delivery/types/article", headers=token).json())
    page = client.get("/delivery/entries", headers=token)
    EntryPage.model_validate(page.json())
    assert "total" not in page.json()
    counted = client.get("/delivery/entries", headers=token, params={"total": "true"})
    assert isinstance(counted.json()["total"], int)
    EntryPage.model_validate(counted.json())
    EntryDocument.model_validate(client.get("/delivery/entries/" + published["id"], headers=token).json())
    assets = client.get("/delivery/entries/" + published["id"] + "/resolved-assets", headers=token)
    assert assets.status_code == 200, assets.text
    assert assets.json() and "etag" not in assets.headers
    ASSETS.validate_python(assets.json())
    redirects = client.get("/delivery/website/redirects", headers=token)
    assert redirects.json()
    REDIRECTS.validate_python(redirects.json())
    PATHS.validate_python(client.get("/delivery/website/reserved-paths", headers=token).json())
    unknown = client.get("/delivery/entries", headers=token, params={"status": "draft"})
    ErrorBody.model_validate(unknown.json())
    missing = client.get("/delivery/entries/missing", headers=token)
    ErrorBody.model_validate(missing.json())
