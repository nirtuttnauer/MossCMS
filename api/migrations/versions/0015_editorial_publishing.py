"""Editorial capabilities, optional field rules, review binding, and releases."""

from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("projects", sa.Column("custom_permissions", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("projects", sa.Column("field_rules", sa.JSON(), nullable=True))
    op.add_column("projects", sa.Column("review_types", sa.JSON(), nullable=True))
    op.add_column("entries", sa.Column("review_state", sa.String(16), nullable=False, server_default="draft"))
    op.add_column("entries", sa.Column("approved_revision", sa.Integer(), nullable=True))
    op.add_column("entries", sa.Column("approved_slug", sa.String(220), nullable=True))
    op.add_column("entries", sa.Column("approved_schema_version", sa.Integer(), nullable=True))
    op.add_column("entries", sa.Column("submitted_revision", sa.Integer(), nullable=True))
    op.add_column("entries", sa.Column("reviewer_id", sa.String(36), nullable=True))
    op.add_column("entries", sa.Column("review_author_id", sa.String(36), nullable=True))
    op.add_column("entries", sa.Column("schedule_actor_id", sa.String(36), nullable=True))
    op.create_table(
        "releases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_releases_project_id", "releases", ["project_id"])
    op.create_index("ix_releases_status", "releases", ["status"])
    op.create_index(
        "ix_releases_due",
        "releases",
        ["scheduled_at"],
        sqlite_where=sa.text("status = 'scheduled'"),
        postgresql_where=sa.text("status = 'scheduled'"),
    )
    op.create_table(
        "release_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("release_id", sa.String(36), sa.ForeignKey("releases.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("entry_id", sa.String(36), sa.ForeignKey("entries.id"), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(220), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("release_id", "entry_id", name="uq_release_items_entry"),
    )
    op.create_index("ix_release_items_release_id", "release_items", ["release_id"])
    op.create_index("ix_release_items_project_id", "release_items", ["project_id"])
    op.create_index("ix_release_items_entry_id", "release_items", ["entry_id"])


def downgrade():
    op.drop_table("release_items")
    op.drop_index("ix_releases_due", table_name="releases")
    op.drop_index("ix_releases_status", table_name="releases")
    op.drop_index("ix_releases_project_id", table_name="releases")
    op.drop_table("releases")
    for name in (
        "schedule_actor_id",
        "review_author_id",
        "reviewer_id",
        "submitted_revision",
        "approved_schema_version",
        "approved_slug",
        "approved_revision",
        "review_state",
    ):
        op.drop_column("entries", name)
    op.drop_column("projects", "review_types")
    op.drop_column("projects", "field_rules")
    op.drop_column("projects", "custom_permissions")
