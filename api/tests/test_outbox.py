from datetime import timedelta
from sqlalchemy import select
from app.models import PublicationEvent, now
from app.outbox import claim_events, complete_event
from conftest import define, entry, gql


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
