from datetime import timedelta
import re

import pytest
from sqlalchemy import MetaData, Table, create_engine, delete, event, inspect, select, text, update

from app import content
from app.indexing import index_rows, rebuild, scalar_hash
from app.migrate import migrate
from app.models import Entry, EntryFieldIndex, now
from conftest import database_url, define, drop_test_database, entry, gql
from test_schema_cache import token


def count(client, headers, filters, delivery=False):
    result = gql(
        client,
        headers,
        'query($filters:JSON!){entries(typeKey:"article",filters:$filters){total nodes{id}}}',
        {"filters": filters},
        delivery=delivery,
    )
    assert not result.get("errors"), result
    return result["data"]["entries"]["total"]


def test_hashes_preserve_scalar_types_numeric_equality_and_accepted_strings():
    assert scalar_hash(2) == scalar_hash(2.0)
    assert scalar_hash(-0.0) == scalar_hash(0)
    assert len({scalar_hash(True), scalar_hash(1), scalar_hash("1")}) == 3
    assert scalar_hash("שלום\0" + "x" * 100000) == scalar_hash("שלום\0" + "x" * 100000)
    for value in (None, {}, [], float("nan"), float("inf"), 10**1000):
        assert scalar_hash(value) is None
    assert len(scalar_hash("large" * 20000)) == 64


def test_indexes_follow_drafts_live_snapshots_and_unpublishing(client, admin):
    define(client, admin)
    saved = entry(client, admin, data={"title": "Live", "body": "text"}, status="published")["data"]["saveEntry"]
    updated = entry(client, admin, data={"title": "Draft", "body": "text"}, id=saved["id"], version=saved["version"])[
        "data"
    ]["saveEntry"]
    delivery = token(client, admin)
    assert count(client, admin, {"title": "Draft"}) == 1
    assert count(client, admin, {"title": "Live"}) == 0
    assert count(client, delivery, {"title": "Live"}, True) == 1
    assert count(client, delivery, {"title": "Draft"}, True) == 0
    result = gql(
        client,
        admin,
        "mutation($id:ID!,$version:Int!){unpublishEntry(id:$id,version:$version){id}}",
        {"id": updated["id"], "version": updated["version"]},
    )
    assert not result.get("errors"), result
    assert count(client, delivery, {"title": "Live"}, True) == 0
    with client.app.state.engine.connect() as connection:
        assert (
            connection.scalar(select(EntryFieldIndex.entry_id).where(EntryFieldIndex.snapshot == "published")) is None
        )


def test_due_publication_indexes_captured_revision_not_later_draft(app, client, admin):
    define(client, admin)
    saved = entry(
        client,
        admin,
        data={"title": "Captured", "body": "text"},
        status="scheduled",
        scheduledAt=(now() + timedelta(hours=1)).isoformat() + "Z",
    )["data"]["saveEntry"]
    entry(client, admin, data={"title": "Later", "body": "text"}, id=saved["id"], version=saved["version"])
    with app.state.db.begin() as session:
        session.get(Entry, saved["id"]).scheduled_at = now() - timedelta(seconds=1)
    content.publish_due(app.state.db)
    delivery = token(client, admin)
    assert count(client, delivery, {"title": "Captured"}, True) == 1
    assert count(client, delivery, {"title": "Later"}, True) == 0
    assert count(client, admin, {"title": "Later"}) == 1


def test_schema_rename_reindexes_and_private_fields_stay_forbidden(client, admin):
    definition = define(client, admin)
    entry(client, admin, data={"title": "Live", "body": "Renamed", "secret": "hidden"}, status="published")
    result = gql(
        client,
        admin,
        'mutation($fields:JSON!,$version:Int!){saveContentType(key:"article",name:"Article",fields:$fields,version:$version,migration:{rename:{body:"summary"}}){id}}',
        {
            "version": definition["version"],
            "fields": [
                {"name": "title", "type": "text"},
                {"name": "summary", "type": "text"},
                {"name": "secret", "type": "text", "private": True},
            ],
        },
    )
    assert not result.get("errors"), result
    delivery = token(client, admin)
    assert count(client, delivery, {"summary": "Renamed"}, True) == 1
    result = gql(client, delivery, '{entries(typeKey:"article",filters:{secret:"hidden"}){total}}', delivery=True)
    assert result.get("errors")
    with client.app.state.engine.connect() as connection:
        assert connection.scalar(select(EntryFieldIndex.entry_id).where(EntryFieldIndex.field == "body")) is None


