"""Project-scoped content queries, revisions, schema migrations and publishing."""

import hashlib
import base64
import json
import re
from copy import deepcopy
from datetime import datetime

from sqlalchemy import case, and_, false, func, inspect, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.sql import ColumnElement

from .models import (
    ContentType,
    DraftReceipt,
    Entry,
    EntryFieldIndex,
    Project,
    Revision,
    SchemaRevision,
    WebsitePath,
    now,
    uid,
)
from .indexing import SORT_PREFIX_BYTES, indexed_value, scalar_fields
from .outbox import emit
from .schema import NAME, public_data, reference_targets, validate_data, validate_fields
from .security import CmsError, audit, require
from .transforms import transform_data, validate_steps


def slugify(value):
    result = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not result or len(result) > 220:
        raise CmsError(
            "Slug must contain letters or numbers and be at most 220 characters.",
            field_path="slug",
            reason="invalid_slug",
        )
    return result


def scoped(session, model, identity):
    return select(model).where(model.project_id == identity["project_id"])


def get_type(session, identity, key):
    cached = identity.get("type_records", {})
    record = cached.get(key)
    if record is None or inspect(record).deleted or record in session.deleted:
        record = session.scalar(scoped(session, ContentType, identity).where(ContentType.key == key))
    if (
        record is None
        or record.project_id != identity["project_id"]
        or (identity.get("delivery") and identity["scopes"] and key not in identity["scopes"])
    ):
        raise CmsError("Content type not found.", "NOT_FOUND")
    return record


def get_entry(session, identity, id):
    cached = identity.get("entry_records")
    if cached is not None and id in cached:
        record = cached[id]
    else:
        record = session.get(Entry, id)
        if cached is not None:
            cached[id] = record
    if (
        not record
        or inspect(record).deleted
        or record in session.deleted
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
        "title": (
            record.published_slug
            if any(f["name"] == "title" and f.get("private") for f in definition.fields)
            else record.published_title
        )
        if delivery
        else record.title,
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
        "publishedData": None if delivery else record.published_data,
        "publishedSlug": None if delivery else record.published_slug,
        "publishedTitle": None if delivery else record.published_title,
        "publishedSnapshot": None
        if delivery or record.published_slug is None
        else {
            "slug": record.published_slug,
            "title": record.published_title,
            "data": record.published_data,
            "revision": record.published_revision,
            "schemaVersion": record.published_schema_version,
            "publishedAt": record.published_at.isoformat() + "Z" if record.published_at else None,
        },
    }


def private_title_types(session, identity):
    return [
        t.id
        for t in session.scalars(scoped(session, ContentType, identity)).all()
        if any(f["name"] == "title" and f.get("private") for f in t.fields)
    ]


def delivery_title(session, identity):
    return case(
        (Entry.type_id.in_(private_title_types(session, identity)), Entry.published_slug), else_=Entry.published_title
    )


