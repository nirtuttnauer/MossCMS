"""Committed OpenAPI document for the HTTP API.

FastAPI generates the schema from the registered routes. `api/openapi.json` is that
document. The diff test fails when they diverge, so a route or model change has to
update the file in the same review.
"""

import json
import warnings
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, ConfigDict, Field

from .schema import LOCALE

OPENAPI_PATH = Path(__file__).resolve().parents[1] / "openapi.json"

OPENAPI_SUMMARY = "Editorial HTTP API and read-only delivery API"
OPENAPI_DESCRIPTION = """\
MossCMS HTTP API.

`GET /openapi.json` and `HEAD /openapi.json` return this document. The route is public: it does not take a delivery token or a session. A successful response reuses the delivery ETag helper: `Cache-Control: private, no-cache`, `Vary: Authorization, Origin`, and a strong ETag. The ETag is a quoted SHA-256 hex digest of `json.dumps(payload, sort_keys=True)` encoded as UTF-8. `If-None-Match` returns 304 with an empty body only when the header equals that quoted digest. `*`, a weak validator, and a list of validators do not match. `GET /docs` is the rendered reference for this document.

`api/openapi.json` is the reviewed copy. The API test fails when FastAPI generates a different document.

Routes under `/delivery` read published content for `Authorization: Bearer` with a delivery token. They do not accept a session cookie or a query-string token. `/delivery/entries/{id}/resolved-assets` is `Cache-Control: no-store` and has no ETag, because the signed media URLs expire. Every other successful delivery read, including `POST /delivery/graphql`, uses the ETag helper. Editorial routes use a session and stay `Cache-Control: no-store` when they are under `/auth` or `/api`.
"""

DELIVERY_BEARER = "DeliveryBearer"

CACHEABLE_PATHS = {
    "/delivery/types",
    "/delivery/types/{typeKey}",
    "/delivery/entries",
    "/delivery/entries/{id}",
    "/delivery/website/redirects",
    "/delivery/website/reserved-paths",
    "/delivery/graphql",
}
NO_STORE_PATHS = {"/delivery/entries/{id}/resolved-assets"}


class UnauthorizedBody(BaseModel):
    """401 from delivery identify. There is no code field."""

    model_config = ConfigDict(extra="forbid")
    detail: str


class ErrorBody(BaseModel):
    """Delivery error body. fieldPath and reason appear only when the error has them."""

    model_config = ConfigDict(extra="forbid")
    detail: str
    code: str
    fieldPath: list[str | int] | None = None
    reason: str | None = None


class ContentTypeDocument(BaseModel):
    """One content type with private fields removed."""

    model_config = ConfigDict(extra="forbid")
    id: str
    key: str
    name: str
    fields: list[dict[str, Any]]
    version: int


class EntryDocument(BaseModel):
    """Published entry. Delivery nulls the draft and schedule channels."""

    model_config = ConfigDict(extra="forbid")
    id: str
    typeKey: str
    slug: str
    title: str | None
    data: dict[str, Any]
    status: Literal["published"]
    version: int
    updatedAt: str
    scheduledAt: Literal[None]
    isLive: bool
    hasUnpublishedChanges: Literal[False]
    publishedAt: str
    publishedRevision: int
    scheduledRevision: Literal[None]
    scheduleError: Literal[None]
    publishedData: Literal[None]
    publishedSlug: Literal[None]
    publishedTitle: Literal[None]
    publishedSnapshot: Literal[None]


class EntryPage(BaseModel):
    """One delivery page. total is present only when the request sets total=true."""

    model_config = ConfigDict(extra="forbid")
    nodes: list[EntryDocument]
    endCursor: str | None
    hasNextPage: bool
    total: int | None = None


class VariantDocument(BaseModel):
    """Signed rendition. The URL expires."""

    model_config = ConfigDict(extra="forbid")
    width: int
    height: int
    size: int
    url: str


