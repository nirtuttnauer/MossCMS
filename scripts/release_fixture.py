#!/usr/bin/env python3
"""Seed/verify only disposable loopback moss_release_* databases; never production."""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import MetaData, create_engine, inspect, text
from sqlalchemy.engine import make_url


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
    from app.migrate import migrate

    mode = argparse.ArgumentParser()
    mode.add_argument("action", choices=["seed", "verify-upgrade"])
    args = mode.parse_args()
    url = os.environ["MOSS_RELEASE_DATABASE_URL"]
    parsed = make_url(url)
    if parsed.host not in {"localhost", "127.0.0.1"} or not (parsed.database or "").startswith("moss_release_"):
        raise SystemExit("Refusing to write outside an explicit loopback moss_release_* fixture database.")
    engine = create_engine(url)
    if args.action == "seed":
        if inspect(engine).get_table_names():
            raise SystemExit("Seed requires an empty disposable database.")
        migrate(engine, "0001")
        metadata = MetaData()
        metadata.reflect(engine)
        instant = datetime(2026, 10, 7, 12)
        with engine.begin() as connection:
            connection.execute(
                metadata.tables["projects"].insert(),
                dict(id="legacy-project", name="Legacy workspace", created_at=instant),
            )
            connection.execute(
                metadata.tables["content_types"].insert(),
                dict(
                    id="legacy-type",
                    project_id="legacy-project",
                    key="legacyPost",
                    name="Legacy post",
                    fields=[
                        {"name": "title", "type": "text"},
                        {"name": "body", "type": "richText"},
                    ],
                    version=4,
                ),
            )
            rows = []
            for index in range(1004):
                state = ["published", "scheduled", "deleted", "draft"][index] if index < 4 else "draft"
                rows.append(
                    dict(
                        id=f"legacy-{index}",
                        project_id="legacy-project",
                        type_id="legacy-type",
                        slug=f"legacy-{index}",
                        title=f"Legacy {index}",
                        data={"title": f"Legacy {index}", "body": "Working"},
                        published_data={"title": f"Legacy {index}", "body": "Live"} if state == "published" else None,
                        status=state,
                        scheduled_at=datetime(2030, 1, 1) if state == "scheduled" else None,
                        version=7,
                        updated_at=instant,
                    )
                )
            connection.execute(metadata.tables["entries"].insert(), rows)
            connection.execute(
                metadata.tables["revisions"].insert(),
                dict(
                    id="legacy-revision",
                    project_id="legacy-project",
                    entry_id="legacy-0",
                    number=2,
                    snapshot={"data": {"body": "Historical"}},
                    author="owner",
                    created_at=instant,
                ),
            )
        print("Seeded schema0001: 1004 entries, one revision, one workspace, one content type.")
    else:
        with engine.connect() as connection:
            before = connection.execute(text("select id,slug,data,status,version from entries order by id")).all()
            history = connection.execute(text("select id,entry_id,number,snapshot from revisions order by id")).all()
        started = time.perf_counter()
        migrate(engine)
        duration = time.perf_counter() - started
        with engine.connect() as connection:
            after = connection.execute(text("select id,slug,data,status,version from entries order by id")).all()
            assert before == after
            assert (
                history
                == connection.execute(text("select id,entry_id,number,snapshot from revisions order by id")).all()
            )
            assert (
                connection.execute(text("select published_slug from entries where id='legacy-0'")).scalar_one()
                == "legacy-0"
            )
            assert (
                connection.execute(text("select scheduled_revision from entries where id='legacy-1'")).scalar_one() == 7
            )
            assert (
                connection.execute(text("select count(*) from entries where published_slug is not null")).scalar_one()
                == 1
            )
            print(
                json.dumps(
                    {
                        "upgradeSeconds": round(duration, 4),
                        "entriesPreserved": len(after),
                        "historyPreserved": len(history),
                        "schema": connection.execute(text("select version_num from alembic_version")).scalar_one(),
                    }
                )
            )
    engine.dispose()


if __name__ == "__main__":
    main()
