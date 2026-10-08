"""Webhook subscriptions and bounded per-receiver delivery history."""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "webhooks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("secret", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_webhooks_project_id", "webhooks", ["project_id"])
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("webhook_id", sa.String(36), sa.ForeignKey("webhooks.id"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_at", sa.DateTime(), nullable=False),
        sa.Column("claim", sa.String(36), nullable=True),
        sa.Column("error", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("event_id", "webhook_id"),
    )
    op.create_index("ix_webhook_deliveries_project_id", "webhook_deliveries", ["project_id"])
    op.create_index("ix_webhook_deliveries_state", "webhook_deliveries", ["state"])


def downgrade():
    op.drop_table("webhook_deliveries")
    op.drop_table("webhooks")
