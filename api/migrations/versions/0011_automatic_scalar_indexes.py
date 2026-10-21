"""Backfill bounded scalar hashes without converting stored JSON content."""

from alembic import op
import sqlalchemy as sa

from app.indexing import rebuild

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    index = op.create_table(
        "entry_field_indexes",
        sa.Column("entry_id", sa.String(36), sa.ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("snapshot", sa.String(9), primary_key=True),
        sa.Column("field", sa.String(60), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("type_id", sa.String(36), nullable=False),
        sa.Column("value_hash", sa.String(64), nullable=False),
    )
    connection = op.get_bind()
    entries = sa.Table("entries", sa.MetaData(), autoload_with=connection)
    rebuild(connection, entries, index, clear_existing=False)
    op.create_index(
        "ix_entry_fields_lookup",
        "entry_field_indexes",
        ["project_id", "type_id", "snapshot", "field", "value_hash", "entry_id"],
    )


def downgrade():
    op.drop_table("entry_field_indexes")
