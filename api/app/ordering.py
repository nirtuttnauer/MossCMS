"""Scalar ORDER BY with indexed values, stable IDs and a separate null tail."""

import base64
import json
from datetime import date

from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.orm import aliased

from .indexing import SCALARS, SORT_PREFIX_BYTES
from .models import Entry, EntryFieldIndex
from .security import CmsError


def field_page(session, identity, definition, query, order_by, first, after):
    field = next((field for field in definition.fields if field["name"] == order_by["field"]), None)
    if (
        field is None
        or field["type"] not in SCALARS
        or field.get("localized")
        or (identity.get("delivery") and field.get("private"))
    ):
        raise CmsError("Order by a visible, non-localized scalar field.")
    descending = order_by["direction"] == "desc"
    snapshot = "published" if identity.get("delivery") else "draft"
    metadata = [identity["project_id"], definition.id, field["name"], field["type"], snapshot, order_by["direction"]]
    cursor = None
    if after:
        try:
            if len(after) > 1024 * 1024:
                raise ValueError()
            cursor = json.loads(base64.b64decode(after, altchars=b"-_", validate=True))
            if (
                cursor["scope"] != metadata
                or not isinstance(cursor["id"], str)
                or len(cursor["id"]) > 100
                or "\0" in cursor["id"]
                or type(cursor["null"]) is not bool
            ):
                raise ValueError()
            cursor["id"].encode("utf-8")
            if not cursor["null"]:
                if field["type"] == "date":
                    if type(cursor["value"]) is not int or not 1 <= cursor["value"] <= date.max.toordinal():
                        raise ValueError()
                else:
                    cursor["value"] = base64.b64decode(cursor["value"], validate=True)
        except Exception as exc:
            raise CmsError("Invalid page cursor.") from exc
    index = aliased(EntryFieldIndex)
    scope = (
        index.project_id == identity["project_id"],
        index.type_id == definition.id,
        index.snapshot == snapshot,
        index.field == field["name"],
    )
    prefix = index.date_key if field["type"] == "date" else index.sort_prefix
    long = (
        field["type"] != "date"
        and session.scalar(select(index.entry_id).where(*scope, index.sort_long.is_(True)).limit(1)) is not None
    )
    value = func.coalesce(index.sort_key, index.sort_prefix) if long else prefix
    selected = query.join(index, and_(index.entry_id == Entry.id, *scope)).where(prefix.is_not(None))
    keys = [prefix, value, index.entry_id] if long else [prefix, index.entry_id]
    selected = selected.order_by(*(key.desc() if descending else key.asc() for key in keys))
    rows = []
    if cursor is None or not cursor["null"]:
        if cursor is not None:
            raw = cursor["value"]
            cutoff = raw if field["type"] == "date" else raw[:SORT_PREFIX_BYTES]
            values = [cutoff, raw, cursor["id"]] if long else [cutoff, cursor["id"]]
            boundary = tuple_(*values)
            selected = selected.where(tuple_(*keys) < boundary if descending else tuple_(*keys) > boundary)
        rows = [
            (record, raw, False) for record, raw in session.execute(selected.add_columns(value).limit(first + 1)).all()
        ]
    if len(rows) < first + 1:
        nonnull = select(index.entry_id).where(*scope, prefix.is_not(None))
        missing = query.where(Entry.id.not_in(nonnull)).order_by(Entry.id.desc() if descending else Entry.id.asc())
        if cursor is not None and cursor["null"]:
            missing = missing.where(Entry.id < cursor["id"] if descending else Entry.id > cursor["id"])
        rows += [(record, None, True) for record in session.scalars(missing.limit(first + 1 - len(rows))).all()]
    items = rows[:first]
    end_cursor = None
    if items:
        last, raw, null = items[-1]
        encoded = None if null else raw if field["type"] == "date" else base64.b64encode(raw).decode()
        end_cursor = base64.urlsafe_b64encode(
            json.dumps({"scope": metadata, "id": last.id, "null": null, "value": encoded}).encode()
        ).decode()
    return [record for record, _, _ in items], end_cursor, len(rows) > first
