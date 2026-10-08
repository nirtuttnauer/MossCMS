"""Preserve complete live and scheduled versions independently of working data."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

COLUMNS = {
    "published_slug": sa.String(220),
    "published_title": sa.String(200),
    "published_at": sa.DateTime(),
    "published_revision": sa.Integer(),
    "published_schema_version": sa.Integer(),
    "scheduled_data": sa.JSON(),
    "scheduled_slug": sa.String(220),
    "scheduled_title": sa.String(200),
    "scheduled_revision": sa.Integer(),
    "scheduled_schema_version": sa.Integer(),
    "schedule_error": sa.JSON(),
}


def upgrade():
    for name, kind in COLUMNS.items():
        op.add_column("entries", sa.Column(name, kind, nullable=True))
    connection = op.get_bind()
    entries = sa.Table("entries", sa.MetaData(), autoload_with=connection)
    types = sa.Table("content_types", sa.MetaData(), autoload_with=connection)
    rows = connection.execute(
        sa.select(entries, types.c.version.label("schema_version")).join(types, entries.c.type_id == types.c.id)
    ).mappings()
    for row in rows:
        values = {}
        if row["status"] == "published" and row["published_data"] is not None:
            values = dict(
                published_slug=row["slug"],
                published_title=row["title"],
                published_at=row["updated_at"],
                published_revision=row["version"],
                published_schema_version=row["schema_version"],
            )
        if row["status"] == "scheduled" and row["scheduled_at"] is not None:
            values.update(
                scheduled_data=row["data"],
                scheduled_slug=row["slug"],
                scheduled_title=row["title"],
                scheduled_revision=row["version"],
                scheduled_schema_version=row["schema_version"],
            )
        if values:
            connection.execute(entries.update().where(entries.c.id == row["id"]).values(**values))
    # A unique index permits multiple NULLs in both PostgreSQL and SQLite.
    op.create_index("uq_entries_public_slug", "entries", ["project_id", "type_id", "published_slug"], unique=True)
    op.create_index("ix_entries_published_at", "entries", ["published_at"])


def downgrade():
    raise RuntimeError("Independent snapshots cannot be downgraded losslessly. Restore the previous backup/image pair.")
