"""Saved-revision-scoped expiring preview capabilities."""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "preview_grants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("entry_id", sa.String(36), sa.ForeignKey("entries.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("type_key", sa.String(60), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_preview_grants_project_id", "preview_grants", ["project_id"])


def downgrade():
    op.drop_table("preview_grants")
