"""Store scalar hashes as 32 bytes rather than 64 hexadecimal characters."""

from alembic import op
import sqlalchemy as sa

from app.indexing import scalar_fields

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    metadata = sa.MetaData()
    definitions = sa.Table("content_types", metadata, autoload_with=connection)
    index = sa.Table("entry_field_indexes", metadata, autoload_with=connection)
    for type_id, project_id, fields in connection.execute(
        sa.select(definitions.c.id, definitions.c.project_id, definitions.c.fields)
    ):
        connection.execute(
            sa.delete(index).where(
                index.c.project_id == project_id,
                index.c.type_id == type_id,
                index.c.field.not_in(scalar_fields(fields)),
            )
        )
    if connection.dialect.name == "postgresql":
        op.alter_column(
            "entry_field_indexes",
            "value_hash",
            existing_type=sa.String(64),
            type_=sa.LargeBinary(32),
            postgresql_using="decode(value_hash, 'hex')",
        )
    else:
        convert_sqlite(True)
    long_index(True)


def convert_sqlite(binary):
    connection = op.get_bind()
    target = sa.LargeBinary(32) if binary else sa.String(64)
    op.add_column("entry_field_indexes", sa.Column("converted_hash", target))
    table = sa.Table("entry_field_indexes", sa.MetaData(), autoload_with=connection)
    last = None
    while True:
        keys = (table.c.entry_id, table.c.snapshot, table.c.field)
        query = sa.select(*keys, table.c.value_hash).order_by(*keys).limit(1000)
        if last is not None:
            query = query.where(sa.tuple_(*keys) > sa.tuple_(*last))
        rows = connection.execute(query).mappings().all()
        if not rows:
            break
        connection.execute(
            sa.update(table)
            .where(*(column == sa.bindparam("key_" + column.name) for column in keys))
            .values(converted_hash=sa.bindparam("new_hash")),
            [
                {
                    **{"key_" + column.name: row[column.name] for column in keys},
                    "new_hash": bytes.fromhex(row["value_hash"]) if binary else row["value_hash"].hex(),
                }
                for row in rows
            ],
        )
        last = tuple(rows[-1][column.name] for column in keys)
    op.drop_index("ix_entry_fields_lookup", table_name="entry_field_indexes")
    with op.batch_alter_table("entry_field_indexes") as batch:
        batch.drop_column("value_hash")
        batch.alter_column("converted_hash", new_column_name="value_hash", existing_type=target, nullable=False)
    op.create_index(
        "ix_entry_fields_lookup",
        "entry_field_indexes",
        ["project_id", "type_id", "snapshot", "field", "value_hash", "entry_id"],
    )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column(
            "entry_field_indexes",
            "value_hash",
            existing_type=sa.LargeBinary(32),
            type_=sa.String(64),
            postgresql_using="encode(value_hash, 'hex')",
        )
    else:
        convert_sqlite(False)
    long_index(False)


def long_index(compact):
    op.drop_index("ix_entry_fields_long", table_name="entry_field_indexes")
    op.create_index(
        "ix_entry_fields_long",
        "entry_field_indexes",
        (["sort_long"] if compact else []) + ["project_id", "type_id", "snapshot", "field"],
        postgresql_where=sa.text("sort_long IS TRUE"),
        sqlite_where=sa.text("sort_long IS 1"),
    )
