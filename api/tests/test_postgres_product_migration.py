"""Rehearse the populated locale/path upgrade on a disposable PostgreSQL database."""

import pytest
from sqlalchemy import MetaData, Table, create_engine, select

from app.migrate import migrate
from app.models import now
from conftest import TEST_DATABASE_URL, database_url, drop_test_database


@pytest.mark.skipif(not TEST_DATABASE_URL.startswith("postgresql"), reason="PostgreSQL forward-upgrade rehearsal")
def test_postgres_0009_preserves_localized_live_scheduled_and_revision_data(tmp_path):
    url = database_url(tmp_path)
    engine = create_engine(url)
    try:
        migrate(engine, "0008")
        metadata = MetaData()
        projects = Table("projects", metadata, autoload_with=engine)
        types = Table("content_types", metadata, autoload_with=engine)
        entries = Table("entries", metadata, autoload_with=engine)
        revisions = Table("revisions", metadata, autoload_with=engine)
        working = {"title": {"en": "Working", "he": "טיוטה"}, "secret": "editorial"}
        live = {"title": {"en": "Live", "he": "פורסם"}, "secret": "live-private"}
        captured = {"title": {"en": "Future", "ar": "مستقبل"}, "secret": "scheduled-private"}
        instant = now()
        snapshot = {"slug": "older-working", "data": working, "status": "draft"}
        with engine.begin() as connection:
            connection.execute(
                projects.insert(), {"id": "project", "name": "Disposable upgrade", "created_at": instant}
            )
            connection.execute(
                types.insert(),
                {
                    "id": "type",
                    "project_id": "project",
                    "key": "sitePost",
                    "name": "Posts",
                    "version": 1,
                    "fields": [
                        {"name": "title", "type": "text", "localized": True},
                        {"name": "secret", "type": "text", "private": True},
                    ],
                },
            )
            connection.execute(
                entries.insert(),
                {
                    "id": "entry",
                    "project_id": "project",
                    "type_id": "type",
                    "slug": "working",
                    "title": "Working",
                    "data": working,
                    "published_data": live,
                    "published_slug": "live",
                    "published_title": "Live",
                    "published_at": instant,
                    "published_revision": 2,
                    "published_schema_version": 1,
                    "scheduled_data": captured,
                    "scheduled_slug": "future",
                    "scheduled_title": "Future",
                    "scheduled_at": instant,
                    "scheduled_revision": 3,
                    "scheduled_schema_version": 1,
                    "status": "scheduled",
                    "version": 4,
                    "updated_at": instant,
                },
            )
            connection.execute(
                revisions.insert(),
                {
                    "id": "revision",
                    "project_id": "project",
                    "entry_id": "entry",
                    "number": 1,
                    "snapshot": snapshot,
                    "author": "Synthetic tester",
                    "created_at": instant,
                },
            )
        migrate(engine)
        upgraded = MetaData()
        projects = Table("projects", upgraded, autoload_with=engine)
        entries = Table("entries", upgraded, autoload_with=engine)
        paths = Table("website_paths", upgraded, autoload_with=engine)
        revision_table = Table("revisions", upgraded, autoload_with=engine)
        with engine.connect() as connection:
            project = connection.execute(select(projects)).mappings().one()
            assert project["default_locale"] == "en" and project["locales"] == ["en"]
            entry = connection.execute(select(entries)).mappings().one()
            assert (entry["slug"], entry["data"]) == ("working", working)
            assert (entry["published_slug"], entry["published_data"], entry["published_revision"]) == ("live", live, 2)
            assert (entry["scheduled_slug"], entry["scheduled_data"], entry["scheduled_revision"]) == (
                "future",
                captured,
                3,
            )
            assert entry["scheduled_at"] == instant and entry["version"] == 4
            assert connection.execute(select(revision_table.c.snapshot)).scalar_one() == snapshot
            assert connection.execute(select(paths)).all() == []
    finally:
        engine.dispose()
        drop_test_database(url)
