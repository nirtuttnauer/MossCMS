"""Transactional publication metadata and recoverable, bounded worker claims."""

from datetime import timedelta
from sqlalchemy import delete, or_, select, update
from .models import ContentType, PublicationEvent, now, uid

DEFAULT_CLAIM_LIMIT = 50
MAX_CLAIM_LIMIT = 100
CLAIM_LEASE_DURATION = timedelta(minutes=2)
PROCESSED_EVENT_RETENTION = timedelta(days=30)


def emit(session, record, kind, revision, slug, previous_slug=None):
    id = uid()
    session.add(
        PublicationEvent(
            id=id,
            project_id=record.project_id,
            payload={
                "id": id,
                "event": kind,
                "workspaceId": record.project_id,
                "typeKey": session.get(ContentType, record.type_id).key,
                "entryId": record.id,
                "publicationRevision": revision,
                "slug": slug,
                "previousSlug": previous_slug,
                "occurredAt": now().isoformat() + "Z",
            },
        )
    )


def claim_events(factory, limit=DEFAULT_CLAIM_LIMIT):
    claimed = []
    with factory.begin() as session:
        rows = session.scalars(
            select(PublicationEvent)
            .where(
                or_(
                    PublicationEvent.state == "pending",
                    (PublicationEvent.state == "processing") & (PublicationEvent.lease_until <= now()),
                )
            )
            .order_by(PublicationEvent.created_at, PublicationEvent.id)
            .limit(min(MAX_CLAIM_LIMIT, max(1, limit)))
            .with_for_update(skip_locked=True)
        ).all()
        for row in rows:
            row.state = "processing"
            row.claim = uid()
            row.lease_until = now() + CLAIM_LEASE_DURATION
            claimed.append({"id": row.id, "project_id": row.project_id, "claim": row.claim, "payload": row.payload})
    return claimed


def complete_event(factory, id, claim):
    with factory.begin() as session:
        result = session.execute(
            update(PublicationEvent)
            .where(PublicationEvent.id == id, PublicationEvent.claim == claim, PublicationEvent.state == "processing")
            .values(state="processed", claim=None, lease_until=None)
        )
        return result.rowcount == 1


def prune_events(factory):
    with factory.begin() as session:
        session.execute(
            delete(PublicationEvent).where(
                PublicationEvent.state == "processed", PublicationEvent.created_at < now() - PROCESSED_EVENT_RETENTION
            )
        )
