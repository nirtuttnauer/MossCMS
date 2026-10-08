"""Project-scoped content operations, schema validation and publishing."""

import hashlib
import base64
import json
import re
from copy import deepcopy
from datetime import date, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from .models import Asset, ContentType, DraftReceipt, Entry, Revision, SchemaRevision, now
from .security import CmsError, audit, require

KINDS = {"text", "richText", "number", "boolean", "date", "enum", "object", "list", "reference", "asset"}
NAME = re.compile(r"^[a-z][a-zA-Z0-9_]{0,59}$")
LOCALE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")


def slugify(value):
    result = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not result or len(result) > 220:
        raise CmsError("Slug must contain letters or numbers and be at most 220 characters.")
    return result


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
        for flag in ("required", "localized", "private"):
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
            raise CmsError(f"{path} is required.")
        return
    if f.get("localized"):
        if not isinstance(value, dict) or not value or any(not LOCALE.fullmatch(k) for k in value):
            raise CmsError(f"{path} must be a map of locale codes to values.")
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
        if good and record is not None and kind == "reference":
            good = record.status != "deleted"
            if f.get("target"):
                good = good and session.get(ContentType, record.type_id).key == f["target"]
    if not good:
        raise CmsError(f"{path} is not a valid {kind} value.")


def validate_data(fields, data, session, project_id, path="data"):
    if not isinstance(data, dict):
        raise CmsError(f"{path} must be an object.")
    if len(json.dumps(data)) > 1024 * 1024:
        raise CmsError("An entry may not exceed 1 MiB.")
    known = {f["name"] for f in fields}
    unknown = set(data) - known
    if unknown:
        raise CmsError(f"Unknown fields: {', '.join(sorted(unknown))}")
    for f in fields:
        validate_value(f, data.get(f["name"]), session, project_id, f"{path}.{f['name']}")


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


def scoped(session, model, identity):
    return select(model).where(model.project_id == identity["project_id"])


def get_type(session, identity, key):
    record = session.scalar(scoped(session, ContentType, identity).where(ContentType.key == key))
    if record is None or (identity.get("delivery") and identity["scopes"] and key not in identity["scopes"]):
        raise CmsError("Content type not found.", "NOT_FOUND")
    return record


def get_entry(session, identity, id):
    record = session.get(Entry, id)
    if (
        not record
        or record.project_id != identity["project_id"]
        or (identity.get("delivery") and (record.published_slug is None or record.status == "deleted"))
    ):
        raise CmsError("Entry not found.", "NOT_FOUND")
    get_type(session, identity, session.get(ContentType, record.type_id).key)
    return record


def entry_dict(session, identity, record):
    definition = session.get(ContentType, record.type_id)
    delivery = identity.get("delivery")
    data = record.published_data or {} if identity.get("delivery") else record.data
    if identity.get("delivery"):
        data = public_data(definition.fields, data)
    return {
        "id": record.id,
        "typeKey": definition.key,
        "slug": record.published_slug if delivery else record.slug,
        "title": record.published_title if delivery else record.title,
        "data": data,
        "status": "published" if delivery else record.status,
        "version": record.published_revision if delivery else record.version,
        "updatedAt": (record.published_at if delivery else record.updated_at).isoformat() + "Z",
        "scheduledAt": None if delivery else record.scheduled_at.isoformat() + "Z" if record.scheduled_at else None,
        "isLive": record.published_slug is not None,
        "hasUnpublishedChanges": False
        if delivery
        else (
            record.published_slug is None
            or record.slug != record.published_slug
            or record.title != record.published_title
            or record.data != record.published_data
        ),
        "publishedAt": record.published_at.isoformat() + "Z" if record.published_at else None,
        "publishedRevision": record.published_revision,
        "scheduledRevision": None if delivery else record.scheduled_revision,
        "scheduleError": None if delivery else record.schedule_error,
    }