def entry_page(
    session,
    identity,
    type_key=None,
    status=None,
    search="",
    sort="updated_desc",
    first=20,
    after=None,
    filters=None,
    order_by=None,
    include_total=True,
):
    require(identity)
    if not 1 <= first <= 100 or sort not in {"updated_desc", "updated_asc", "title_asc", "title_desc"}:
        raise CmsError("Use a page size of 1–100 and a supported sort order.")
    if order_by is not None and (not type_key or sort != "updated_desc"):
        raise CmsError("Field ordering requires a content type; use either sort or orderBy.")
    title_attr = (
        delivery_title(session, identity) if identity.get("delivery") and sort.startswith("title") else Entry.title
    )
    query = scoped(session, Entry, identity)
    if identity.get("delivery"):
        query = query.where(Entry.published_slug.is_not(None), Entry.status != "deleted")
        # A named type is checked by get_type below; only untyped lists need a scope subquery.
        if identity["scopes"] and not type_key:
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
        definition = get_type(session, identity, type_key)
        query = query.where(Entry.type_id == definition.id)
    if search:
        safe = search[:100].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        title_match: ColumnElement[bool] = Entry.title.ilike(f"%{safe}%", escape="\\")
        if identity.get("delivery"):
            title_match = Entry.published_title.ilike(f"%{safe}%", escape="\\")
            if type_key:
                if any(f["name"] == "title" and f.get("private") for f in definition.fields):
                    title_match = false()
            else:
                # Keep the searchable column visible to the index while excluding private titles.
                title_match = and_(Entry.type_id.not_in(private_title_types(session, identity)), title_match)
        query = query.where(
            or_(
                title_match,
                (Entry.published_slug if identity.get("delivery") else Entry.slug).ilike(f"%{safe}%", escape="\\"),
            )
        )
    count_query = query
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
            digest = indexed_value(fields[key], value)
            expr = (
                target[key].as_boolean()
                if isinstance(value, bool)
                else target[key].as_float()
                if isinstance(value, (int, float))
                else target[key].as_string()
            )
            comparison = expr == value
            count_comparison = comparison
            if digest is not None:
                candidates = Entry.id.in_(
                    select(EntryFieldIndex.entry_id).where(
                        EntryFieldIndex.project_id == identity["project_id"],
                        EntryFieldIndex.type_id == definition.id,
                        EntryFieldIndex.snapshot == ("published" if identity.get("delivery") else "draft"),
                        EntryFieldIndex.field == key,
                        EntryFieldIndex.value_hash == bytes.fromhex(digest),
                    )
                )
                # Recheck JSON only for indexed candidates; a join misestimated common values and probed per row.
                comparison = case((candidates, comparison), else_=False)
                count_comparison = comparison
                if isinstance(value, str):
                    raw = value.encode("utf-8", errors="surrogatepass")
                    exact = EntryFieldIndex.sort_prefix == raw[:SORT_PREFIX_BYTES]
                    if len(raw) >= SORT_PREFIX_BYTES:
                        exact = and_(exact, func.coalesce(EntryFieldIndex.sort_key, EntryFieldIndex.sort_prefix) == raw)
                    # Exact projection values avoid parsing every matched document just to count strings.
                    exact_candidates = Entry.id.in_(
                        select(EntryFieldIndex.entry_id).where(
                            EntryFieldIndex.project_id == identity["project_id"],
                            EntryFieldIndex.type_id == definition.id,
                            EntryFieldIndex.snapshot == ("published" if identity.get("delivery") else "draft"),
                            EntryFieldIndex.field == key,
                            exact,
                        )
                    )
                    # Separate covering scans avoid projection heap reads and per-match entry probes.
                    count_comparison = case((candidates, exact_candidates), else_=False)
            query = query.where(comparison)
            count_query = count_query.where(count_comparison)
    total_query = select(func.count()).select_from(count_query.subquery())
    total = session.scalar(total_query) if include_total else None
    if order_by is not None:
        from .ordering import field_page

        items, cursor, has_next = field_page(session, identity, definition, query, order_by, first, after)
        return {
            "nodes": [entry_dict(session, identity, record) for record in items],
            "total": total,
            "totalQuery": total_query,
            "endCursor": cursor,
            "hasNextPage": has_next,
        }
    attr = (
        title_attr if sort.startswith("title") else Entry.published_at if identity.get("delivery") else Entry.updated_at
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
            (entry_dict(session, identity, last)["title"] if identity.get("delivery") else last.title)
            if sort.startswith("title")
            else (last.published_at if identity.get("delivery") else last.updated_at).isoformat()
        )
        cursor = base64.urlsafe_b64encode(json.dumps([value, last.id, sort]).encode()).decode()
    return {
        "nodes": [entry_dict(session, identity, e) for e in items],
        "total": total,
        "totalQuery": total_query,
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


def website_path(definition, slug, data, fields=None):
    """Only current public values determine the website canonical route."""
    if not slug:
        return None
    if definition.key == "sitePost":
        return "/blog/" + slug
    if definition.key == "siteProject":
        return "/projects/" + slug
    if definition.key == "sitePage":
        visible = public_data(definition.fields if fields is None else fields, data or {})
        return "/" if slug == "home" or visible.get("kind") == "home" else "/" + slug
    return None


def reserve_website_paths(session, record, definition, slug, data, previous_definition=None, fields=None):
    target = website_path(definition, slug, data, fields)
    previous = website_path(previous_definition or definition, record.published_slug, record.published_data)
    paths = {path for path in (target, previous) if path}
    if not paths:
        return
    if not record.id:
        record.id = uid()
    with session.no_autoflush:
        # The unique path claim arbitrates concurrent publications without reversing scheduler lock order.
        known = session.scalars(select(WebsitePath).where(WebsitePath.project_id == record.project_id)).all()
        for claim in known:
            if claim.path in paths and claim.entry_id != record.id:
                raise CmsError(
                    "This website URL belongs to another entry's publication history. Choose a different slug.",
                    "CONFLICT",
                    field_path="slug",
                    reason="website_path_conflict",
                )
        live = session.scalars(
            select(Entry).where(
                Entry.project_id == record.project_id,
                Entry.id != record.id,
                Entry.published_slug.is_not(None),
                Entry.status != "deleted",
            )
        ).all()
        for entry in live:
            other = session.get(ContentType, entry.type_id)
            if website_path(other, entry.published_slug, entry.published_data) in paths:
                raise CmsError(
                    "This website URL is already live on another entry. Choose a different slug.",
                    "CONFLICT",
                    field_path="slug",
                    reason="website_path_conflict",
                )
        owned = {claim.path for claim in known if claim.entry_id == record.id}
        for path in paths - owned:
            session.add(WebsitePath(project_id=record.project_id, entry_id=record.id, path=path))


def website_path_conflict(error):
    """Report a raced unique-path claim as the same actionable editorial conflict."""
    if not isinstance(error, IntegrityError):
        return error
    constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    if constraint == "website_paths_project_id_path_key" or (
        "UNIQUE constraint failed: website_paths.project_id, website_paths.path" in str(error.orig)
    ):
        return CmsError(
            "This website URL belongs to another entry's publication history. Choose a different slug.",
            "CONFLICT",
            field_path="slug",
            reason="website_path_conflict",
        )
    return error


def website_reserved_paths(session, identity):
    """Formerly public paths remain reserved without disclosing unpublished destinations."""
    require(identity)
    query = (
        select(WebsitePath.path)
        .join(Entry, WebsitePath.entry_id == Entry.id)
        .join(ContentType, Entry.type_id == ContentType.id)
        .where(WebsitePath.project_id == identity["project_id"])
        .order_by(WebsitePath.path)
    )
    if identity.get("delivery") and identity["scopes"]:
        query = query.where(ContentType.key.in_(identity["scopes"]))
    return list(session.scalars(query).all())


def website_redirects(session, identity):
    require(identity)
    rows = session.execute(
        select(WebsitePath, Entry, ContentType)
        .join(Entry, WebsitePath.entry_id == Entry.id)
        .join(ContentType, Entry.type_id == ContentType.id)
        .where(
            WebsitePath.project_id == identity["project_id"],
            Entry.published_slug.is_not(None),
            Entry.status != "deleted",
        )
        .order_by(WebsitePath.path)
    ).all()
    mappings = []
    for claim, entry, definition in rows:
        if identity.get("delivery") and identity["scopes"] and definition.key not in identity["scopes"]:
            continue
        target = website_path(definition, entry.published_slug, entry.published_data)
        if target and target != claim.path:
            mappings.append({"from": claim.path, "to": target, "entryId": entry.id})
    return mappings


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
    collision = session.scalar(
        select(Entry.id).where(
            Entry.project_id == identity["project_id"],
            Entry.type_id == definition.id,
            Entry.slug == slug,
            Entry.id != id,
        )
    )
    if collision:
        raise CmsError(
            "This slug is already used by another entry. Choose a different slug.",
            "CONFLICT",
            field_path="slug",
            reason="slug_conflict",
        )
    if not id:
        session.add(record)
    record.slug = slug
    title = data.get("title", slug)
    if isinstance(title, dict):
        with session.no_autoflush:
            project = session.get(Project, identity["project_id"])
        title = title.get(project.default_locale) or title.get("en") or next(iter(title.values()), slug)
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
    previous_slug = record.published_slug
    if status == "published":
        reserve_website_paths(session, record, definition, slug, data)
        publish_snapshot(record, definition, data, slug, record.title, next_version)
    elif status == "scheduled":
        record.scheduled_revision = next_version
    revision(session, identity, record)
    if status == "published":
        emit(session, record, "published", record.published_revision, record.published_slug, previous_slug)
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


def save_entry_receipt(session, identity, key, type_key, slug, data, status, id, version, scheduled_at):
    require(identity, "editor", write=True)
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,100}", key):
        raise CmsError("Use a stable mutation request key of 16–100 characters.")
    values = {
        "operation": "saveEntry",
        "typeKey": type_key,
        "slug": slug,
        "data": data,
        "status": status,
        "id": id,
        "version": version,
        "scheduledAt": scheduled_at,
    }
    fingerprint = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
    previous = session.get(DraftReceipt, (identity["project_id"], identity["user"].id, key))
    if previous:
        if previous.fingerprint != fingerprint:
            raise CmsError("Request key was already used with different values.", "CONFLICT")
        return previous.response
    record = save_entry(session, identity, type_key, slug, data, status, id, version, scheduled_at)
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
    if record.published_slug:
        reserve_website_paths(session, record, target, record.published_slug, record.published_data, source)
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


