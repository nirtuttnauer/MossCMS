from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event, Thread
import pytest
from sqlalchemy import select, text
from app.models import Entry, PublicationEvent, database, now
from app.content import publish_due
from app.outbox import claim_events
from conftest import define, entry


@pytest.mark.postgres
def test_postgres_workers_skip_locked_rows_and_claim_once(app, client, admin):
    assert app.state.engine.dialect.name == "postgresql"
    define(client, admin)
    ids = []
    for i in range(10):
        ids.append(
            entry(
                client,
                admin,
                slug=f"scheduled-{i}",
                status="scheduled",
                scheduledAt=(now() + timedelta(hours=1)).isoformat(),
            )["data"]["saveEntry"]["id"]
        )
    with app.state.db.begin() as session:
        for id in ids:
            session.get(Entry, id).scheduled_at = now() - timedelta(seconds=1)
    with app.state.db.begin() as lock:
        lock.scalar(select(Entry).where(Entry.id == ids[0]).with_for_update())
        with ThreadPoolExecutor(2) as workers:
            list(workers.map(lambda _: publish_due(app.state.db), range(2)))
        with app.state.db() as session:
            assert session.get(Entry, ids[0]).published_slug is None
            assert len(session.scalars(select(PublicationEvent)).all()) == 9
    publish_due(app.state.db)
    with ThreadPoolExecutor(2) as workers:
        claims = list(workers.map(lambda _: claim_events(app.state.db), range(2)))
    all_claims = [row["id"] for batch in claims for row in batch]
    assert len(all_claims) == len(set(all_claims)) == 10


def test_sqlite_savepoint_transaction_waits_for_a_committing_writer(tmp_path):
    # publish_due and run_release write inside begin_nested() while request or worker threads commit their own writes.
    engine, factory = database(f"sqlite:///{tmp_path}/locks.db")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE counter (id INTEGER PRIMARY KEY, n INTEGER NOT NULL)"))
        connection.execute(text("INSERT INTO counter VALUES (1, 0)"))
    writing, reading = Event(), Event()

    def writer():
        with factory.begin() as session:
            session.execute(text("UPDATE counter SET n = n + 1"))
            writing.set()
            # Without the write lock up front, the savepoint transaction reads first and this commit then waits for its
            # shared lock. With it, the savepoint transaction waits for this commit, so the wait here times out.
            reading.wait(0.5)

    thread = Thread(target=writer)
    thread.start()
    assert writing.wait(5)
    with factory.begin() as session, session.begin_nested():
        session.execute(text("SELECT n FROM counter")).scalar_one()
        reading.set()
        thread.join(0.1)
        session.execute(text("UPDATE counter SET n = n + 10"))
    thread.join()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT n FROM counter")).scalar_one() == 11
    engine.dispose()