def entry_page(
    session, identity, type_key=None, status=None, search="", sort="updated_desc", first=20, after=None, filters=None
):
    require(identity)
    if not 1 <= first <= 100 or sort not in {"updated_desc", "updated_asc", "title_asc", "title_desc"}:
        raise CmsError("Use a page size of 1–100 and a supported sort order.")
    query = scoped(session, Entry, identity)
    if identity.get("delivery"):
        query = query.where(Entry.published_slug.is_not(None), Entry.status != "deleted")
        if identity["scopes"]:
            query = query.where(
                Entry.type_id.in_(
                    select(ContentType.id).where(
                        ContentType.project_id == identity["project_id"], ContentType.key.in_(identity["scopes"])
                    )
                )
            )
    elif status:
        if status not in {"draft", "published", "scheduled", "deleted"}:
            raise CmsError("Unknown status.")
        query = query.where(editorial_condition(status))
    else:
        query = query.where(Entry.status != "deleted")
    if type_key:
        query = query.where(Entry.type_id == get_type(session, identity, type_key).id)
    if search:
        safe = search[:100].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(
            or_(
                (Entry.published_title if identity.get("delivery") else Entry.title).ilike(f"%{safe}%", escape="\\"),
                (Entry.published_slug if identity.get("delivery") else Entry.slug).ilike(f"%{safe}%", escape="\\"),
            )
        )
    if filters:
        if not type_key or not isinstance(filters, dict) or len(filters) > 10:
            raise CmsError("Field filters require a content type and at most ten exact-match fields.")
        fields = {f["name"]: f for f in get_type(session, identity, type_key).fields}
        for key, value in filters.items():
            if (
                key not in fields
                or fields[key].get("localized")
                or fields[key]["type"] not in {"text", "richText", "number", "boolean", "date", "enum"}
                or (identity.get("delivery") and fields[key].get("private"))
            ):
                raise CmsError("Filter on a visible scalar field.")
            if value is not None and not isinstance(value, (str, bool, int, float)):
                raise CmsError("Filter values must be scalars.")
            if isinstance(value, str) and len(value) > 10000:
                raise CmsError("Filter value is too long.")
            target = Entry.published_data if identity.get("delivery") else Entry.data
            expr = (
                target[key].as_boolean()
                if isinstance(value, bool)
                else target[key].as_float()
                if isinstance(value, (int, float))
                else target[key].as_string()
            )
            query = query.where(expr == value)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    attr = (
        (Entry.published_title if identity.get("delivery") else Entry.title)
        if sort.startswith("title")
        else Entry.published_at
        if identity.get("delivery")
        else Entry.updated_at
    )
    descending = sort.endswith("desc")
    if after:
        try:
            if len(after) > 1000:
                raise ValueError()
            value, id, cursor_sort = json.loads(base64.urlsafe_b64decode(after.encode()))
            if cursor_sort != sort:
                raise ValueError()
            if not sort.startswith("title"):
                value = datetime.fromisoformat(value)
        except Exception as exc:
            raise CmsError("Invalid page cursor.") from exc
        query = query.where(
            or_(
                attr < value if descending else attr > value,
                and_(attr == value, Entry.id < id if descending else Entry.id > id),
            )
        )
    rows = session.scalars(
        query.order_by(
            attr.desc() if descending else attr.asc(), Entry.id.desc() if descending else Entry.id.asc()
        ).limit(first + 1)
    ).all()
    items = rows[:first]
    cursor = None
    if items:
        last = items[-1]
        value = (
            (last.published_title if identity.get("delivery") else last.title)
            if sort.startswith("title")
            else (last.published_at if identity.get("delivery") else last.updated_at).isoformat()
        )
        cursor = base64.urlsafe_b64encode(json.dumps([value, last.id, sort]).encode()).decode()
    return {
        "nodes": [entry_dict(session, identity, e) for e in items],
        "total": total,
        "endCursor": cursor,
        "hasNextPage": len(rows) > first,
    }


def editorial_condition(status):
    if status == "published":
        return and_(Entry.published_slug.is_not(None), Entry.status != "deleted")
    if status == "scheduled":
        return and_(Entry.scheduled_at.is_not(None), Entry.status != "deleted")
    return Entry.status == status


