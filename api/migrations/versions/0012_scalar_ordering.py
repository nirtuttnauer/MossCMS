"""Backfill sortable scalar projections with bounded index keys."""

from alembic import op
import sqlalchemy as sa

from app.indexing import rebuild

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column("sort_key", sa.LargeBinary(), nullable=True),
        sa.Column("sort_prefix", sa.LargeBinary(), nullable=True),
        sa.Column("sort_long", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("date_key", sa.Integer(), nullable=True),
    ):
        op.add_column("entry_field_indexes", column)
    connection = op.get_bind()
    metadata = sa.MetaData()
    entries = sa.Table("entries", metadata, autoload_with=connection)
    index = sa.Table("entry_field_indexes", metadata, autoload_with=connection)
    # Derived rows are rebuilt under the upgrade lock; avoid retaining an obsolete copy.
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text("TRUNCATE TABLE entry_field_indexes"))
    else:
        connection.execute(sa.delete(index))
    rebuild(connection, entries, index, clear_existing=False)
    for name, columns, options in (
        ("ix_entry_fields_order", ["project_id", "type_id", "snapshot", "field", "sort_prefix", "entry_id"], {}),
        (
            "ix_entry_fields_date_order",
            ["project_id", "type_id", "snapshot", "field", "date_key", "entry_id"],
            {"postgresql_where": sa.text("date_key IS NOT NULL"), "sqlite_where": sa.text("date_key IS NOT NULL")},
        ),
        (
            "ix_entry_fields_long",
            ["project_id", "type_id", "snapshot", "field"],
            {
                "postgresql_where": sa.text("sort_long IS TRUE"),
                "sqlite_where": sa.text("sort_long IS 1"),
            },
        ),
    ):
        op.create_index(name, "entry_field_indexes", columns, **options)


def downgrade():
    for name in ("ix_entry_fields_long", "ix_entry_fields_date_order", "ix_entry_fields_order"):
        op.drop_index(name, table_name="entry_field_indexes")
    for column in ("date_key", "sort_long", "sort_prefix", "sort_key"):
        op.drop_column("entry_field_indexes", column)