def test_index_changes_roll_back_and_hash_candidates_are_rechecked(app, client, admin):
    define(client, admin)
    saved = entry(client, admin, data={"title": "Live", "body": "text"}, status="published")["data"]["saveEntry"]
    other = entry(client, admin, "other", data={"title": "Other", "body": "text"}, status="published")["data"][
        "saveEntry"
    ]
    with pytest.raises(RuntimeError), app.state.db.begin() as session:
        session.get(Entry, saved["id"]).data = {"title": "Rolled back"}
        session.flush()
        raise RuntimeError("abort")
    assert count(client, admin, {"title": "Live"}) == 1
    assert count(client, admin, {"title": "Rolled back"}) == 0
    with app.state.engine.begin() as connection:
        connection.execute(
            update(EntryFieldIndex)
            .where(EntryFieldIndex.entry_id == other["id"], EntryFieldIndex.field == "title")
            .values(value_hash=bytes.fromhex(scalar_hash("Live")))
        )
    assert count(client, token(client, admin), {"title": "Live"}, True) == 1


def test_rebuild_repairs_direct_writes_and_hard_delete_cleans_up(app, client, admin):
    definition = define(client, admin)
    with app.state.db.begin() as session:
        record = Entry(
            project_id=admin["x-moss-project"], type_id=definition["id"], slug="raw", title="Raw", data={"title": "Raw"}
        )
        session.add(record)
        session.flush()
        record_id = record.id
    with app.state.engine.begin() as connection:
        connection.execute(delete(EntryFieldIndex).where(EntryFieldIndex.entry_id == record_id))
        assert rebuild(connection, Entry.__table__, EntryFieldIndex.__table__, admin["x-moss-project"]) == 1
    assert count(client, admin, {"title": "Raw"}) == 1
    with app.state.db.begin() as session:
        session.delete(session.get(Entry, record_id))
    with app.state.engine.connect() as connection:
        assert connection.scalar(select(EntryFieldIndex.entry_id)) is None


def test_populated_upgrade_backfills_in_batches_without_changing_snapshots(tmp_path):
    url = database_url(tmp_path)
    engine = create_engine(url)
    try:
        migrate(engine, "0010")
        metadata = MetaData()
        projects, types, entries = [
            Table(name, metadata, autoload_with=engine) for name in ("projects", "content_types", "entries")
        ]
        rows = [
            dict(
                id=f"fixture-{i:04d}",
                project_id="project",
                type_id="type",
                slug=f"fixture-{i}",
                title="Draft",
                data={"title": "Draft\0שלום", "number": 2, "flag": True, "nested": {"en": "localized"}},
                published_data={"title": "Live", "number": 2.0, "flag": False},
                published_slug=f"live-{i}",
                scheduled_data={"title": "Captured"},
                status="scheduled",
                version=7,
                updated_at=now(),
            )
            for i in range(501)
        ]
        with engine.begin() as connection:
            connection.execute(projects.insert(), dict(id="project", name="Fixture", created_at=now()))
            connection.execute(
                types.insert(),
                dict(
                    id="type",
                    project_id="project",
                    key="article",
                    name="Article",
                    fields=[{"name": "title", "type": "text"}],
                    version=1,
                ),
            )
            connection.execute(entries.insert(), rows)
            before = connection.execute(select(entries).order_by(entries.c.id)).mappings().all()
        migrate(engine)
        index = Table("entry_field_indexes", MetaData(), autoload_with=engine)
        with engine.connect() as connection:
            assert connection.execute(select(entries).order_by(entries.c.id)).mappings().all() == before
            projected = connection.execute(select(index)).mappings().all()
            assert len(projected) == 501 * 2
            assert dict(projected[0]) in index_rows(rows[0])
        assert "ix_entry_fields_lookup" in {item["name"] for item in inspect(engine).get_indexes(index.name)}
    finally:
        engine.dispose()
        drop_test_database(url)


