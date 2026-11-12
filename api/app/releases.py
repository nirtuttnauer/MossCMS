"""Coordinated releases capture approved revisions and commit every action or none."""

from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from .models import ContentType, Entry, PublicationEvent, Release, ReleaseItem, now, uid
from .permissions import ensure_access
from .security import CmsError, audit

MAX_RELEASE_ITEMS = 30
OPEN = ("draft", "scheduled")


def release_dict(session, release):
    items = session.scalars(
        select(ReleaseItem).where(ReleaseItem.release_id == release.id).order_by(ReleaseItem.slug)
    ).all()
    return {
        "id": release.id,
        "name": release.name,
        "status": release.status,
        "scheduledAt": release.scheduled_at.isoformat() + "Z" if release.scheduled_at else None,
        "error": release.error,
        "version": release.version,
        "items": [
            {
                "id": item.id,
                "entryId": item.entry_id,
                "action": item.action,
                "revision": item.revision,
                "slug": item.slug,
                "title": item.title,
                "schemaVersion": item.schema_version,
            }
            for item in items
        ],
    }


def entry_in_open_release(session, project_id, entry_id):
    if not entry_id:
        return False
    return (
        session.scalar(
            select(ReleaseItem.id)
            .join(Release, Release.id == ReleaseItem.release_id)
            .where(
                Release.project_id == project_id,
                Release.status.in_(OPEN),
                ReleaseItem.entry_id == entry_id,
            )
        )
        is not None
    )


def _locked(session, identity, release_id, version):
    ensure_access(identity)
    release = session.get(Release, release_id)
    if not release or release.project_id != identity["project_id"]:
        raise CmsError("Release not found.", "NOT_FOUND")
    if version != release.version:
        raise CmsError("This release changed. Reload it.", "CONFLICT")
    return release


def create_release(session, identity, name):
    ensure_access(identity)
    name = name.strip()
    if not name or len(name) > 100:
        raise CmsError("Use a release name of 1–100 characters.")
    release = Release(project_id=identity["project_id"], name=name, created_by=identity["user"].id, status="draft")
    session.add(release)
    session.flush()
    audit(session, identity["project_id"], identity["actor"], "release.create", releaseId=release.id)
    session.flush()
    return release


def add_release_entry(session, identity, release_id, entry_id, action, version):
    from .content import get_entry

    release = _locked(session, identity, release_id, version)
    if release.status not in OPEN:
        raise CmsError("This release can no longer be changed.")
    if action not in {"publish", "unpublish"}:
        raise CmsError("Choose publish or unpublish.")
    items = session.scalars(select(ReleaseItem).where(ReleaseItem.release_id == release.id)).all()
    if len(items) >= MAX_RELEASE_ITEMS:
        raise CmsError(f"A release can contain at most {MAX_RELEASE_ITEMS} entries.")
    if any(item.entry_id == entry_id for item in items):
        raise CmsError("This entry is already in the release.")
    record = get_entry(session, identity, entry_id)
    if record.status == "deleted":
        raise CmsError("Restore the entry before adding it to a release.")
    if record.scheduled_at or record.schedule_error:
        raise CmsError("Cancel this entry's individual schedule before adding it to a release.")
    if entry_in_open_release(session, identity["project_id"], entry_id):
        raise CmsError("This entry already belongs to an open release.")
    definition = session.get(ContentType, record.type_id)
    if action == "publish":
        from .reviews import approval_matches

        if not approval_matches(session, record, definition, record.data, record.slug):
            raise CmsError("Approve the current revision before adding it to a release.")
    elif not record.published_slug:
        raise CmsError("Only a live entry can be unpublished by a release.")
    session.add(
        ReleaseItem(
            release_id=release.id,
            project_id=release.project_id,
            entry_id=record.id,
            action=action,
            revision=record.version,
            slug=record.slug,
            title=record.title[:200],
            data=deepcopy(record.data if action == "publish" else record.published_data or {}),
            schema_version=definition.version,
        )
    )
    release.updated_at = now()
    audit(
        session,
        identity["project_id"],
        identity["actor"],
        "release.add",
        releaseId=release.id,
        entryId=entry_id,
        itemAction=action,
    )
    session.flush()
    return release


def remove_release_entry(session, identity, release_id, entry_id, version):
    release = _locked(session, identity, release_id, version)
    if release.status not in OPEN:
        raise CmsError("This release can no longer be changed.")
    item = session.scalar(
        select(ReleaseItem).where(ReleaseItem.release_id == release.id, ReleaseItem.entry_id == entry_id)
    )
    if not item:
        raise CmsError("That entry is not in this release.", "NOT_FOUND")
    session.delete(item)
    release.updated_at = now()
    audit(session, identity["project_id"], identity["actor"], "release.remove", releaseId=release.id, entryId=entry_id)
    session.flush()
    return release


