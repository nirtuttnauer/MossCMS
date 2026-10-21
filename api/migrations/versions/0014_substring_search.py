"""Index case-insensitive title/slug substrings on PostgreSQL."""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "ix_entries_draft_search",
        "entries",
        ["title", "slug"],
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops", "slug": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_entries_published_search",
        "entries",
        ["published_title", "published_slug"],
        postgresql_using="gin",
        postgresql_ops={"published_title": "gin_trgm_ops", "published_slug": "gin_trgm_ops"},
        postgresql_where=sa.text("published_slug IS NOT NULL"),
    )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index("ix_entries_published_search", table_name="entries")
        op.drop_index("ix_entries_draft_search", table_name="entries")
        # The extension may also serve operator-owned indexes; leave it installed.