def test_scalar_lookup_has_usable_covering_index(app, client, admin):
    definition = define(client, admin)
    entry(client, admin)
    with app.state.engine.begin() as connection:
        connection.execute(
            Entry.__table__.insert(),
            [
                {
                    "project_id": admin["x-moss-project"],
                    "type_id": definition["id"],
                    "slug": f"plan-{i}",
                    "title": f"Title {i}",
                    "data": {"title": f"Title {i}"},
                }
                for i in range(500)
            ],
        )
        rebuild(connection, Entry.__table__, EntryFieldIndex.__table__, admin["x-moss-project"])
        connection.execute(text("ANALYZE"))
    with app.state.engine.connect() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SET LOCAL enable_seqscan = off"))
            prefix = "EXPLAIN "
        else:
            prefix = "EXPLAIN QUERY PLAN "
        plan = connection.execute(
            text(
                prefix
                + "SELECT entry_id FROM entry_field_indexes WHERE project_id = :project AND type_id = :type AND snapshot = 'draft' AND field = 'title' AND value_hash = :hash"
            ),
            {"project": admin["x-moss-project"], "type": definition["id"], "hash": bytes.fromhex(scalar_hash("hello"))},
        ).all()
        assert "ix_entry_fields_lookup" in str(plan)


def test_multiple_scalar_filters_remain_scoped_to_workspace_and_type(client, admin):
    fields = [
        {"name": "title", "type": "text"},
        {"name": "price", "type": "number"},
        {"name": "enabled", "type": "boolean"},
        {"name": "translated", "type": "text", "localized": True},
    ]
    define(client, admin, fields=fields)
    data = {"title": "Same", "price": 2, "enabled": True, "translated": {"en": "Same"}}
    entry(client, admin, data=data, status="published")
    define(client, admin, key="restricted", fields=fields)
    entry(client, admin, key="restricted", data=data, status="published")
    project = client.post("/api/projects", headers=admin, json={"name": "Other"}).json()
    other = {**admin, "x-moss-project": project["id"]}
    define(client, other, fields=fields)
    entry(client, other, data=data, status="published")
    delivery = token(client, admin)
    assert count(client, delivery, {"title": "Same", "price": 2.0, "enabled": True}, True) == 1
    assert count(client, delivery, {"price": 2, "enabled": False}, True) == 0
    assert count(client, delivery, {"price": "2"}, True) == 1
    result = gql(client, delivery, '{entries(typeKey:"restricted",filters:{title:"Same"}){total}}', delivery=True)
    assert result.get("errors")
    result = gql(client, delivery, '{entries(typeKey:"article",filters:{translated:"Same"}){total}}', delivery=True)
    assert result.get("errors")


def test_index_writes_touch_only_changed_scalar_fields(app, client, admin):
    define(
        client,
        admin,
        fields=[
            {"name": "title", "type": "text"},
            {"name": "body", "type": "richText", "localized": True},
            {"name": "flag", "type": "boolean"},
        ],
    )
    saved = entry(client, admin, data={"title": "Stable", "body": {"en": "One"}, "flag": False}, status="published")[
        "data"
    ]["saveEntry"]
    changes = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        if "entry_field_indexes" in statement and statement.startswith(("INSERT", "DELETE")):
            changes.append((statement.split()[0], cursor.rowcount))

    event.listen(app.state.engine, "after_cursor_execute", capture)
    try:
        for data, expected in [
            ({"title": "Changed", "body": {"en": "One"}, "flag": False}, [("DELETE", 1), ("INSERT", 1)]),
            ({"title": "Changed", "body": {"en": "Two"}, "flag": False}, []),
            ({"title": "Changed", "body": {"en": "Two"}}, [("DELETE", 1)]),
        ]:
            changes.clear()
            result = entry(client, admin, data=data, id=saved["id"], version=saved["version"])
            assert not result.get("errors"), result
            saved = result["data"]["saveEntry"]
            assert changes == expected
        assert count(client, token(client, admin), {"title": "Stable"}, True) == 1
        assert count(client, admin, {"flag": False}) == 0
    finally:
        event.remove(app.state.engine, "after_cursor_execute", capture)


