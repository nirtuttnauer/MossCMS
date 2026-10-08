from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from sqlalchemy import select
from app.models import Entry, PublicationEvent, now
from app.content import publish_due
from app.outbox import claim_events
from conftest import define, entry


def test_postgres_workers_skip_locked_rows_and_claim_once(app, client, admin):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row-lock rehearsal")
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
