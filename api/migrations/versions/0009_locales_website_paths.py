"""Workspace locale suggestions and reservations for known published website paths."""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("projects", sa.Column("default_locale", sa.String(20), nullable=False, server_default="en"))
    op.add_column("projects", sa.Column("locales", sa.JSON(), nullable=False, server_default='["en"]'))
    op.create_table(
        "website_paths",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("entry_id", sa.String(36), sa.ForeignKey("entries.id"), nullable=False),
        sa.Column("path", sa.String(300), nullable=False),
        sa.UniqueConstraint("project_id", "path"),
    )
    op.create_index("ix_website_paths_project_id", "website_paths", ["project_id"])
    op.create_index("ix_website_paths_entry_id", "website_paths", ["entry_id"])


def downgrade():
    op.drop_table("website_paths")
    op.drop_column("projects", "locales")
    op.drop_column("projects", "default_locale")