class AssetDocument(BaseModel):
    """Signed original and renditions for one published image. Not cacheable."""

    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    mime: str
    size: int
    url: str
    width: int | None
    height: int | None
    variants: list[VariantDocument]


class RedirectDocument(BaseModel):
    """A live entry's former public path."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_: str = Field(alias="from")
    to: str
    entryId: str


def _error_responses(*, cacheable: bool) -> dict[int, dict[str, Any]]:
    responses: dict[int, dict[str, Any]] = {
        401: {"model": UnauthorizedBody, "description": "Missing, expired, or non-delivery credential."},
        403: {"model": ErrorBody, "description": "The delivery token is not allowed to read this."},
        404: {"model": ErrorBody, "description": "No published entry or content type is visible to the token."},
        422: {"model": ErrorBody, "description": "Unknown parameter, bad cursor, bad page, or rejected filter."},
        500: {"model": ErrorBody, "description": "The request could not be completed."},
    }
    if cacheable:
        responses[304] = {
            "description": "Not Modified. Empty body, no content type. ETag, Cache-Control, and Vary match the 200."
        }
    return responses


CACHEABLE_RESPONSES = _error_responses(cacheable=True)
NO_STORE_RESPONSES = _error_responses(cacheable=False)


def _query(name: str, schema: dict[str, Any], description: str) -> dict[str, Any]:
    return {"name": name, "in": "query", "required": False, "schema": schema, "description": description}


ENTRY_QUERY = [
    _query(
        "typeKey",
        {"type": "string"},
        "Optional content type key. Unknown keys and keys outside the token scopes are 404.",
    ),
    _query(
        "search",
        {"type": "string"},
        "Substring match against the published title and slug. A private title does not match.",
    ),
    _query(
        "sort",
        {
            "type": "string",
            "enum": ["updated_desc", "updated_asc", "title_asc", "title_desc"],
            "default": "updated_desc",
        },
        "Delivery updated_* orders by published_at. title_* uses the published slug when title is private.",
    ),
    _query(
        "first", {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}, "Page size. A non-integer is 422."
    ),
    _query("after", {"type": "string"}, "Opaque endCursor from the previous page."),
    _query(
        "filters",
        {"type": "string"},
        "JSON object of at most ten exact filters on visible non-localized scalars. At most 4096 bytes before URL decoding.",
    ),
    _query(
        "orderBy",
        {"type": "string"},
        "Visible non-localized scalar field. Requires typeKey and cannot be combined with another sort.",
    ),
    _query(
        "direction",
        {"type": "string", "enum": ["asc", "desc"]},
        "Used only with orderBy. Defaults to asc when orderBy is set.",
    ),
    _query(
        "total",
        {"type": "boolean", "default": False},
        "true adds total. Any other spelling is 422. Omitted or false leaves total out of the body.",
    ),
    _query(
        "locale",
        {"type": "string", "pattern": LOCALE.pattern},
        "Selects that locale from every localized public field. No fallback. Omitted, locale maps stay maps.",
    ),
]
ITEM_QUERY = [ENTRY_QUERY[-1]]
IF_NONE_MATCH = {
    "name": "If-None-Match",
    "in": "header",
    "required": False,
    "schema": {"type": "string"},
    "description": "Quoted strong ETag. An exact match returns 304. *, weak validators, and lists do not match.",
}
ETAG_HEADERS = {
    "ETag": {
        "description": "Quoted SHA-256 of json.dumps(payload, sort_keys=True) encoded as UTF-8.",
        "schema": {"type": "string"},
    },
    "Cache-Control": {"schema": {"type": "string", "const": "private, no-cache"}},
    "Vary": {
        "description": "The helper sets Authorization, Origin. CORS appends Origin again, same as other delivery responses.",
        "schema": {"type": "string"},
    },
}
NO_STORE_HEADERS = {
    "Cache-Control": {"schema": {"type": "string", "const": "no-store"}},
    "Vary": {
        "description": "The helper sets Authorization, Origin. CORS appends Origin again, same as other delivery responses.",
        "schema": {"type": "string"},
    },
}


def canonical_openapi(schema: dict[str, Any]) -> str:
    """Stable text for review. Key order in the generated dict is not part of the contract."""
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def _suffix_operation_id(operation_id: str, method: str) -> str:
    """GET and HEAD share one route operation id. The published id names the method."""
    if operation_id.endswith(f"_{method}"):
        return operation_id
    return f"{operation_id}_{method}"


def _extend_parameters(operation: dict[str, Any], extra: list[dict[str, Any]]) -> None:
    if not extra:
        return
    current = operation.setdefault("parameters", [])
    operation["parameters"] = [*current, *json.loads(json.dumps(extra))]


def apply_delivery_contract(schema: dict[str, Any]) -> None:
    """Document delivery auth and cache headers without changing route validation."""
    components = schema.setdefault("components", {})
    schemes = components.setdefault("securitySchemes", {})
    schemes[DELIVERY_BEARER] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "delivery-token",
        "description": "Raw delivery token. A session token, cookie, or query parameter is rejected.",
    }
    graphql = {
        "/graphql": (
            "Editorial GraphQL",
            "Session cookie, X-Moss-Project, and X-Moss-CSRF for mutations. Responses are not ETag-cached.",
        ),
        "/delivery/graphql": (
            "Delivery GraphQL",
            "Bearer delivery token. Published content only. The delivery schema has no mutations. "
            "A successful response uses the delivery ETag.",
        ),
    }
    for path, operations in schema.get("paths", {}).items():
        for method, operation in operations.items():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            operation["operationId"] = _suffix_operation_id(operation["operationId"], method)
            if path not in CACHEABLE_PATHS and path not in NO_STORE_PATHS and path not in graphql:
                continue
            if path.startswith("/delivery/"):
                operation["security"] = [{DELIVERY_BEARER: []}]
            if path in graphql:
                operation["summary"], operation["description"] = graphql[path]
            if path in CACHEABLE_PATHS:
                if path == "/delivery/entries":
                    _extend_parameters(operation, ENTRY_QUERY)
                elif path == "/delivery/entries/{id}":
                    _extend_parameters(operation, ITEM_QUERY)
                _extend_parameters(operation, [IF_NONE_MATCH])
                success = operation.setdefault("responses", {}).setdefault("200", {})
                success.setdefault("headers", {}).update(json.loads(json.dumps(ETAG_HEADERS)))
                not_modified = operation.setdefault("responses", {}).setdefault("304", {})
                not_modified.setdefault(
                    "description",
                    "Not Modified. Empty body, no content type. ETag, Cache-Control, and Vary match the 200.",
                )
                not_modified.setdefault("headers", {}).update(json.loads(json.dumps(ETAG_HEADERS)))
            if path in NO_STORE_PATHS:
                success = operation.setdefault("responses", {}).setdefault("200", {})
                success.setdefault("headers", {}).update(json.loads(json.dumps(NO_STORE_HEADERS)))
            if method == "head":
                for status in ("200", "304"):
                    response = operation.get("responses", {}).get(status)
                    if isinstance(response, dict):
                        response.pop("content", None)


def build_openapi(app: FastAPI) -> dict[str, Any]:
    """Schema FastAPI generates for the current routes, plus the delivery contract notes."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=r"Duplicate Operation ID", category=UserWarning)
        schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            summary=app.summary,
            description=app.description,
            routes=app.routes,
            webhooks=app.webhooks.routes,
            tags=app.openapi_tags,
            servers=app.servers,
            terms_of_service=app.terms_of_service,
            contact=app.contact,
            license_info=app.license_info,
            separate_input_output_schemas=app.separate_input_output_schemas,
            external_docs=app.openapi_external_docs,
        )
    apply_delivery_contract(schema)
    return schema
