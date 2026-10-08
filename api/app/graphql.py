"""Editorial GraphQL and dynamically generated, project-specific delivery types."""

import hashlib
import hmac
import time
from datetime import date
from enum import Enum
from typing import Any, cast

import strawberry
from sqlalchemy import and_, func, or_, select
from strawberry.scalars import JSON

from . import content
from .models import Asset, Audit, ContentType, Entry, Membership, Revision, SchemaRevision
from .security import CmsError, audit, require


class SafeSchema(strawberry.Schema):
    def process_errors(self, errors, execution_context=None):
        # Strawberry's default logger includes the submitted query (possibly inline secrets).
        # The HTTP layer reports structured codes/request IDs without bodies instead.
        pass


@strawberry.type
class EntryNode:
    id: strawberry.ID
    type_key: str
    slug: str
    title: str
    data: JSON
    status: str
    version: int
    updated_at: str
    scheduled_at: str | None

    is_live: bool
    has_unpublished_changes: bool
    published_at: str | None
    published_revision: int | None
    scheduled_revision: int | None
    schedule_error: JSON | None

    @strawberry.field
    def resolved_assets(self, info: strawberry.Info) -> list["AssetNode"]:
        c = info.context
        record = content.get_entry(c["session"], c, str(self.id))
        definition = c["session"].get(ContentType, record.type_id)
        data = record.published_data if c.get("delivery") else record.data
        ids = content.image_asset_ids(definition.fields, data or {})
        rows = c["session"].scalars(content.scoped(c["session"], Asset, c).where(Asset.id.in_(ids))).all()
        return [asset_node(a, c["settings"]) for a in rows if a.mime.startswith("image/")]

    @classmethod
    def from_dict(cls, d):
        return cls(
            id=strawberry.ID(d["id"]),
            type_key=d["typeKey"],
            slug=d["slug"],
            title=d["title"],
            data=d["data"],
            status=d["status"],
            version=d["version"],
            updated_at=d["updatedAt"],
            scheduled_at=d["scheduledAt"],
            is_live=d["isLive"],
            has_unpublished_changes=d["hasUnpublishedChanges"],
            published_at=d["publishedAt"],
            published_revision=d["publishedRevision"],
            scheduled_revision=d["scheduledRevision"],
            schedule_error=d["scheduleError"],
        )


@strawberry.type
class EntryPage:
    nodes: list[EntryNode]
    total: int
    end_cursor: str | None
    has_next_page: bool


@strawberry.type
class TypeNode:
    id: strawberry.ID
    key: str
    name: str
    fields: JSON
    version: int

    @strawberry.field
    def entry_count(self, info: strawberry.Info) -> int:
        c = info.context
        query = content.scoped(c["session"], Entry, c).where(Entry.type_id == str(self.id), Entry.status != "deleted")
        if c["delivery"]:
            query = query.where(Entry.published_slug.is_not(None))
        return c["session"].scalar(select(func.count()).select_from(query.subquery())) or 0


def type_node(record, delivery=False):
    def visible(fields):
        result = []
        for f in fields:
            if not f.get("private"):
                f = dict(f)

                def project_field(field):
                    field = dict(field)
                    if field["type"] == "object":
                        field["fields"] = visible(field["fields"])
                    if field["type"] == "list":
                        field["item"] = project_field(field["item"])
                    return field

                result.append(project_field(f))
        return result

    return TypeNode(
        id=strawberry.ID(record.id),
        key=record.key,
        name=record.name,
        fields=visible(record.fields) if delivery else record.fields,
        version=record.version,
    )


@strawberry.type
class RevisionNode:
    number: int
    snapshot: JSON
    author: str
    created_at: str


@strawberry.type
class ReferenceNode:
    id: strawberry.ID
    entry: EntryNode | None


@strawberry.type
class AssetNode:
    id: strawberry.ID
    name: str
    mime: str
    size: int
    url: str
    width: int | None = None
    height: int | None = None
    variants: JSON | None = None


def asset_node(record, settings):
    from .images import variant_metadata

    expiry = int(time.time()) + 900
    signature = hmac.new(settings.secret.encode(), f"{record.id}:{expiry}".encode(), hashlib.sha256).hexdigest()
    return AssetNode(
        id=strawberry.ID(record.id),
        name=record.name,
        mime=record.mime,
        size=record.size,
        width=record.width,
        height=record.height,
        variants=variant_metadata(record, settings),
        url=f"{settings.public_url}/media/{record.id}?expires={expiry}&signature={signature}",
    )


