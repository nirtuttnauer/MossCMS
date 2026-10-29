"""Cacheable delivery REST reads. They call the delivery helpers unchanged."""

import hashlib
import json
import logging
import re
import urllib.parse

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse

from . import content
from .graphql import resolved_image_assets
from .models import ContentType
from .schema import public_fields
from .security import CmsError, identify, require

logger = logging.getLogger("mosscms")

# Byte length of the filters query value as it appears in the request, before URL-decoding.
MAX_FILTERS_BYTES = 4096
ENTRY_PARAMETERS = {"typeKey", "search", "sort", "first", "after", "filters", "orderBy", "direction", "total"}
PAGE_SIZE = "Use a page size of 1–100 and a supported sort order."


def delivery_etag(payload) -> str:
    """Quoted SHA-256 of the canonical JSON payload. Shared with delivery GraphQL."""
    return '"' + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest() + '"'


def filters_measured_length(raw: bytes) -> int:
    """Bytes of the filters value before URL-decoding and before JSON parsing."""
    return len(raw)


def parse_filters(value: str):
    """JSON-parse a filters query value. Callers enforce MAX_FILTERS_BYTES first."""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise CmsError("Filters must be a JSON object.") from exc
    if type(parsed) is not dict:
        raise CmsError("Filters must be a JSON object.")
    return parsed


def delivery_representation(request, payload, *, cacheable: bool):
    headers = {
        "Cache-Control": "private, no-cache" if cacheable else "no-store",
        "Vary": "Authorization, Origin",
    }
    if cacheable:
        headers["ETag"] = delivery_etag(payload)
        if request.headers.get("if-none-match") == headers["ETag"]:
            return Response(status_code=304, headers=headers)
    if request.method == "HEAD":
        return Response(status_code=200, headers=headers)
    return JSONResponse(payload, headers=headers)


def error_response(status, body):
    return JSONResponse(
        body,
        status_code=status,
        headers={"Cache-Control": "no-store", "Vary": "Authorization, Origin"},
    )


def _query_parts(query_string: bytes):
    for part in query_string.split(b"&"):
        if not part:
            continue
        key, separator, value = part.partition(b"=")
        try:
            name = urllib.parse.unquote_to_bytes(key).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CmsError("Unknown delivery parameter.") from exc
        yield name, value if separator else b""


def ensure_known_parameters(request, allowed: set[str]) -> None:
    names = [name for name, _ in _query_parts(request.scope.get("query_string", b""))]
    if any(name not in allowed for name in names) or len(names) != len(set(names)):
        raise CmsError("Unknown delivery parameter.")


def load_filters(query_string: bytes):
    values = [value for name, value in _query_parts(query_string) if name == "filters"]
    if not values:
        return None
    if len(values) != 1:
        raise CmsError("Unknown delivery parameter.")
    raw = values[0]
    if filters_measured_length(raw) > MAX_FILTERS_BYTES:
        raise CmsError("Filters value is too long.")
    try:
        decoded = urllib.parse.unquote_to_bytes(raw).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CmsError("Filters must be a JSON object.") from exc
    return parse_filters(decoded)


def parse_first(value: str | None) -> int:
    if value is None:
        return 20
    if not re.fullmatch(r"[0-9]{1,3}", value):
        raise CmsError(PAGE_SIZE)
    number = int(value)
    if not 1 <= number <= 100:
        raise CmsError(PAGE_SIZE)
    return number


def type_document(record):
    return {
        "id": record.id,
        "key": record.key,
        "name": record.name,
        "fields": public_fields(record.fields),
        "version": record.version,
    }


def asset_document(asset):
    return {
        "id": str(asset.id),
        "name": asset.name,
        "mime": asset.mime,
        "size": asset.size,
        "url": asset.url,
        "width": asset.width,
        "height": asset.height,
        "variants": asset.variants,
    }


def types_payload(context):
    ensure_known_parameters(context["request"], set())
    session = context["session"]
    rows = session.scalars(content.scoped(session, ContentType, context).order_by(ContentType.name)).all()
    return [type_document(row) for row in rows if not context["scopes"] or row.key in context["scopes"]]


def type_payload(context, key):
    ensure_known_parameters(context["request"], set())
    return type_document(content.get_type(context["session"], context, key))


