from datetime import datetime

from sqlalchemy import MetaData, Table, create_engine, select

from app.migrate import migrate


def test_upgrade_preserves_live_urls_schedules_and_history(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/restored.db")
    migrate(engine, "0001")
    metadata = MetaData()
    projects = Table("projects", metadata, autoload_with=engine)
    types = Table("content_types", metadata, autoload_with=engine)
    entries = Table("entries", metadata, autoload_with=engine)
    revisions = Table("revisions", metadata, autoload_with=engine)
    instant = datetime(2026, 10, 7, 12)
    with engine.begin() as c:
        c.execute(projects.insert(), dict(id="p", name="Restored", created_at=instant))
        c.execute(types.insert(), dict(id="t", project_id="p", key="post", name="Post", fields=[], version=4))
        for state in ["draft", "published", "scheduled", "deleted"]:
            c.execute(
                entries.insert(),
                dict(
                    id=state,
                    project_id="p",
                    type_id="t",
                    slug=state,
                    title=state,
                    data={"body": "working"},
                    published_data={"body": "live"} if state == "published" else None,
                    status=state,
                    scheduled_at=instant if state == "scheduled" else None,
                    version=7,
                    updated_at=instant,
                ),
            )
        c.execute(
            revisions.insert(),
            dict(
                id="r",
                project_id="p",
                entry_id="published",
                number=2,
                snapshot={"data": {"body": "old"}},
                author="owner",
                created_at=instant,
            ),
        )
    migrate(engine)
    entries = Table("entries", MetaData(), autoload_with=engine)
    with engine.connect() as c:
        rows = {r["id"]: r for r in c.execute(select(entries)).mappings()}
        assert rows["published"]["published_slug"] == "published"
        assert rows["published"]["published_data"] == {"body": "live"}
        assert rows["published"]["published_revision"] == 7
        assert rows["published"]["published_schema_version"] == 4
        assert rows["scheduled"]["scheduled_data"] == {"body": "working"}
        assert rows["scheduled"]["scheduled_revision"] == 7
        assert rows["scheduled"]["scheduled_at"] == instant
        assert all(rows[state]["published_slug"] is None for state in ["draft", "scheduled", "deleted"])
        assert c.execute(select(revisions.c.snapshot)).scalar_one() == {"data": {"body": "old"}}
    engine.dispose()