@strawberry.type
class Query:
    @strawberry.field
    def draft_receipt(self, info: strawberry.Info, key: str) -> EntryNode | None:
        c = info.context
        response = content.draft_receipt(c["session"], c, key)
        return EntryNode.from_dict(response) if response else None

    @strawberry.field
    def content_groups(self, info: strawberry.Info, status: str | None = None) -> JSON:
        c = info.context
        return cast(JSON, content.content_groups(c["session"], c, status))

    @strawberry.field
    def content_types(self, info: strawberry.Info) -> list[TypeNode]:
        c = info.context
        require(c)
        rows = c["session"].scalars(content.scoped(c["session"], ContentType, c).order_by(ContentType.name)).all()
        return [
            type_node(t, c["delivery"]) for t in rows if not c["delivery"] or not c["scopes"] or t.key in c["scopes"]
        ]

    @strawberry.field
    def entries(
        self,
        info: strawberry.Info,
        type_key: str | None = None,
        status: str | None = None,
        search: str = "",
        sort: str = "updated_desc",
        first: int = 20,
        after: str | None = None,
        filters: JSON | None = None,
    ) -> EntryPage:
        c = info.context
        page = content.entry_page(c["session"], c, type_key, status, search, sort, first, after, filters)
        return EntryPage(
            nodes=[EntryNode.from_dict(d) for d in page["nodes"]],
            total=page["total"],
            end_cursor=page["endCursor"],
            has_next_page=page["hasNextPage"],
        )

    @strawberry.field
    def entry(self, info: strawberry.Info, id: strawberry.ID) -> EntryNode:
        c = info.context
        require(c)
        return EntryNode.from_dict(content.entry_dict(c["session"], c, content.get_entry(c["session"], c, str(id))))

    @strawberry.field
    def revisions(self, info: strawberry.Info, id: strawberry.ID, first: int = 20) -> list[RevisionNode]:
        c = info.context
        require(c)
        if c["delivery"]:
            raise CmsError("Revision history is editorial only.", "FORBIDDEN")
        content.get_entry(c["session"], c, str(id))
        if not 1 <= first <= 100:
            raise CmsError("Use a revision page size of 1–100.")
        rows = (
            c["session"]
            .scalars(
                content.scoped(c["session"], Revision, c)
                .where(Revision.entry_id == str(id))
                .order_by(Revision.number.desc())
                .limit(first)
            )
            .all()
        )
        return [
            RevisionNode(
                number=r.number, snapshot=r.snapshot, author=r.author, created_at=r.created_at.isoformat() + "Z"
            )
            for r in rows
        ]

    @strawberry.field
    def schema_history(self, info: strawberry.Info, key: str) -> JSON:
        c = info.context
        require(c, "admin")
        definition = content.get_type(c["session"], c, key)
        rows = (
            c["session"]
            .scalars(
                select(SchemaRevision)
                .where(SchemaRevision.type_id == definition.id)
                .order_by(SchemaRevision.version.desc())
                .limit(50)
            )
            .all()
        )
        return cast(
            JSON,
            [{"version": r.version, "fields": r.fields, "createdAt": r.created_at.isoformat() + "Z"} for r in rows],
        )

    @strawberry.field
    def assets(self, info: strawberry.Info, first: int = 50) -> list[AssetNode]:
        c = info.context
        require(c)
        if c["delivery"]:
            raise CmsError("Use an asset field on published content.", "FORBIDDEN")
        if not 1 <= first <= 100:
            raise CmsError("Use an asset page size of 1–100.")
        rows = (
            c["session"]
            .scalars(content.scoped(c["session"], Asset, c).order_by(Asset.created_at.desc()).limit(first))
            .all()
        )
        return [asset_node(a, c["settings"]) for a in rows]

    @strawberry.field
    def asset_page(
        self,
        info: strawberry.Info,
        first: int = 24,
        after: str | None = None,
        search: str = "",
        images_only: bool = False,
        id: strawberry.ID | None = None,
    ) -> JSON:
        c = info.context
        require(c)
        if c["delivery"]:
            raise CmsError("Use an asset field on published content.", "FORBIDDEN")
        if not 1 <= first <= 100 or len(search) > 254:
            raise CmsError("Use 1–100 assets per page and a search of at most 254 characters.")
        query = content.scoped(c["session"], Asset, c)
        if search:
            query = query.where(
                Asset.name.ilike("%" + search.replace("%", "\\%").replace("_", "\\_") + "%", escape="\\")
            )
        if images_only:
            query = query.where(Asset.mime.in_(["image/png", "image/jpeg", "image/webp"]))
        if id:
            query = query.where(Asset.id == str(id))
        if after:
            boundary = c["session"].get(Asset, after)
            if not boundary or boundary.project_id != c["project_id"]:
                raise CmsError("Invalid asset cursor.")
            query = query.where(
                or_(
                    Asset.created_at < boundary.created_at,
                    and_(Asset.created_at == boundary.created_at, Asset.id < boundary.id),
                )
            )
        rows = c["session"].scalars(query.order_by(Asset.created_at.desc(), Asset.id.desc()).limit(first + 1)).all()
        return cast(
            JSON,
            {
                "nodes": [asset_node(a, c["settings"]).__dict__ for a in rows[:first]],
                "endCursor": rows[first - 1].id if len(rows) > first else None,
                "hasNextPage": len(rows) > first,
            },
        )

    @strawberry.field
    def publication_queue(
        self, info: strawberry.Info, failed: bool = False, first: int = 25, offset: int = 0, overdue: bool = False
    ) -> JSON:
        c = info.context
        require(c)
        if c["delivery"]:
            raise CmsError("Publication queues are editorial only.", "FORBIDDEN")
        if not 1 <= first <= 100 or not 0 <= offset <= 100000:
            raise CmsError("Use a bounded publication queue page.")
        query = content.scoped(c["session"], Entry, c).where(Entry.status != "deleted")
        query = (
            query.where(Entry.schedule_error["code"].as_string().is_not(None))
            if failed
            else query.where(Entry.scheduled_at.is_not(None))
        )
        if overdue:
            query = query.where(Entry.scheduled_at <= content.now())
        total = c["session"].scalar(select(func.count()).select_from(query.subquery()))
        rows = (
            c["session"]
            .scalars(
                query.order_by(Entry.scheduled_at.asc(), Entry.updated_at.desc(), Entry.id).offset(offset).limit(first)
            )
            .all()
        )
        return cast(JSON, {"nodes": [content.entry_dict(c["session"], c, r) for r in rows], "total": total})

    @strawberry.field
    def overview(self, info: strawberry.Info) -> JSON:
        c = info.context
        require(c)
        if c["delivery"]:
            raise CmsError("Overview is editorial only.", "FORBIDDEN")
        session = c["session"]

        def count(model, *extra):
            return session.scalar(
                select(func.count()).select_from(model).where(model.project_id == c["project_id"], *extra)
            )

        return cast(
            JSON,
            {
                "total": count(Entry, Entry.status != "deleted"),
                "published": count(Entry, Entry.published_slug.is_not(None), Entry.status != "deleted"),
                "drafts": count(Entry, Entry.status == "draft"),
                "scheduled": count(Entry, Entry.scheduled_at.is_not(None), Entry.status != "deleted"),
                "types": count(ContentType),
                "assets": count(Asset),
                "members": count(Membership),
            },
        )

    @strawberry.field
    def audit_log(self, info: strawberry.Info, first: int = 50) -> JSON:
        c = info.context
        require(c, "admin")
        if not 1 <= first <= 100:
            raise CmsError("Use an audit page size of 1–100.")
        rows = (
            c["session"]
            .scalars(content.scoped(c["session"], Audit, c).order_by(Audit.created_at.desc()).limit(first))
            .all()
        )
        return cast(
            JSON,
            [
                {
                    "actor": r.actor,
                    "action": r.action,
                    "details": r.details,
                    "createdAt": r.created_at.isoformat() + "Z",
                }
                for r in rows
            ],
        )