def test_compact_hash_upgrade_and_downgrade_preserve_derived_rows(tmp_path):
    from alembic import command
    from alembic.config import Config
    from pathlib import Path

    engine = create_engine(database_url(tmp_path))
    try:
        migrate(engine, "0012")
        metadata = MetaData()
        tables = {
            name: Table(name, metadata, autoload_with=engine)
            for name in ("projects", "content_types", "entries", "entry_field_indexes")
        }
        with engine.begin() as connection:
            connection.execute(tables["projects"].insert(), {"id": "p", "name": "Fixture", "created_at": now()})
            connection.execute(
                tables["content_types"].insert(),
                {
                    "id": "t",
                    "project_id": "p",
                    "key": "article",
                    "name": "Articles",
                    "fields": [{"name": "title", "type": "text"}],
                    "version": 1,
                },
            )
            connection.execute(
                tables["entries"].insert(),
                [
                    {
                        "id": f"e{i:04d}",
                        "project_id": "p",
                        "type_id": "t",
                        "slug": f"e{i}",
                        "title": "Draft",
                        "data": {"title": "Draft\0שלום"},
                        "published_data": {"title": "Live"},
                        "published_slug": f"live{i}",
                        "status": "published",
                        "version": 1,
                        "updated_at": now(),
                    }
                    for i in range(1001)
                ],
            )
            rebuild(connection, tables["entries"], tables["entry_field_indexes"])
            before = (
                connection.execute(
                    select(tables["entry_field_indexes"]).order_by(*tables["entry_field_indexes"].primary_key)
                )
                .mappings()
                .all()
            )
        with engine.begin() as connection:
            connection.execute(
                tables["entry_field_indexes"].insert(),
                [
                    {
                        "entry_id": f"e{i:04d}",
                        "snapshot": "draft",
                        "field": "legacyReference",
                        "project_id": "p",
                        "type_id": "t",
                        "value_hash": scalar_hash("unused"),
                    }
                    for i in range(1001)
                ],
            )
        migrate(engine)
        compact = Table("entry_field_indexes", MetaData(), autoload_with=engine)
        with engine.connect() as connection:
            after = connection.execute(select(compact).order_by(*compact.primary_key)).mappings().all()
            assert len(after) == len(before) == 2002
            assert [{**row, "value_hash": row["value_hash"].hex()} for row in after] == before
            assert all(len(row["value_hash"]) == 32 for row in after)
        root = Path(__file__).resolve().parents[1]
        config = Config(str(root / "alembic.ini"))
        config.set_main_option("script_location", str(root / "migrations"))
        config.attributes["engine"] = engine
        command.downgrade(config, "0012")
        restored = Table("entry_field_indexes", MetaData(), autoload_with=engine)
        with engine.connect() as connection:
            assert connection.execute(select(restored).order_by(*restored.primary_key)).mappings().all() == before
        migrate(engine)
    finally:
        url = engine.url.render_as_string(hide_password=False)
        engine.dispose()
        drop_test_database(url)


def test_projection_excludes_references_assets_localized_and_unknown_fields(app, client, admin):
    definition = define(
        client,
        admin,
        fields=[
            {"name": "title", "type": "text"},
            {"name": "secret", "type": "text", "private": True},
            {"name": "related", "type": "reference", "target": "article"},
            {"name": "cover", "type": "asset"},
            {"name": "translated", "type": "text", "localized": True},
        ],
    )
    data = {
        "title": "Kept",
        "secret": "Kept private",
        "related": "legacy-reference",
        "cover": "legacy-asset",
        "translated": "legacy scalar",
        "unknown": "unused",
    }
    with app.state.engine.begin() as connection:
        connection.execute(
            Entry.__table__.insert(),
            {
                "id": "legacy",
                "project_id": admin["x-moss-project"],
                "type_id": definition["id"],
                "slug": "legacy",
                "title": "Kept",
                "data": data,
            },
        )
        rebuild(connection, Entry.__table__, EntryFieldIndex.__table__, admin["x-moss-project"])
        assert set(connection.scalars(select(EntryFieldIndex.field))) == {"title", "secret"}
    with app.state.db.begin() as session:
        record = session.get(Entry, "legacy")
        record.data = {**data, "title": "Updated"}
        session.flush()
        assert set(session.scalars(select(EntryFieldIndex.field))) == {"title", "secret"}


def test_schema_field_reclassification_reindexes_unchanged_values(app, client, admin):
    fields = [{"name": "title", "type": "text"}, {"name": "link", "type": "text"}]
    definition = define(client, admin, fields=fields)
    target = entry(client, admin, "target", data={"title": "Target"}, status="published")["data"]["saveEntry"]
    saved = entry(client, admin, "source", data={"title": "Source", "link": target["id"]}, status="published")["data"][
        "saveEntry"
    ]
    query = 'mutation($fields:JSON!,$version:Int!){saveContentType(key:"article",name:"Articles",fields:$fields,version:$version){version}}'
    version = definition["version"]
    for schema, expected in [
        (fields[:1] + [{"name": "link", "type": "reference", "target": "article"}], 0),
        (fields, 2),
    ]:
        result = gql(client, admin, query, {"fields": schema, "version": version})
        assert not result.get("errors"), result
        version = result["data"]["saveContentType"]["version"]
        with app.state.engine.connect() as connection:
            assert (
                len(
                    connection.execute(
                        select(EntryFieldIndex).where(
                            EntryFieldIndex.entry_id == saved["id"], EntryFieldIndex.field == "link"
                        )
                    ).all()
                )
                == expected
            )
    assert count(client, token(client, admin), {"link": target["id"]}, True) == 1


