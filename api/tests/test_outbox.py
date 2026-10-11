from datetime import datetime, timedelta
import pytest
from sqlalchemy import create_engine, insert, select
from sqlalchemy.orm import sessionmaker
from app import outbox
from app.models import Base, Project, PublicationEvent, now
from app.outbox import claim_events, complete_event, prune_events
from conftest import define, entry, gql


@pytest.fixture
def outbox_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Project.__table__, PublicationEvent.__table__])
    factory = sessionmaker(engine)
    with factory.begin() as session:
        session.add(Project(id="project", name="Outbox tests"))
    yield factory
    engine.dispose()


@pytest.mark.parametrize("limit, expected", [(None, 50), (10, 10), (100, 100), (101, 100), (0, 1), (-5, 1)])
def test_claim_limits_and_persisted_leases(outbox_db, monkeypatch, limit, expected):
    clock = datetime(2026, 1, 15, 12)
    monkeypatch.setattr(outbox, "now", lambda: clock)
    with outbox_db.begin() as session:
        session.execute(
            insert(PublicationEvent),
            [
                {"id": f"event-{index:03}", "project_id": "project", "payload": {"index": index}, "created_at": clock}
                for index in reversed(range(101))
            ],
        )
    claimed = claim_events(outbox_db) if limit is None else claim_events(outbox_db, limit)
    assert [event["id"] for event in claimed] == [f"event-{index:03}" for index in range(expected)]
    assert len({event["claim"] for event in claimed}) == expected
    with outbox_db() as session:
        rows = session.scalars(select(PublicationEvent).order_by(PublicationEvent.id)).all()
        for event, row in zip(claimed, rows):
            assert event == {"id": row.id, "project_id": "project", "claim": row.claim, "payload": row.payload}
            assert row.state == "processing"
            assert row.claim
            assert row.lease_until == clock + timedelta(minutes=2)
        assert all(row.state == "pending" and row.claim is None and row.lease_until is None for row in rows[expected:])


def test_claim_orders_by_created_at_then_id(outbox_db):
    clock = datetime(2026, 1, 15, 12)
    with outbox_db.begin() as session:
        session.add_all(
            PublicationEvent(id=id, project_id="project", payload={}, created_at=created_at)
            for id, created_at in [("b", clock), ("z", clock - timedelta(seconds=1)), ("a", clock)]
        )
    assert [event["id"] for event in claim_events(outbox_db)] == ["z", "a", "b"]


def test_claim_recovers_expired_and_boundary_leases(outbox_db, monkeypatch):
    clock = datetime(2026, 1, 15, 12)
    monkeypatch.setattr(outbox, "now", lambda: clock)
    with outbox_db.begin() as session:
        session.add_all(
            PublicationEvent(
                id=id,
                project_id="project",
                payload={"id": id},
                state="processing",
                claim=f"old-{id}",
                lease_until=clock + timedelta(microseconds=offset),
                created_at=clock,
            )
            for id, offset in [("expired", -1), ("boundary", 0), ("future", 1)]
        )
    claimed = claim_events(outbox_db)
    assert [event["id"] for event in claimed] == ["boundary", "expired"]
    for event in claimed:
        assert event["claim"] != f"old-{event['id']}"
        assert event["payload"] == {"id": event["id"]}
        assert not complete_event(outbox_db, event["id"], f"old-{event['id']}")
    with outbox_db() as session:
        for event in claimed:
            assert session.get(PublicationEvent, event["id"]).lease_until == clock + timedelta(minutes=2)
        future = session.get(PublicationEvent, "future")
        assert future.state == "processing" and future.claim == "old-future"
        assert future.lease_until == clock + timedelta(microseconds=1)
    assert claim_events(outbox_db) == []


def test_complete_requires_current_claim_and_processing_state(outbox_db):
    lease_until = datetime(2026, 1, 15, 12)
    with outbox_db.begin() as session:
        session.add_all(
            PublicationEvent(
                id=state, project_id="project", payload={}, state=state, claim="current", lease_until=lease_until
            )
            for state in ["pending", "processing", "processed"]
        )
    assert not complete_event(outbox_db, "unknown", "current")
    assert not complete_event(outbox_db, "processing", "stale")
    assert not complete_event(outbox_db, "pending", "current")
    assert not complete_event(outbox_db, "processed", "current")
    with outbox_db() as session:
        for row in session.scalars(select(PublicationEvent)):
            assert row.state == row.id and row.claim == "current" and row.lease_until == lease_until
    assert complete_event(outbox_db, "processing", "current")
    assert not complete_event(outbox_db, "processing", "current")
    with outbox_db() as session:
        row = session.get(PublicationEvent, "processing")
        assert row.state == "processed" and row.claim is None and row.lease_until is None


def test_prune_retains_cutoff_and_unprocessed_events(outbox_db, monkeypatch):
    clock = datetime(2026, 1, 15, 12)
    cutoff = clock - timedelta(days=30)
    monkeypatch.setattr(outbox, "now", lambda: clock)
    with outbox_db.begin() as session:
        session.add_all(
            PublicationEvent(id=id, project_id="project", payload={}, state=state, created_at=created_at)
            for id, state, created_at in [
                ("old-processed", "processed", cutoff - timedelta(microseconds=1)),
                ("boundary-processed", "processed", cutoff),
                ("recent-processed", "processed", cutoff + timedelta(microseconds=1)),
                ("old-pending", "pending", cutoff - timedelta(days=1)),
                ("old-processing", "processing", cutoff - timedelta(days=1)),
            ]
        )
    prune_events(outbox_db)
    with outbox_db() as session:
        assert set(session.scalars(select(PublicationEvent.id))) == {
            "boundary-processed",
            "recent-processed",
            "old-pending",
            "old-processing",
        }


def test_outbox_commits_only_public_changes_and_recovers_claims(app, client, admin):
    define(client, admin)
    draft = entry(client, admin, data={"title": "Draft", "secret": "Never event data"})["data"]["saveEntry"]
    with app.state.db() as session:
        assert session.scalars(select(PublicationEvent)).all() == []
    published = entry(client, admin, status="published", id=draft["id"], version=draft["version"])["data"]["saveEntry"]
    # Transaction rollback also removes its event (second field intentionally conflicts).
    result = gql(
        client,
        admin,
        "mutation($id:ID!,$version:Int!){unpublishEntry(id:$id,version:$version){id} cancelSchedule(id:$id,version:0){id}}",
        published,
    )
    assert "errors" in result
    with app.state.db() as session:
        events = session.scalars(select(PublicationEvent)).all()
        assert len(events) == 1
        assert "data" not in events[0].payload and "title" not in events[0].payload
    first = claim_events(app.state.db)
    assert len(first) == 1 and claim_events(app.state.db) == []
    with app.state.db.begin() as session:
        session.get(PublicationEvent, first[0]["id"]).lease_until = now() - timedelta(seconds=1)
    recovered = claim_events(app.state.db)[0]
    assert recovered["payload"]["id"] == first[0]["payload"]["id"]
    assert not complete_event(app.state.db, first[0]["id"], first[0]["claim"])
    assert complete_event(app.state.db, recovered["id"], recovered["claim"])
    assert claim_events(app.state.db) == []
