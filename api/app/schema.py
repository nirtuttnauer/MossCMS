"""Content field schemas, value validation and public-data projection."""

import json
import re
from datetime import date

from .images import RASTER_MIMES
from .models import Asset, ContentType, Entry
from .security import CmsError

KINDS = {"text", "richText", "number", "boolean", "date", "enum", "object", "list", "reference", "asset"}
NAME = re.compile(r"^[a-z][a-zA-Z0-9_]{0,59}$")
LOCALE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")


def validate_fields(fields, depth=0, named=True):
    if depth > 5 or not isinstance(fields, list) or not 1 <= len(fields) <= 40:
        raise CmsError("Use 1–40 fields per object and at most five nesting levels.")
    names = set()
    for f in fields:
        if not isinstance(f, dict) or not isinstance(f.get("type"), str) or f.get("type") not in KINDS:
            raise CmsError("Each field must specify a supported type.")
        if named:
            name = f.get("name", "")
            if (
                not isinstance(name, str)
                or not NAME.fullmatch(name)
                or name in names
                or name in {"id", "slug", "status", "version", "updatedAt", "_data"}
            ):
                raise CmsError(f"Invalid, reserved, or duplicate field name: {name}")
            names.add(name)
        for flag in ("required", "localized", "private", "imageOnly"):
            if flag in f and not isinstance(f[flag], bool):
                raise CmsError(f"{flag} must be a boolean.")
        if f["type"] == "object":
            validate_fields(f.get("fields"), depth + 1)
        if f["type"] == "list":
            validate_fields([f.get("item")], depth + 1, named=False)
        if f["type"] == "enum":
            options = f.get("options")
            if (
                not isinstance(options, list)
                or not options
                or len(options) > 40
                or any(not isinstance(x, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,50}", x) for x in options)
                or len(set(options)) != len(options)
            ):
                raise CmsError("Enum options must be unique GraphQL identifiers.")


def validate_value(f, value, session, project_id, path):
    if value is None:
        if f.get("required"):
            raise CmsError(f"{path} is required.", field_path=path, reason="required")
        return
    if f.get("localized"):
        if (
            not isinstance(value, dict)
            or not value
            or any(not isinstance(k, str) or not LOCALE.fullmatch(k) for k in value)
        ):
            raise CmsError(
                f"{path} must be a map of locale codes to values.", field_path=path, reason="invalid_locale_map"
            )
        for locale, translated in value.items():
            validate_value({**f, "localized": False}, translated, session, project_id, f"{path}.{locale}")
        return
    kind = f["type"]
    good = True
    if kind in {"text", "richText"}:
        good = isinstance(value, str) and len(value) <= 100000
    elif kind == "number":
        import math

        good = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    elif kind == "boolean":
        good = isinstance(value, bool)
    elif kind == "date":
        try:
            date.fromisoformat(value)
        except (ValueError, TypeError):
            good = False
    elif kind == "enum":
        good = value in f["options"]
    elif kind == "object":
        validate_data(f["fields"], value, session, project_id, path)
    elif kind == "list":
        good = isinstance(value, list) and len(value) <= 1000
        if good:
            for i, item in enumerate(value):
                validate_value(f["item"], item, session, project_id, f"{path}[{i}]")
    elif kind in {"reference", "asset"}:
        model = Entry if kind == "reference" else Asset
        record = session.get(model, value) if isinstance(value, str) else None
        good = record is not None and record.project_id == project_id
        if good and record is not None and kind == "asset" and f.get("imageOnly"):
            good = record.mime in RASTER_MIMES
        if good and record is not None and kind == "reference":
            good = record.status != "deleted"
            if f.get("target"):
                good = good and session.get(ContentType, record.type_id).key == f["target"]
    if not good:
        raise CmsError(f"{path} is not a valid {kind} value.", field_path=path)


def validate_data(fields, data, session, project_id, path="data"):
    if not isinstance(data, dict):
        raise CmsError(f"{path} must be an object.", field_path=path)
    if len(json.dumps(data)) > 1024 * 1024:
        raise CmsError("An entry may not exceed 1 MiB.")
    known = {f["name"] for f in fields}
    unknown = set(data) - known
    if unknown:
        raise CmsError(
            f"Unknown fields: {', '.join(sorted(unknown))}",
            field_path=f"{path}.{sorted(unknown)[0]}",
            reason="unknown_field",
        )
    for f in fields:
        validate_value(f, data.get(f["name"]), session, project_id, f"{path}.{f['name']}")


def public_fields(fields):
    def project_field(field):
        field = dict(field)
        if field["type"] == "object":
            field["fields"] = public_fields(field["fields"])
        if field["type"] == "list":
            field["item"] = project_field(field["item"])
        return field

    return [project_field(field) for field in fields if not field.get("private")]


def public_value(f, value):
    if f.get("private") or value is None:
        return None
    if f.get("localized"):
        return {locale: public_value({**f, "localized": False}, v) for locale, v in value.items()}
    if f["type"] == "object":
        return public_data(f["fields"], value)
    if f["type"] == "list":
        return [public_value(f["item"], item) for item in value]
    return value


def public_data(fields, data):
    return {f["name"]: public_value(f, data.get(f["name"])) for f in fields if not f.get("private")}


def image_asset_ids(fields, data):
    ids = set()

    def walk(field, value):
        if field.get("private") or value is None:
            return
        if field.get("localized") and isinstance(value, dict):
            for translated in value.values():
                walk({**field, "localized": False}, translated)
        elif field["type"] == "richText" and isinstance(value, str):
            ids.update(re.findall(r"asset:([A-Za-z0-9_-]{1,100})", value))
        elif field["type"] == "asset" and isinstance(value, str):
            ids.add(value)
        elif field["type"] == "object" and isinstance(value, dict):
            for child in field.get("fields", []):
                walk(child, value.get(child["name"]))
        elif field["type"] == "list" and isinstance(value, list):
            for item in value:
                walk(field["item"], item)

    for field in fields:
        walk(field, data.get(field["name"]))
    return sorted(ids)[:50]


def reference_targets(fields):
    targets = set()
    for field in fields:
        if field["type"] == "reference" and field.get("target"):
            if not isinstance(field["target"], str):
                raise CmsError("Reference targets must be content type keys.")
            targets.add(field["target"])
        if field["type"] == "object":
            targets.update(reference_targets(field["fields"]))
        if field["type"] == "list":
            targets.update(reference_targets([field["item"]]))
    return targets
