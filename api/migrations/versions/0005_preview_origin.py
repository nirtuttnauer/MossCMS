"""Trusted website preview origin per workspace."""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("projects", sa.Column("preview_origin", sa.String(2048), nullable=True))


def downgrade():
    op.drop_column("projects", "preview_origin")