def _apply_item(session, item):
    from .content import publish_snapshot, summarize_status
    from .outbox import emit
    from .reviews import assert_captured_publication
    from .schema import validate_data

    record = session.get(Entry, item.entry_id, with_for_update=True)
    definition = session.get(ContentType, record.type_id) if record else None
    if not record or record.project_id != item.project_id or record.status == "deleted" or not definition:
        raise CmsError("A release entry is missing. Nothing was published.")
    if definition.version != item.schema_version:
        raise CmsError("A schema change invalidated this release. Nothing was published.")
    if item.action == "publish":
        validate_data(definition.fields, item.data, session, record.project_id)
        assert_captured_publication(session, record, definition, item.data, item.slug, check_actor=False)
        collision = session.scalar(
            select(Entry.id).where(
                Entry.project_id == record.project_id,
                Entry.type_id == record.type_id,
                Entry.published_slug == item.slug,
                Entry.id != record.id,
                Entry.status != "deleted",
            )
        )
        if collision:
            raise CmsError("A release URL conflicts with live content. Nothing was published.", "CONFLICT")
        from .content import reserve_website_paths

        previous = record.published_slug
        reserve_website_paths(session, record, definition, item.slug, item.data)
        publish_snapshot(record, definition, item.data, item.slug, item.title, item.revision)
        record.updated_at = now()
        summarize_status(record)
        emit(session, record, "published", item.revision, record.published_slug, previous)
        return
    if not record.published_slug:
        raise CmsError("A release tried to unpublish an entry that is not live. Nothing was published.")
    emit(session, record, "unpublished", record.published_revision, record.published_slug)
    record.published_data = record.published_slug = record.published_title = record.published_at = None
    record.published_revision = record.published_schema_version = None
    record.updated_at = now()
    summarize_status(record)


def run_release(session, release):
    from .content import revision

    if release.status == "published":
        return release
    items = session.scalars(select(ReleaseItem).where(ReleaseItem.release_id == release.id)).all()
    if not items:
        release.status = "failed"
        release.scheduled_at = None
        release.error = {
            "code": "VALIDATION",
            "message": "Add at least one entry before publishing a release.",
            "failedAt": now().isoformat() + "Z",
        }
        release.updated_at = now()
        session.flush()
        return release
    try:
        with session.begin_nested():
            for item in items:
                _apply_item(session, item)
            for item in items:
                record = session.get(Entry, item.entry_id)
                revision(session, {"actor": "release"}, record)
            event_id = uid()
            session.add(
                PublicationEvent(
                    id=event_id,
                    project_id=release.project_id,
                    payload={
                        "id": event_id,
                        "event": "release.published",
                        "workspaceId": release.project_id,
                        "releaseId": release.id,
                        "entryIds": [item.entry_id for item in items],
                        "occurredAt": now().isoformat() + "Z",
                    },
                )
            )
            release.status = "published"
            release.scheduled_at = None
            release.error = None
            release.updated_at = now()
    except (CmsError, IntegrityError, StaleDataError) as exc:
        release.status = "failed"
        release.scheduled_at = None
        release.error = {
            "code": exc.code if isinstance(exc, CmsError) else "CONFLICT",
            "message": str(exc)
            if isinstance(exc, CmsError)
            else "The release conflicted with live content. Nothing was published.",
            "failedAt": now().isoformat() + "Z",
        }
        release.updated_at = now()
    audit(session, release.project_id, "release", "release." + release.status, releaseId=release.id)
    session.flush()
    return release


def publish_release(session, identity, release_id, version):
    release = _locked(session, identity, release_id, version)
    if release.status not in OPEN:
        raise CmsError("This release is already finished.")
    return run_release(session, release)


def schedule_release(session, identity, release_id, version, scheduled_at):
    from datetime import datetime, timezone

    release = _locked(session, identity, release_id, version)
    if release.status not in OPEN:
        raise CmsError("This release is already finished.")
    if not session.scalar(select(ReleaseItem.id).where(ReleaseItem.release_id == release.id)):
        raise CmsError("Add at least one entry before scheduling a release.")
    try:
        when = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
        if when.tzinfo:
            when = when.astimezone(timezone.utc).replace(tzinfo=None)
        if when <= now():
            raise ValueError()
    except (AttributeError, ValueError):
        raise CmsError("Choose a future release time.") from None
    release.status = "scheduled"
    release.scheduled_at = when
    release.error = None
    release.updated_at = now()
    audit(session, identity["project_id"], identity["actor"], "release.schedule", releaseId=release.id)
    session.flush()
    return release


def cancel_release(session, identity, release_id, version):
    release = _locked(session, identity, release_id, version)
    if release.status == "published":
        raise CmsError("A published release cannot be cancelled.")
    release.status = "cancelled"
    release.scheduled_at = None
    release.updated_at = now()
    audit(session, identity["project_id"], identity["actor"], "release.cancel", releaseId=release.id)
    session.flush()
    return release


def publish_due_releases(session):
    due = session.scalars(
        select(Release)
        .where(Release.status == "scheduled", Release.scheduled_at <= now())
        .with_for_update(skip_locked=True)
    ).all()
    for release in due:
        run_release(session, release)
