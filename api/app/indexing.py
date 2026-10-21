"""Transactional scalar-filter projections; stored content remains the source of truth."""

import hashlib
import math
from datetime import date
from decimal import Decimal

from sqlalchemy import LargeBinary, MetaData, Table, and_, delete, insert, inspect, or_, select

SORT_PREFIX_BYTES = 1024
SCALARS = {"text", "richText", "enum", "number", "boolean", "date"}


def scalar_fields(fields):
    return {field["name"] for field in fields if field["type"] in SCALARS and not field.get("localized")}


def order_keys(value):
    date_key = None
    if isinstance(value, bool):
        key = bytes([int(value)])
    elif isinstance(value, (int, float)):
        number = Decimal(value)
        if number == 0:
            key = b"\x80"
        else:
            sign, digits, exponent = number.as_tuple()
            adjusted = len(digits) + int(exponent) - 1
            coefficient = bytes(48 + digit for digit in digits).rstrip(b"0")
            magnitude = (adjusted + 1024).to_bytes(2, "big") + coefficient + b"\x00"
            key = b"\x7f" + bytes(255 - byte for byte in magnitude) if sign else b"\x81" + magnitude
    else:
        key = value.encode("utf-8", errors="surrogatepass")
        if len(value) <= 32:
            try:
                date_key = date.fromisoformat(value).toordinal()
            except ValueError:
                pass
    return {
        "sort_key": key,
        "sort_prefix": key[:SORT_PREFIX_BYTES],
        "sort_long": len(key) > SORT_PREFIX_BYTES,
        "date_key": date_key,
    }


def scalar_hash(value):
    if isinstance(value, bool):
        encoded = "b:1" if value else "b:0"
    elif isinstance(value, (int, float)):
        try:
            number = float(value)
        except OverflowError:
            return None
        if not math.isfinite(number):
            return None
        encoded = "n:" + (0.0 if number == 0 else number).hex()
    elif isinstance(value, str):
        encoded = "s:" + value
    else:
        return None
    return hashlib.sha256(encoded.encode("utf-8", errors="surrogatepass")).hexdigest()


def index_rows(entry, snapshots=("draft", "published"), binary_hash=True, fields=None):
    rows = []
    for snapshot in snapshots:
        data = entry["data" if snapshot == "draft" else "published_data"] or {}
        for field, value in data.items():
            if fields is not None and field not in fields:
                continue
            digest = scalar_hash(value)
            if digest is not None:
                keys = order_keys(value)
                if not keys["sort_long"]:
                    keys["sort_key"] = None
                rows.append(
                    dict(
                        entry_id=entry["id"],
                        project_id=entry["project_id"],
                        type_id=entry["type_id"],
                        snapshot=snapshot,
                        field=field,
                        value_hash=bytes.fromhex(digest) if binary_hash else digest,
                        **keys,
                    )
                )
    return rows


def sync_entry(mapper, connection, entry):
    from .models import ContentType, EntryFieldIndex

    state = inspect(entry)
    override = entry.__dict__.pop("_scalar_index_fields", None)
    scope_changed = (
        state.attrs.project_id.history.has_changes()
        or state.attrs.type_id.history.has_changes()
        or override is not None
    )
    snapshots = [
        snapshot
        for snapshot, attribute in (("draft", "data"), ("published", "published_data"))
        if state.pending or scope_changed or state.attrs[attribute].history.has_changes()
    ]
    if not snapshots:
        return
    values = {key: getattr(entry, key) for key in ("id", "project_id", "type_id", "data", "published_data")}
    clauses = []
    for snapshot in snapshots:
        attribute = "data" if snapshot == "draft" else "published_data"
        history = state.attrs[attribute].history
        if scope_changed or state.pending or not history.deleted:
            clauses.append(EntryFieldIndex.snapshot == snapshot)
            continue
        old, current = history.deleted[0] or {}, values[attribute] or {}
        changed = [
            field
            for field in old.keys() | current.keys()
            if (type(old.get(field)) is not type(current.get(field)) or old.get(field) != current.get(field))
            and (scalar_hash(old.get(field)) is not None or scalar_hash(current.get(field)) is not None)
        ]
        values[attribute] = {field: current[field] for field in changed if field in current}
        if changed:
            clauses.append(and_(EntryFieldIndex.snapshot == snapshot, EntryFieldIndex.field.in_(changed)))
    if not clauses:
        return
    connection.execute(delete(EntryFieldIndex).where(EntryFieldIndex.entry_id == entry.id, or_(*clauses)))
    fields = override
    if fields is None:
        definition = state.session.identity_map.get((ContentType, (entry.type_id,), None))
        schema = (
            definition.fields
            if definition is not None
            else connection.scalar(select(ContentType.fields).where(ContentType.id == entry.type_id))
        )
        fields = scalar_fields(schema)
    rows = index_rows(values, snapshots, fields=fields)
    if rows:
        connection.execute(insert(EntryFieldIndex), rows)


def remove_entry(mapper, connection, entry):
    from .models import EntryFieldIndex

    connection.execute(delete(EntryFieldIndex).where(EntryFieldIndex.entry_id == entry.id))


def rebuild(connection, entries, index, project_id=None, clear_existing=True):
    """Backfill in bounded batches; row locks serialize a repair with CMS writes."""
    definitions = Table("content_types", MetaData(), autoload_with=connection)
    last, count = "", 0
    while True:
        query = (
            select(*(entries.c[key] for key in ("id", "project_id", "type_id", "data", "published_data")))
            .where(entries.c.id > last)
            .order_by(entries.c.id)
            .limit(100)
            .with_for_update()
        )
        if project_id is not None:
            query = query.where(entries.c.project_id == project_id)
        batch = connection.execute(query).mappings().all()
        if not batch:
            return count
        if clear_existing:
            connection.execute(delete(index).where(index.c.entry_id.in_([entry["id"] for entry in batch])))
        fields = {
            type_id: scalar_fields(definition)
            for type_id, definition in connection.execute(
                select(definitions.c.id, definitions.c.fields).where(
                    definitions.c.id.in_({entry["type_id"] for entry in batch})
                )
            )
        }
        # Historical migrations backfill the projection before newer columns exist.
        rows = [
            {key: value for key, value in row.items() if key in index.c}
            for entry in batch
            for row in index_rows(
                entry, binary_hash=isinstance(index.c.value_hash.type, LargeBinary), fields=fields[entry["type_id"]]
            )
        ]
        if rows:
            connection.execute(index.insert(), rows)
        count += len(batch)
        last = batch[-1]["id"]


def indexed_value(field, value):
    # Other coercions and null/missing comparisons retain the original JSON query.
    kind = field["type"]
    compatible = (
        (kind in {"text", "richText", "enum", "date"} and isinstance(value, str))
        or (kind == "number" and isinstance(value, (int, float)) and not isinstance(value, bool))
        or (kind == "boolean" and isinstance(value, bool))
    )
    return scalar_hash(value) if compatible else None