def content_groups(session, identity, status=None):
    require(identity)
    if identity.get("delivery"):
        raise CmsError("Content groups are editorial only.", "FORBIDDEN")
    if status and status not in {"draft", "published", "scheduled", "deleted"}:
        raise CmsError("Unknown status.")
    condition = editorial_condition(status) if status else Entry.status != "deleted"
    rows = session.execute(
        select(ContentType.key, ContentType.name, func.count(Entry.id))
        .outerjoin(
            Entry,
            and_(Entry.type_id == ContentType.id, Entry.project_id == identity["project_id"], condition),
        )
        .where(ContentType.project_id == identity["project_id"])
        .group_by(ContentType.key, ContentType.name)
        .order_by(ContentType.name)
    ).all()
    return [{"key": key, "name": name, "count": count} for key, name, count in rows]


def revision(session, identity, record):
    session.flush()
    snapshot = {
        "typeKey": session.get(ContentType, record.type_id).key,
        "slug": record.slug,
        "title": record.title,
        "data": record.data,
        "status": record.status,
        "scheduledAt": record.scheduled_at.isoformat() if record.scheduled_at else None,
        "publishedRevision": record.published_revision,
        "scheduledRevision": record.scheduled_revision,
    }
    session.add(
        Revision(
            project_id=record.project_id,
            entry_id=record.id,
            number=record.version,
            snapshot=snapshot,
            author=identity["actor"],
        )
    )


def summarize_status(record):
    if record.status != "deleted":
        record.status = "scheduled" if record.scheduled_at else "published" if record.published_slug else "draft"


def clear_schedule(record):
    record.scheduled_at = record.scheduled_data = record.scheduled_slug = record.scheduled_title = None
    record.scheduled_revision = record.scheduled_schema_version = record.schedule_error = None


def publish_snapshot(record, definition, data, slug, title, number):
    record.published_data = deepcopy(data)
    record.published_slug, record.published_title = slug, title
    record.published_at, record.published_revision = now(), number
    record.published_schema_version = definition.version
    clear_schedule(record)
    summarize_status(record)


def save_entry(
    session, identity, type_key, slug, data, status="draft", id=None, version=None, scheduled_at=None, restoring=False
):
    require(identity, "editor", write=True)
    definition = get_type(session, identity, type_key)
    validate_data(definition.fields, data, session, identity["project_id"])
    slug = slugify(slug)
    if status not in {"draft", "published", "scheduled"}:
        raise CmsError("Use draft, published, or scheduled status.")
    schedule = None
    if status == "scheduled":
        try:
            schedule = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
            if schedule.tzinfo:
                from datetime import timezone

                schedule = schedule.astimezone(timezone.utc).replace(tzinfo=None)
            if schedule <= now():
                raise ValueError()
        except (AttributeError, ValueError):
            raise CmsError("Choose a future publishing time.") from None
    record = get_entry(session, identity, id) if id else Entry(project_id=identity["project_id"], type_id=definition.id)
    if id and (record.type_id != definition.id or version != record.version):
        raise CmsError("This entry changed. Reload before saving.", "CONFLICT")
    if record.status == "deleted" and not restoring:
        raise CmsError("Restore a revision to recover a trashed entry.")
    if not id:
        session.add(record)
    record.slug = slug
    title = data.get("title", slug)
    if isinstance(title, dict):
        title = title.get("en") or next(iter(title.values()), slug)
    record.title = str(title)[:200]
    record.data = deepcopy(data)
    record.status = "draft" if restoring else status
    if status == "scheduled":
        record.scheduled_at = schedule
        record.scheduled_data = deepcopy(data)
        record.scheduled_slug, record.scheduled_title = slug, record.title
        record.scheduled_schema_version = definition.version
        record.schedule_error = None
    summarize_status(record)
    record.updated_at = now()
    record.author_id = identity["user"].id
    next_version = record.version + 1 if id else 1
    if status == "published":
        publish_snapshot(record, definition, data, slug, record.title, next_version)
    elif status == "scheduled":
        record.scheduled_revision = next_version
    revision(session, identity, record)
    audit(
        session,
        record.project_id,
        identity["actor"],
        "entry.save",
        entryId=record.id,
        version=record.version,
        status=status,
    )
    return record


def draft_receipt(session, identity, key):
    require(identity, "editor")
    receipt = session.get(DraftReceipt, (identity["project_id"], identity["user"].id, key))
    return receipt.response if receipt else None