def test_string_totals_use_exact_projection_values_including_long_prefix_collisions(app, client, admin):
    define(client, admin)
    values = ["Short", "x" * 1024, "x" * 1024 + "a", "x" * 1024 + "b"]
    for i, value in enumerate(values):
        result = entry(client, admin, f"row-{i}", data={"title": str(i), "body": value}, status="published")
        assert not result.get("errors"), result
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT count("):
            statements.append(statement)

    event.listen(app.state.engine, "before_cursor_execute", capture)
    try:
        headers = token(client, admin)
        for value in values:
            assert count(client, headers, {"body": value}, True) == 1
        assert len(statements) == len(values)
        assert all("entry_field_indexes" in sql and "CASE WHEN" in sql for sql in statements)
        assert all("published_data" not in sql.split("WHERE", 1)[1] for sql in statements)
    finally:
        event.remove(app.state.engine, "before_cursor_execute", capture)


def test_string_totals_preserve_scalar_type_guards_for_legacy_values(app, client, admin):
    definition = define(client, admin)
    with app.state.engine.begin() as connection:
        connection.execute(
            Entry.__table__.insert(),
            {
                "id": "legacy-bool",
                "project_id": admin["x-moss-project"],
                "type_id": definition["id"],
                "slug": "legacy",
                "title": "Legacy",
                "data": {"title": "Legacy", "body": True},
            },
        )
        rebuild(connection, Entry.__table__, EntryFieldIndex.__table__, admin["x-moss-project"])
    assert count(client, admin, {"body": "\x01"}) == 0


def test_common_string_count_avoids_per_match_probes_in_generic_postgres_plan(app, client, admin):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL generic prepared plans")
    from psycopg.sql import Literal

    definition = define(client, admin)
    with app.state.engine.begin() as connection:
        connection.execute(
            Entry.__table__.insert(),
            [
                {
                    "project_id": admin["x-moss-project"],
                    "type_id": definition["id"],
                    "slug": f"count-{i}",
                    "title": f"Title {i}",
                    "data": {"body": "Common" if i < 1000 else "Rare" if i == 1000 else "Other"},
                    "published_data": {"body": "Common" if i < 1000 else "Rare" if i == 1000 else "Other"},
                    "published_slug": f"count-{i}",
                    "published_at": now(),
                    "status": "published",
                }
                for i in range(1200)
            ],
        )
        rebuild(connection, Entry.__table__, EntryFieldIndex.__table__, admin["x-moss-project"])
        connection.execute(text("ANALYZE"))
    identity = {"project_id": admin["x-moss-project"], "role": "reader", "delivery": True, "scopes": ["article"]}
    with app.state.db() as session:
        session.execute(text("SET LOCAL plan_cache_mode = force_generic_plan"))
        raw = session.connection().connection.driver_connection
        for value, expected in [("Common", 1000), ("Rare", 1), ("Absent", 0)]:
            page = content.entry_page(session, identity, "article", filters={"body": value}, include_total=False)
            compiled = page["totalQuery"].compile(
                dialect=app.state.engine.dialect, compile_kwargs={"render_postcompile": True}
            )
            with raw.cursor() as cursor:
                cursor.execute(str(compiled), compiled.params, prepare=True)
                assert cursor.fetchone()[0] == expected
                cursor.execute("SELECT name FROM pg_prepared_statements WHERE statement LIKE 'SELECT count(%%'")
                prepared_name = cursor.fetchone()[0]
                names = list(dict.fromkeys(re.findall(r"%\(([^)]+)\)s", str(compiled))))
                arguments = ", ".join(Literal(compiled.params[name]).as_string(raw) for name in names)
                cursor.execute(f'EXPLAIN (ANALYZE, FORMAT JSON) EXECUTE "{prepared_name}"({arguments})')
                plan = cursor.fetchone()[0][0]["Plan"]

            def nodes(node):
                yield node
                for child in node.get("Plans", []):
                    yield from nodes(child)

            assert all(node.get("Index Name") != "entries_pkey" for node in nodes(plan))
            assert all(
                node["Actual Loops"] <= 1 for node in nodes(plan) if node.get("Relation Name") == "content_types"
            )