@strawberry.type
class Mutation:
    @strawberry.mutation
    def create_preview_grant(self, info: strawberry.Info, id: strawberry.ID, version: int) -> JSON:
        from .preview import create_grant

        c = info.context
        return cast(JSON, create_grant(c["session"], c, str(id), version))

    @strawberry.mutation
    def revoke_preview_grant(self, info: strawberry.Info, id: strawberry.ID) -> bool:
        from .preview import revoke_grant

        c = info.context
        return revoke_grant(c["session"], c, str(id))

    @strawberry.mutation
    def save_draft(
        self,
        info: strawberry.Info,
        request_key: str,
        type_key: str,
        slug: str,
        data: JSON,
        id: strawberry.ID | None = None,
        version: int | None = None,
    ) -> EntryNode:
        c = info.context
        response = content.save_draft(
            c["session"], c, request_key, type_key, slug, data, str(id) if id else None, version
        )
        return EntryNode.from_dict(response)

    @strawberry.mutation
    def unpublish_entry(self, info: strawberry.Info, id: strawberry.ID, version: int) -> EntryNode:
        c = info.context
        record = content.publication_action(c["session"], c, str(id), version, unpublish=True)
        return EntryNode.from_dict(content.entry_dict(c["session"], c, record))

    @strawberry.mutation
    def retry_publication(self, info: strawberry.Info, id: strawberry.ID, version: int) -> EntryNode:
        c = info.context
        record = content.retry_publication(c["session"], c, str(id), version)
        return EntryNode.from_dict(content.entry_dict(c["session"], c, record))

    @strawberry.mutation
    def cancel_schedule(self, info: strawberry.Info, id: strawberry.ID, version: int) -> EntryNode:
        c = info.context
        record = content.publication_action(c["session"], c, str(id), version)
        return EntryNode.from_dict(content.entry_dict(c["session"], c, record))

    @strawberry.mutation
    def move_entry(self, info: strawberry.Info, id: strawberry.ID, type_key: str, version: int) -> EntryNode:
        c = info.context
        record = content.move_entry(c["session"], c, str(id), type_key, version)
        return EntryNode.from_dict(content.entry_dict(c["session"], c, record))

    @strawberry.mutation
    def save_content_type(
        self,
        info: strawberry.Info,
        key: str,
        name: str,
        fields: JSON,
        version: int | None = None,
        migration: JSON | None = None,
    ) -> TypeNode:
        c = info.context
        return type_node(content.save_type(c["session"], c, key, name, fields, version, migration))

    @strawberry.mutation
    def delete_content_type(self, info: strawberry.Info, key: str) -> bool:
        c = info.context
        require(c, "admin", write=True)
        session = c["session"]
        definition = content.get_type(session, c, key)
        if session.scalar(select(Entry.id).where(Entry.type_id == definition.id).limit(1)):
            raise CmsError("This content type has entries or history and cannot be deleted.")
        for other in session.scalars(content.scoped(session, ContentType, c)).all():
            if other.id != definition.id and key in content.reference_targets(other.fields):
                raise CmsError("Another schema references this type. Update that reference first.")
        for revision in session.scalars(select(SchemaRevision).where(SchemaRevision.type_id == definition.id)):
            session.delete(revision)
        session.flush()
        session.delete(definition)
        audit(session, c["project_id"], c["actor"], "schema.delete", key=key)
        return True

    @strawberry.mutation
    def save_entry(
        self,
        info: strawberry.Info,
        type_key: str,
        slug: str,
        data: JSON,
        status: str = "draft",
        id: strawberry.ID | None = None,
        version: int | None = None,
        scheduled_at: str | None = None,
        request_key: str | None = None,
    ) -> EntryNode:
        c = info.context
        if request_key:
            return EntryNode.from_dict(
                content.save_entry_receipt(
                    c["session"],
                    c,
                    request_key,
                    type_key,
                    slug,
                    data,
                    status,
                    str(id) if id else None,
                    version,
                    scheduled_at,
                )
            )
        entry = content.save_entry(
            c["session"], c, type_key, slug, data, status, str(id) if id else None, version, scheduled_at
        )
        return EntryNode.from_dict(content.entry_dict(c["session"], c, entry))

    @strawberry.mutation
    def delete_entry(self, info: strawberry.Info, id: strawberry.ID, version: int) -> bool:
        c = info.context
        return content.archive_entry(c["session"], c, str(id), version)

    @strawberry.mutation
    def restore_entry(self, info: strawberry.Info, id: strawberry.ID, number: int, version: int) -> EntryNode:
        c = info.context
        entry = content.restore_entry(c["session"], c, str(id), number, version)
        return EntryNode.from_dict(content.entry_dict(c["session"], c, entry))


