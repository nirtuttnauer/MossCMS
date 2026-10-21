"""Index published pagination and due schedules without changing stored records."""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_entries_delivery_page",
        "entries",
        ["project_id", "type_id", "published_at", "id"],
        postgresql_where=sa.text("published_slug IS NOT NULL"),
        sqlite_where=sa.text("published_slug IS NOT NULL"),
        postgresql_include=["status"],
    )
    op.create_index(
        "ix_entries_due_schedule",
        "entries",
        ["scheduled_at"],
        postgresql_where=sa.text("scheduled_at IS NOT NULL"),
        sqlite_where=sa.text("scheduled_at IS NOT NULL"),
    )


def downgrade():
    op.drop_index("ix_entries_due_schedule", table_name="entries")
    op.drop_index("ix_entries_delivery_page", table_name="entries")
