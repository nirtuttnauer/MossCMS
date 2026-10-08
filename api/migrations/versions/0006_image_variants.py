"""Optional dimensions and precomputed image variants."""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    for name, kind in [("width", sa.Integer()), ("height", sa.Integer()), ("variants", sa.JSON())]:
        op.add_column("assets", sa.Column(name, kind, nullable=True))


def downgrade():
    for name in ["variants", "height", "width"]:
        op.drop_column("assets", name)
