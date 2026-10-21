from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    text,
)
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .indexing import remove_entry, sync_entry


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100))
    preview_origin: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    default_locale: Mapped[str] = mapped_column(String(20), default="en", server_default="en")
    locales: Mapped[list] = mapped_column(JSON, default=lambda: ["en"], server_default='["en"]')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Membership(Base):
    __tablename__ = "memberships"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))


class Token(Base):
    __tablename__ = "tokens"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    email: Mapped[str] = mapped_column(String(254), default="")
    role: Mapped[str] = mapped_column(String(16), default="reader")
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    csrf: Mapped[str] = mapped_column(String(64), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ContentType(Base):
    __tablename__ = "content_types"
    __table_args__ = (UniqueConstraint("project_id", "key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    key: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(100))
    fields: Mapped[list] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __mapper_args__ = {"version_id_col": version}


class SchemaRevision(Base):
    __tablename__ = "schema_revisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    type_id: Mapped[str] = mapped_column(ForeignKey("content_types.id"))
    version: Mapped[int] = mapped_column(Integer)
    fields: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Entry(Base):
    __tablename__ = "entries"
    __table_args__ = (
        UniqueConstraint("project_id", "type_id", "slug"),
        UniqueConstraint("project_id", "type_id", "published_slug", name="uq_entries_public_slug"),
        Index(
            "ix_entries_draft_search",
            "title",
            "slug",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops", "slug": "gin_trgm_ops"},
        ).ddl_if(dialect="postgresql"),
        Index(
            "ix_entries_published_search",
            "published_title",
            "published_slug",
            postgresql_using="gin",
            postgresql_ops={"published_title": "gin_trgm_ops", "published_slug": "gin_trgm_ops"},
            postgresql_where=text("published_slug IS NOT NULL"),
        ).ddl_if(dialect="postgresql"),
        Index(
            "ix_entries_delivery_page",
            "project_id",
            "type_id",
            "published_at",
            "id",
            postgresql_where=text("published_slug IS NOT NULL"),
            sqlite_where=text("published_slug IS NOT NULL"),
            postgresql_include=["status"],
        ),
        Index(
            "ix_entries_due_schedule",
            "scheduled_at",
            postgresql_where=text("scheduled_at IS NOT NULL"),
            sqlite_where=text("scheduled_at IS NOT NULL"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    type_id: Mapped[str] = mapped_column(ForeignKey("content_types.id"), index=True)
    slug: Mapped[str] = mapped_column(String(220))
    title: Mapped[str] = mapped_column(String(200))
    data: Mapped[dict] = mapped_column(JSON)
    published_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    published_slug: Mapped[str | None] = mapped_column(String(220), nullable=True)
    published_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    published_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_schema_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduled_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scheduled_slug: Mapped[str | None] = mapped_column(String(220), nullable=True)
    scheduled_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    scheduled_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduled_schema_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schedule_error: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True, default="draft")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    __mapper_args__ = {"version_id_col": version}


class EntryFieldIndex(Base):
    __tablename__ = "entry_field_indexes"
    __table_args__ = (
        Index("ix_entry_fields_lookup", "project_id", "type_id", "snapshot", "field", "value_hash", "entry_id"),
        Index("ix_entry_fields_order", "project_id", "type_id", "snapshot", "field", "sort_prefix", "entry_id"),
        Index(
            "ix_entry_fields_date_order",
            "project_id",
            "type_id",
            "snapshot",
            "field",
            "date_key",
            "entry_id",
            postgresql_where=text("date_key IS NOT NULL"),
            sqlite_where=text("date_key IS NOT NULL"),
        ),
        Index(
            "ix_entry_fields_long",
            "sort_long",
            "project_id",
            "type_id",
            "snapshot",
            "field",
            postgresql_where=text("sort_long IS TRUE"),
            sqlite_where=text("sort_long IS 1"),
        ),
    )
    entry_id: Mapped[str] = mapped_column(ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True)
    snapshot: Mapped[str] = mapped_column(String(9), primary_key=True)
    field: Mapped[str] = mapped_column(String(60), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36))
    type_id: Mapped[str] = mapped_column(String(36))
    value_hash: Mapped[bytes] = mapped_column(LargeBinary(32))
    sort_key: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    sort_prefix: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    sort_long: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    date_key: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Revision(Base):
    __tablename__ = "revisions"
    __table_args__ = (UniqueConstraint("entry_id", "number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    entry_id: Mapped[str] = mapped_column(ForeignKey("entries.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    author: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(254))
    key: Mapped[str] = mapped_column(String(300))
    storage: Mapped[str] = mapped_column(String(16))
    mime: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    variants: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True, nullable=True)
    actor: Mapped[str] = mapped_column(String(254))
    action: Mapped[str] = mapped_column(String(60))
    details: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


def database(url):
    if url.startswith("sqlite"):
        filename = make_url(url).database
        if filename and filename != ":memory:":
            Path(filename).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        url, pool_pre_ping=True, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {}
    )
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    return engine, sessionmaker(engine, expire_on_commit=False)


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"
    __table_args__ = (UniqueConstraint("provider", "subject"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    subject: Mapped[str] = mapped_column(String(254))


class DraftReceipt(Base):
    __tablename__ = "draft_receipts"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class PreviewGrant(Base):
    __tablename__ = "preview_grants"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    entry_id: Mapped[str] = mapped_column(ForeignKey("entries.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    revision: Mapped[int] = mapped_column(Integer)
    type_key: Mapped[str] = mapped_column(String(60))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PublicationEvent(Base):
    __tablename__ = "publication_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    claim: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Webhook(Base):
    __tablename__ = "webhooks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    url: Mapped[str] = mapped_column(String(2048))
    secret: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(default=True)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (UniqueConstraint("event_id", "webhook_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    event_id: Mapped[str] = mapped_column(String(36))
    webhook_id: Mapped[str] = mapped_column(ForeignKey("webhooks.id"))
    payload: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    claim: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class WebsitePath(Base):
    __tablename__ = "website_paths"
    __table_args__ = (UniqueConstraint("project_id", "path"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    entry_id: Mapped[str] = mapped_column(ForeignKey("entries.id"), index=True)
    path: Mapped[str] = mapped_column(String(300))


event.listen(Entry, "after_insert", sync_entry)
event.listen(Entry, "after_update", sync_entry)
event.listen(Entry, "after_delete", remove_entry)