def generated_schema(definitions, delivery=False, scopes=None):
    attributes = {}

    def field_type(f: dict, name: str) -> Any:
        kind = f["type"]
        if kind in {"text", "richText"}:
            return str
        if kind == "number":
            return float
        if kind == "boolean":
            return bool
        if kind == "date":
            return date
        if kind == "enum":
            return strawberry.enum(Enum(name + "Enum", {v: v for v in f["options"]}))  # type: ignore[call-overload]
        if kind == "reference":
            return ReferenceNode
        if kind == "asset":
            return AssetNode
        if kind == "list":
            return list[field_type(f["item"], name + "Item") | None]  # type: ignore[misc]
        return object_type(f["fields"], name + "Object")

    def value(f, raw, info, typ, locale="en"):
        if f.get("localized") and isinstance(raw, dict):
            raw = raw.get(locale)
        if raw is None:
            return None
        kind = f["type"]
        c = info.context
        if kind == "date":
            return date.fromisoformat(raw)
        if kind == "enum":
            return typ(raw)
        if kind == "object":
            return typ(_data=raw)
        if kind == "list":
            inner = typ.__args__[0]
            if hasattr(inner, "__args__"):
                inner = inner.__args__[0]
            return [value(f["item"], item, info, inner, locale) for item in raw]
        if kind == "reference":
            try:
                entry = content.get_entry(c["session"], c, raw)
                return ReferenceNode(
                    id=strawberry.ID(raw), entry=EntryNode.from_dict(content.entry_dict(c["session"], c, entry))
                )
            except CmsError:
                return None
        if kind == "asset":
            asset = c["session"].get(Asset, raw)
            return asset_node(asset, c["settings"]) if asset and asset.project_id == c["project_id"] else None
        return raw

    def make_field(f, typ):
        def resolver(self, info: strawberry.Info, locale: str = "en"):
            raw = self._data.get(f["name"])
            return value(f, raw, info, typ, locale)

        resolver.__annotations__["return"] = typ | None
        return strawberry.field(resolver=resolver, name=f["name"])

    def object_type(fields, name, root=False):
        attrs: dict[str, Any] = {"__annotations__": {"_data": strawberry.Private[dict]}, "__module__": __name__}
        for f in fields:
            if delivery and f.get("private"):
                continue
            typ = field_type(f, name + f["name"][0].upper() + f["name"][1:])
            attrs[f["name"]] = make_field(f, typ)
        if not any(not f.get("private") or not delivery for f in fields):
            # GraphQL requires an object type to have at least one visible field.
            def empty(self) -> bool:
                return True

            attrs["empty"] = strawberry.field(resolver=empty)
        if root:

            def entry_id(self) -> strawberry.ID:
                return strawberry.ID(self._data["_entryId"])

            def entry_slug(self) -> str:
                return self._data["_entrySlug"]

            attrs["id"] = strawberry.field(resolver=entry_id)
            attrs["slug"] = strawberry.field(resolver=entry_slug)
        return strawberry.type(type(name, (), attrs))

    def make_list(key, typ):
        def resolver(self, info: strawberry.Info, first: int = 20, after: str | None = None, locale: str = "en"):
            c = info.context
            page = content.entry_page(c["session"], c, key, first=first, after=after)
            return [
                typ(_data={**row["data"], "_entryId": row["id"], "_entrySlug": row["slug"]}) for row in page["nodes"]
            ]

        resolver.__annotations__["return"] = list[typ]  # type: ignore[valid-type]
        return strawberry.field(resolver=resolver)

    for definition in definitions:
        if delivery and scopes and definition.key not in scopes:
            continue
        name = "Cms" + definition.key[0].upper() + definition.key[1:]
        typ = object_type(definition.fields, name, root=True)
        attributes["all" + name] = make_list(definition.key, typ)
    query = strawberry.type(type("ProjectQuery", (Query,), attributes))
    return SafeSchema(query=query, mutation=None if delivery else Mutation)