def entries_payload(context):
    request = context["request"]
    ensure_known_parameters(request, ENTRY_PARAMETERS)
    params = request.query_params
    filters = load_filters(request.scope.get("query_string", b""))
    order_name = params.get("orderBy")
    direction = params.get("direction")
    if direction is not None and order_name is None:
        raise CmsError("direction requires orderBy.")
    if order_name is not None and direction is None:
        direction = "asc"
    if direction is not None and direction not in {"asc", "desc"}:
        raise CmsError("Use direction asc or desc.")
    total = params.get("total")
    if total is None or total == "false":
        include_total = False
    elif total == "true":
        include_total = True
    else:
        raise CmsError("total must be true or false.")
    page = content.entry_page(
        context["session"],
        context,
        type_key=params.get("typeKey"),
        search=params.get("search") or "",
        sort=params.get("sort") or "updated_desc",
        first=parse_first(params.get("first")),
        after=params.get("after"),
        filters=filters,
        order_by={"field": order_name, "direction": direction} if order_name else None,
        include_total=include_total,
    )
    body = {"nodes": page["nodes"], "endCursor": page["endCursor"], "hasNextPage": page["hasNextPage"]}
    if include_total:
        body["total"] = page["total"]
    return body


def entry_payload(context, entry_id):
    ensure_known_parameters(context["request"], set())
    session = context["session"]
    return content.entry_dict(session, context, content.get_entry(session, context, entry_id))


def resolved_payload(context, entry_id):
    ensure_known_parameters(context["request"], set())
    session = context["session"]
    record = content.get_entry(session, context, entry_id)
    definition = session.get(ContentType, record.type_id)
    data = record.published_data if context.get("delivery") else record.data
    assets = resolved_image_assets(session, context, definition.fields, data or {}, context["settings"])
    return [asset_document(asset) for asset in assets]


def redirects_payload(context):
    ensure_known_parameters(context["request"], set())
    return content.website_redirects(context["session"], context)


def reserved_payload(context):
    ensure_known_parameters(context["request"], set())
    return content.website_reserved_paths(context["session"], context)


def delivery_call(factory, settings, request, build, *, cacheable):
    with factory() as session:
        try:
            identity = identify(request, session, delivery=True)
            context = {**identity, "session": session, "settings": settings, "request": request}
            require(context)
            payload = build(context)
            session.commit()
        except HTTPException as exc:
            session.rollback()
            detail = exc.detail
            return error_response(exc.status_code, detail if isinstance(detail, dict) else {"detail": detail})
        except CmsError as exc:
            session.rollback()
            status = {"FORBIDDEN": 403, "NOT_FOUND": 404, "CONFLICT": 409}.get(exc.code, 422)
            return error_response(status, {"detail": str(exc), **exc.extensions()})
        except Exception as exc:
            session.rollback()
            logger.error(
                json.dumps(
                    {
                        "requestId": getattr(request.state, "request_id", None),
                        "operation": "delivery",
                        "errorType": type(exc).__name__,
                    }
                )
            )
            return error_response(500, {"detail": "The request could not be completed.", "code": "INTERNAL"})
    return delivery_representation(request, payload, cacheable=cacheable)


def register_delivery_routes(app, factory, settings):
    def call(request, build, *, cacheable):
        return delivery_call(factory, settings, request, build, cacheable=cacheable)

    @app.api_route("/delivery/types", methods=["GET", "HEAD"])
    def delivery_types(request: Request):
        return call(request, types_payload, cacheable=True)

    @app.api_route("/delivery/types/{typeKey}", methods=["GET", "HEAD"])
    def delivery_type(typeKey: str, request: Request):
        return call(request, lambda context: type_payload(context, typeKey), cacheable=True)

    @app.api_route("/delivery/entries", methods=["GET", "HEAD"])
    def delivery_entries(request: Request):
        return call(request, entries_payload, cacheable=True)

    @app.api_route("/delivery/entries/{id}/resolved-assets", methods=["GET", "HEAD"])
    def delivery_resolved_assets(id: str, request: Request):
        return call(request, lambda context: resolved_payload(context, id), cacheable=False)

    @app.api_route("/delivery/entries/{id}", methods=["GET", "HEAD"])
    def delivery_entry(id: str, request: Request):
        return call(request, lambda context: entry_payload(context, id), cacheable=True)

    @app.api_route("/delivery/website/redirects", methods=["GET", "HEAD"])
    def delivery_redirects(request: Request):
        return call(request, redirects_payload, cacheable=True)

    @app.api_route("/delivery/website/reserved-paths", methods=["GET", "HEAD"])
    def delivery_reserved_paths(request: Request):
        return call(request, reserved_payload, cacheable=True)