def retry_publication(session, identity, id, version):
    """Requeue the failed immutable capture; never silently substitute newer edits."""
    require(identity, "editor", write=True)
    record = get_entry(session, identity, id)
    if record.version != version:
        raise CmsError("This entry changed. Reload before retrying.", "CONFLICT")
    if record.status == "deleted" or not record.schedule_error or record.scheduled_data is None:
        raise CmsError("There is no failed captured schedule to retry.")
    definition = session.get(ContentType, record.type_id)
    validate_data(definition.fields, record.scheduled_data, session, identity["project_id"])
    collision = session.scalar(
        select(Entry.id).where(
            Entry.project_id == record.project_id,
            Entry.type_id == record.type_id,
            Entry.published_slug == record.scheduled_slug,
            Entry.id != record.id,
            Entry.status != "deleted",
        )
    )
    if collision:
        raise CmsError("The captured URL is still in use. Resolve the conflict or replace the schedule.", "CONFLICT")
    record.scheduled_at = now()
    record.schedule_error = None
    record.updated_at = now()
    summarize_status(record)
    revision(session, identity, record)
    audit(
        session,
        record.project_id,
        identity["actor"],
        "entry.schedule_retry",
        entryId=id,
        scheduledRevision=record.scheduled_revision,
    )
    return record


