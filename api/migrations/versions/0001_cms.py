"""Versioned CMS schema and non-destructive import of the Article starter."""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=254), nullable=False),
        sa.Column("key", sa.String(length=300), nullable=False),
        sa.Column("storage", sa.String(length=16), nullable=False),
        sa.Column("mime", sa.String(length=100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_assets_project_id"), "assets", ["project_id"], unique=False)
    op.create_table(
        "audit",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("actor", sa.String(length=254), nullable=False),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_project_id"), "audit", ["project_id"], unique=False)
    op.create_table(
        "content_types",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "key"),
    )
    op.create_index(op.f("ix_content_types_project_id"), "content_types", ["project_id"], unique=False)
    op.create_table(
        "memberships",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("project_id", "user_id"),
    )
    op.create_table(
        "oauth_identities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("subject", sa.String(length=254), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "subject"),
    )
    op.create_index(op.f("ix_oauth_identities_user_id"), "oauth_identities", ["user_id"], unique=False)
    op.create_table(
        "tokens",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("csrf", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tokens_kind"), "tokens", ["kind"], unique=False)
    op.create_table(
        "entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("type_id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=220), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("published_data", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("author_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.ForeignKeyConstraint(
            ["type_id"],
            ["content_types.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "type_id", "slug"),
    )
    op.create_index(op.f("ix_entries_project_id"), "entries", ["project_id"], unique=False)
    op.create_index(op.f("ix_entries_status"), "entries", ["status"], unique=False)
    op.create_index(op.f("ix_entries_type_id"), "entries", ["type_id"], unique=False)
    op.create_index(op.f("ix_entries_updated_at"), "entries", ["updated_at"], unique=False)
    op.create_table(
        "schema_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("type_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["type_id"],
            ["content_types.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("entry_id", sa.String(length=36), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("author", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["entries.id"],
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entry_id", "number"),
    )
    op.create_index(op.f("ix_revisions_entry_id"), "revisions", ["entry_id"], unique=False)
    op.create_index(op.f("ix_revisions_project_id"), "revisions", ["project_id"], unique=False)

    # Preserve and import the original Article starter table without dropping it.
    bind = op.get_bind()
    if "articles" in sa.inspect(bind).get_table_names():
        from datetime import datetime, timezone
        from uuid import NAMESPACE_URL, uuid5

        project_id = str(uuid5(NAMESPACE_URL, "mosscms:legacy:project"))
        type_id = str(uuid5(NAMESPACE_URL, "mosscms:legacy:article"))
        current = datetime.now(timezone.utc).replace(tzinfo=None)
        project = sa.table("projects", sa.column("id"), sa.column("name"), sa.column("created_at"))
        op.bulk_insert(project, [{"id": project_id, "name": "Imported workspace", "created_at": current}])
        fields = [{"name": "title", "type": "text", "required": True}, {"name": "body", "type": "richText"}]
        types = sa.table(
            "content_types",
            sa.column("id"),
            sa.column("project_id"),
            sa.column("key"),
            sa.column("name"),
            sa.column("fields", sa.JSON),
            sa.column("version"),
        )
        op.bulk_insert(
            types,
            [
                {
                    "id": type_id,
                    "project_id": project_id,
                    "key": "article",
                    "name": "Article",
                    "fields": fields,
                    "version": 1,
                }
            ],
        )
        schema_revisions = sa.table(
            "schema_revisions",
            sa.column("id"),
            sa.column("type_id"),
            sa.column("version"),
            sa.column("fields", sa.JSON),
            sa.column("created_at"),
        )
        op.bulk_insert(
            schema_revisions,
            [
                {
                    "id": str(uuid5(NAMESPACE_URL, "mosscms:legacy:schema:1")),
                    "type_id": type_id,
                    "version": 1,
                    "fields": fields,
                    "created_at": current,
                }
            ],
        )
        entries = sa.table(
            "entries",
            sa.column("id"),
            sa.column("project_id"),
            sa.column("type_id"),
            sa.column("slug"),
            sa.column("title"),
            sa.column("data", sa.JSON),
            sa.column("published_data", sa.JSON),
            sa.column("status"),
            sa.column("version"),
            sa.column("updated_at"),
        )
        revisions = sa.table(
            "revisions",
            sa.column("id"),
            sa.column("project_id"),
            sa.column("entry_id"),
            sa.column("number"),
            sa.column("snapshot", sa.JSON),
            sa.column("author"),
            sa.column("created_at"),
        )
        for row in bind.execute(sa.text("SELECT id, title, slug, body, status FROM articles")).mappings():
            entry_id = str(uuid5(NAMESPACE_URL, "mosscms:legacy:entry:" + str(row["id"])))
            data = {"title": row["title"], "body": row["body"]}
            op.bulk_insert(
                entries,
                [
                    {
                        "id": entry_id,
                        "project_id": project_id,
                        "type_id": type_id,
                        "slug": row["slug"],
                        "title": row["title"],
                        "data": data,
                        "published_data": data if row["status"] == "published" else None,
                        "status": row["status"],
                        "version": 1,
                        "updated_at": current,
                    }
                ],
            )
            op.bulk_insert(
                revisions,
                [
                    {
                        "id": str(uuid5(NAMESPACE_URL, entry_id)),
                        "project_id": project_id,
                        "entry_id": entry_id,
                        "number": 1,
                        "snapshot": {
                            "slug": row["slug"],
                            "title": row["title"],
                            "data": data,
                            "status": row["status"],
                            "scheduledAt": None,
                        },
                        "author": "migration",
                        "created_at": current,
                    }
                ],
            )


def downgrade():
    op.drop_index(op.f("ix_revisions_project_id"), table_name="revisions")
    op.drop_index(op.f("ix_revisions_entry_id"), table_name="revisions")
    op.drop_table("revisions")
    op.drop_table("schema_revisions")
    op.drop_index(op.f("ix_entries_updated_at"), table_name="entries")
    op.drop_index(op.f("ix_entries_type_id"), table_name="entries")
    op.drop_index(op.f("ix_entries_status"), table_name="entries")
    op.drop_index(op.f("ix_entries_project_id"), table_name="entries")
    op.drop_table("entries")
    op.drop_index(op.f("ix_tokens_kind"), table_name="tokens")
    op.drop_table("tokens")
    op.drop_index(op.f("ix_oauth_identities_user_id"), table_name="oauth_identities")
    op.drop_table("oauth_identities")
    op.drop_table("memberships")
    op.drop_index(op.f("ix_content_types_project_id"), table_name="content_types")
    op.drop_table("content_types")
    op.drop_index(op.f("ix_audit_project_id"), table_name="audit")
    op.drop_table("audit")
    op.drop_index(op.f("ix_assets_project_id"), table_name="assets")
    op.drop_table("assets")
    op.drop_table("users")
    op.drop_table("projects")