def save_draft(session, identity, key, type_key, slug, data, id=None, version=None):
    require(identity, "editor", write=True)
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,100}", key):
        raise CmsError("Use a stable draft request key of 16–100 letters, digits, dashes or underscores.")
    payload = {"typeKey": type_key, "slug": slug, "data": data, "id": id, "version": version}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    previous = session.get(DraftReceipt, (identity["project_id"], identity["user"].id, key))
    if previous:
        if previous.fingerprint != fingerprint:
            raise CmsError("This request key was already used with different draft values.", "CONFLICT")
        return previous.response
    record = save_entry(session, identity, type_key, slug, data, "draft", id, version)
    response = entry_dict(session, identity, record)
    session.add(
        DraftReceipt(
            project_id=identity["project_id"],
            user_id=identity["user"].id,
            key=key,
            fingerprint=fingerprint,
            response=response,
        )
    )
    session.flush()
    return response


def move_entry(session, identity, id, type_key, version):
    """Change an entry's type without replacing its ID, history or publishing schedule."""
    require(identity, "admin", write=True)
    record = get_entry(session, identity, id)
    if record.version != version:
        raise CmsError("This entry changed. Reload before moving it.", "CONFLICT")
    target = get_type(session, identity, type_key)
    source = session.get(ContentType, record.type_id)
    if target.id == source.id:
        return record
    validate_data(target.fields, record.data, session, identity["project_id"])
    if record.published_data is not None:
        validate_data(target.fields, record.published_data, session, identity["project_id"])
    if record.scheduled_data is not None:
        validate_data(target.fields, record.scheduled_data, session, identity["project_id"])
    if record.published_slug:
        record.published_schema_version = target.version
    if record.scheduled_data is not None:
        record.scheduled_schema_version = target.version
    record.type_id = target.id
    record.updated_at = now()
    revision(session, identity, record)
    audit(
        session,
        record.project_id,
        identity["actor"],
        "entry.move",
        entryId=id,
        fromType=source.key,
        toType=target.key,
    )
    return record


def publication_action(session, identity, id, version, unpublish=False):
    require(identity, "editor", write=True)
    record = get_entry(session, identity, id)
    if record.version != version:
        raise CmsError("This entry changed. Reload before changing publication.", "CONFLICT")
    if record.status == "deleted":
        raise CmsError("Restore a revision to recover a trashed entry.")
    clear_schedule(record)
    if unpublish:
        record.published_data = record.published_slug = record.published_title = record.published_at = None
        record.published_revision = record.published_schema_version = None
    summarize_status(record)
    record.updated_at = now()
    revision(session, identity, record)
    audit(
        session,
        record.project_id,
        identity["actor"],
        "entry.unpublish" if unpublish else "entry.schedule_cancel",
        entryId=id,
    )
    return record


def archive_entry(session, identity, id, version):
    require(identity, "editor", write=True)
    record = get_entry(session, identity, id)
    if record.version != version:
        raise CmsError("This entry changed. Reload before deleting.", "CONFLICT")
    record.status, record.published_data = "deleted", None
    record.published_slug = record.published_title = record.published_at = None
    record.published_revision = record.published_schema_version = None
    clear_schedule(record)
    record.updated_at = now()
    revision(session, identity, record)
    audit(session, record.project_id, identity["actor"], "entry.delete", entryId=id)
    return True


def restore_entry(session, identity, id, number, version):
    record = get_entry(session, identity, id)
    old = session.scalar(scoped(session, Revision, identity).where(Revision.entry_id == id, Revision.number == number))
    if not old:
        raise CmsError("Revision not found.", "NOT_FOUND")
    definition = session.get(ContentType, record.type_id)
    return save_entry(
        session,
        identity,
        definition.key,
        old.snapshot["slug"],
        old.snapshot["data"],
        "draft",
        id,
        version,
        restoring=True,
    )