def publication_action(session, identity, id, version, unpublish=False):
    require(identity, "editor", write=True)
    record = get_entry(session, identity, id)
    if record.version != version:
        raise CmsError("This entry changed. Reload before changing publication.", "CONFLICT")
    if record.status == "deleted":
        raise CmsError("Restore a revision to recover a trashed entry.")
    if unpublish and record.published_slug:
        emit(session, record, "unpublished", record.published_revision, record.published_slug)
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
    emit(session, record, "trashed", record.published_revision, record.published_slug)
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
    session.scalar(select(Project.id).where(Project.id == identity["project_id"]).with_for_update())
    if not NAME.fullmatch(key) or not name.strip() or len(name) > 100:
        raise CmsError("Use a content type key beginning with a lower-case letter and a name of 1–100 characters.")
    validate_fields(fields)
    known = set(
        session.scalars(select(ContentType.key).where(ContentType.project_id == identity["project_id"])).all()
    ) | {key}
    unknown = reference_targets(fields) - known
    if unknown:
        raise CmsError("Unknown reference target in this workspace: " + ", ".join(sorted(unknown)))
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
        if set(migration) - {"rename", "defaults", "drop", "steps"}:
            raise CmsError("Migration supports rename, defaults, drop, and ordered steps.")
        validate_steps(migration.get("steps", []))

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
            data = transform_data(data, migration.get("steps", []), key)
            validate_data(fields, data, session, identity["project_id"])
            return data

        eligibility_changed = scalar_fields(record.fields) != scalar_fields(fields)
        # Revision flushes must project transformed entries using the new schema.
        with session.no_autoflush:
            for entry in session.scalars(scoped(session, Entry, identity).where(Entry.type_id == record.id)).all():
                if eligibility_changed:
                    setattr(entry, "_scalar_index_fields", scalar_fields(fields))
                entry.data = transform(entry.data)
                if entry.published_data is not None:
                    published = transform(entry.published_data)
                    reserve_website_paths(session, entry, record, entry.published_slug, published, fields=fields)
                    entry.published_data = published
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
                    previous_slug = record.published_slug
                    reserve_website_paths(session, record, definition, record.scheduled_slug, record.scheduled_data)
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
                    emit(session, record, "published", captured, record.published_slug, previous_slug)
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
