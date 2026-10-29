import re
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text

from app import content
from app.migrate import migrate
from app.models import Entry, now
from conftest import define, entry, gql
from test_schema_cache import token


def search(client, headers, term, delivery=False, type_key="article"):
    result = gql(
        client,
        headers,
        "query($term:String!,$type:String){entries(typeKey:$type,search:$term){total nodes{id slug title}}}",
        {"term": term, "type": type_key},
        delivery=delivery,
    )
    assert not result.get("errors"), result
    page = result["data"]["entries"]
    assert len(page["nodes"]) == page["total"]
    return page


@pytest.mark.parametrize("term", ["ABC", "café", "שלום", "東京", "%", "_", "\\", "Ab"])
def test_substrings_preserve_case_unicode_and_literal_wildcards(client, admin, term):
    define(client, admin)
    literal = entry(
        client,
        admin,
        slug="literal",
        data={"title": "Mix AbC café שלום 東京 literal%under_score\\tail"},
        status="published",
    )["data"]["saveEntry"]
    entry(client, admin, slug="other", data={"title": "Ordinary"}, status="published")
    headers = token(client, admin)
    for identity, delivery in [(admin, False), (headers, True)]:
        assert [row["id"] for row in search(client, identity, term, delivery)["nodes"]] == [literal["id"]]
        assert search(client, identity, "missing-needle", delivery)["total"] == 0


def test_search_keeps_live_and_draft_snapshots_separate(client, admin):
    define(client, admin)
    saved = entry(client, admin, slug="live-slug", data={"title": "PublishedUnique"}, status="published")["data"][
        "saveEntry"
    ]
    entry(client, admin, slug="draft-slug", data={"title": "DraftUnique"}, id=saved["id"], version=saved["version"])
    headers = token(client, admin)
    assert search(client, headers, "publishedunique", True)["total"] == 1
    assert search(client, headers, "draftunique", True)["total"] == 0
    assert search(client, admin, "publishedunique")["total"] == 0
    assert search(client, admin, "draftunique")["total"] == 1
    assert search(client, headers, "live-slug", True)["total"] == 1
    assert search(client, headers, "draft-slug", True)["total"] == 0


def test_search_uses_current_title_privacy_and_workspace_token_scopes(client, admin):
    definition = define(client, admin)
    entry(client, admin, slug="public-slug", data={"title": "SecretNeedle"}, status="published")
    define(client, admin, key="restricted")
    entry(client, admin, key="restricted", slug="restricted-slug", data={"title": "SecretNeedle"}, status="published")
    project = client.post("/api/projects", headers=admin, json={"name": "Other"}).json()
    other = {**admin, "x-moss-project": project["id"]}
    define(client, other)
    entry(client, other, slug="other-slug", data={"title": "SecretNeedle"}, status="published")
    headers = token(client, admin)
    assert search(client, headers, "secretneedle", True, None)["total"] == 1
    result = gql(
        client,
        admin,
        'mutation($version:Int!){saveContentType(key:"article",name:"Article",fields:[{name:"title",type:"text",private:true}],version:$version){id}}',
        {"version": definition["version"]},
    )
    assert not result.get("errors"), result
    for type_key in [None, "article"]:
        assert search(client, headers, "secretneedle", True, type_key)["total"] == 0
        assert search(client, headers, "public-slug", True, type_key)["total"] == 1
    assert search(client, admin, "secretneedle")["total"] == 1
    assert gql(client, headers, '{entries(typeKey:"restricted",search:"SecretNeedle"){total}}', delivery=True).get(
        "errors"
    )


def test_populated_search_upgrade_and_downgrade_preserve_entries(app, client, admin):
    define(client, admin)
    entry(client, admin, data={"title": "Preserved"}, status="published")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    config.attributes["engine"] = app.state.engine
    with app.state.engine.connect() as connection:
        before = connection.execute(select(Entry.__table__)).mappings().all()
    command.downgrade(config, "0013")
    migrate(app.state.engine)
    with app.state.engine.connect() as connection:
        assert connection.execute(select(Entry.__table__)).mappings().all() == before
    indexes = {row["name"] for row in inspect(app.state.engine).get_indexes("entries")}
    expected = {"ix_entries_draft_search", "ix_entries_published_search"}
    assert expected <= indexes if app.state.engine.dialect.name == "postgresql" else not expected & indexes
    assert search(client, token(client, admin), "preserved", True)["total"] == 1


@pytest.mark.postgres
def test_generic_postgres_substring_plan_uses_trigrams_and_rechecks_matches(app, client, admin):
    assert app.state.engine.dialect.name == "postgresql"
    from psycopg.sql import Literal

    definition = define(client, admin)
    with app.state.engine.begin() as connection:
        connection.execute(
            Entry.__table__.insert(),
            [
                {
                    "project_id": admin["x-moss-project"],
                    "type_id": definition["id"],
                    "slug": f"doc-{i:06d}",
                    "title": f"Draft record {i}",
                    "data": {"title": f"Draft record {i}"},
                    "published_data": {"title": f"Live record {i}"},
                    "published_title": f"Live record {i}",
                    "published_slug": f"doc-{i:06d}",
                    "published_at": now(),
                    "status": "published",
                }
                for i in range(10000)
            ],
        )
        # Match populated migration builds rather than timing an unflushed bulk-insert pending list.
        connection.execute(text("REINDEX INDEX ix_entries_published_search"))
        connection.execute(text("ANALYZE entries"))
    identity = {"project_id": admin["x-moss-project"], "role": "reader", "delivery": True, "scopes": ["article"]}
    with app.state.db() as session:
        session.execute(text("SET LOCAL plan_cache_mode = force_generic_plan"))
        raw = session.connection().connection.driver_connection
        for term, expected in [("doc-000002", 1), ("missing-needle", 0)]:
            page = content.entry_page(session, identity, "article", search=term, include_total=False)
            compiled = page["totalQuery"].compile(
                dialect=app.state.engine.dialect, compile_kwargs={"render_postcompile": True}
            )
            with raw.cursor() as cursor:
                cursor.execute(str(compiled), compiled.params, prepare=True)
                assert cursor.fetchone()[0] == expected
                cursor.execute("SELECT name FROM pg_prepared_statements WHERE statement LIKE 'SELECT count(%%'")
                name = cursor.fetchone()[0]
                names = list(dict.fromkeys(re.findall(r"%\(([^)]+)\)s", str(compiled))))
                args = ", ".join(Literal(compiled.params[key]).as_string(raw) for key in names)
                cursor.execute(f'EXPLAIN (ANALYZE, FORMAT JSON) EXECUTE "{name}"({args})')
                plan = cursor.fetchone()[0][0]["Plan"]
            assert "ix_entries_published_search" in str(plan)