def save_type(session, identity, key, name, fields, version=None, migration=None):
    require(identity, "admin", write=True)
    if not NAME.fullmatch(key) or not name.strip() or len(name) > 100:
        raise CmsError("Use a content type key beginning with a lower-case letter and a name of 1–100 characters.")
    validate_fields(fields)
    record = session.scalar(scoped(session, ContentType, identity).where(ContentType.key == key))
    if record:
        if version != record.version:
            raise CmsError("This schema changed. Reload it.", "CONFLICT")
        migration = {} if migration is None else migration
        if not isinstance(migration, dict):
            raise CmsError("Migration must be an object.")
        if not isinstance(migration.get("rename", {}), dict) or not isinstance(migration.get("defaults", {}), dict):
            raise CmsError("Migration rename and defaults must be objects.")
        if not isinstance(migration.get("drop", []), list) or any(
            not isinstance(x, str) for x in migration.get("drop", [])
        ):
            raise CmsError("Migration drop must be a list of field names.")
        if any(not isinstance(x, str) for x in migration.get("rename", {}).values()):
            raise CmsError("Migration rename destinations must be field names.")
        if set(migration) - {"rename", "defaults", "drop"}:
            raise CmsError("Migration supports rename, defaults, and drop.")

        def transform(data):
            data = dict(data)
            for src, dest in migration.get("rename", {}).items():
                if src in data:
                    if dest in data:
                        raise CmsError(f"Cannot rename {src}: {dest} already exists.")
                    data[dest] = data.pop(src)
            for k in migration.get("drop", []):
                data.pop(k, None)
            for k, value in migration.get("defaults", {}).items():
                data.setdefault(k, value)
            validate_data(fields, data, session, identity["project_id"])
            return data

        for entry in session.scalars(scoped(session, Entry, identity).where(Entry.type_id == record.id)).all():
            entry.data = transform(entry.data)
            if entry.published_data is not None:
                entry.published_data = transform(entry.published_data)
                entry.published_schema_version = record.version + 1
            if entry.scheduled_data is not None:
                entry.scheduled_data = transform(entry.scheduled_data)
                entry.scheduled_schema_version = record.version + 1
            entry.updated_at = now()
            revision(session, identity, entry)
        record.version += 1
    else:
        record = ContentType(project_id=identity["project_id"], key=key, name=name, fields=fields)
        session.add(record)
        session.flush()
    record.name, record.fields = name.strip(), fields
    session.add(SchemaRevision(type_id=record.id, version=record.version, fields=fields))
    audit(session, identity["project_id"], identity["actor"], "schema.save", key=key, version=record.version)
    return record


def publish_due(factory):
    with factory.begin() as session:
        for record in session.scalars(
            select(Entry)
            .where(Entry.status != "deleted", Entry.scheduled_at <= now())
            .with_for_update(skip_locked=True)
        ).all():
            due, captured = record.scheduled_at, record.scheduled_revision
            try:
                with session.begin_nested():
                    definition = session.get(ContentType, record.type_id)
                    if record.scheduled_data is None or not record.scheduled_slug or captured is None:
                        raise CmsError("Scheduled snapshot is missing; save a new schedule.")
                    validate_data(definition.fields, record.scheduled_data, session, record.project_id)
                    publish_snapshot(
                        record,
                        definition,
                        record.scheduled_data,
                        record.scheduled_slug,
                        record.scheduled_title,
                        captured,
                    )
                    record.updated_at = now()
                    revision(session, {"actor": "scheduler"}, record)
                    audit(
                        session,
                        record.project_id,
                        "scheduler",
                        "entry.publish",
                        entryId=record.id,
                        scheduledRevision=captured,
                    )
            except (CmsError, IntegrityError, StaleDataError) as exc:
                code = exc.code if isinstance(exc, CmsError) else "CONFLICT"
                reason = (
                    str(exc)
                    if isinstance(exc, CmsError)
                    else "The scheduled URL conflicts with live content. Choose another slug and reschedule."
                )
                record.schedule_error = {
                    "code": code,
                    "message": reason,
                    "revision": captured,
                    "dueAt": due.isoformat() + "Z",
                    "failedAt": now().isoformat() + "Z",
                }
                record.scheduled_at = None
                record.updated_at = now()
                summarize_status(record)
                revision(session, {"actor": "scheduler"}, record)
                audit(
                    session,
                    record.project_id,
                    "scheduler",
                    "entry.schedule_failed",
                    entryId=record.id,
                    scheduledRevision=captured,
                    reason=reason,
                    code=code,
                )
