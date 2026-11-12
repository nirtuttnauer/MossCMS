"""Revision-bound review. Existing types publish as before until review is enabled."""

from sqlalchemy import select

from .models import Membership, Project, Revision
from .permissions import capabilities_for, ensure_access
from .security import CmsError


def review_enabled(session, project_id, type_key):
    project = session.get(Project, project_id)
    return bool(project and (project.review_types or {}).get(type_key))


def bound_revision(session, record):
    number = record.approved_revision or record.submitted_revision
    if not number:
        return None
    return session.scalar(select(Revision).where(Revision.entry_id == record.id, Revision.number == number))


def clear_review(record):
    record.review_state = "draft"
    record.approved_revision = None
    record.approved_slug = None
    record.approved_schema_version = None
    record.submitted_revision = None
    record.reviewer_id = None
    record.review_author_id = None


def invalidate_review(session, record, definition):
    if record.review_state == "draft" and not record.approved_revision and not record.submitted_revision:
        return
    revision = bound_revision(session, record)
    schema_ok = not record.approved_revision or record.approved_schema_version == definition.version
    same = (
        revision
        and revision.snapshot.get("data") == record.data
        and revision.snapshot.get("slug") == record.slug
        and schema_ok
    )
    if not same:
        clear_review(record)


def approval_matches(session, record, definition, data, slug):
    if not review_enabled(session, record.project_id, definition.key):
        return True
    if (
        not record.approved_revision
        or record.approved_schema_version != definition.version
        or slug != record.approved_slug
    ):
        return False
    revision = session.scalar(
        select(Revision).where(Revision.entry_id == record.id, Revision.number == record.approved_revision)
    )
    return bool(revision and revision.snapshot.get("data") == data and revision.snapshot.get("slug") == slug)


def require_approval(session, record, definition, data, slug):
    if approval_matches(session, record, definition, data, slug):
        return
    raise CmsError("Submit this revision for approval before publishing. The approved revision is unchanged.")


def reviewer_still_eligible(session, record):
    if not record.reviewer_id:
        return False
    project = session.get(Project, record.project_id)
    membership = session.get(Membership, (record.project_id, record.reviewer_id))
    if not membership or not project:
        return False
    if record.reviewer_id == record.review_author_id:
        return False
    return "review" in capabilities_for(membership.role, project.custom_permissions)


def schedule_actor_allowed(session, record):
    if not record.schedule_actor_id:
        return True
    project = session.get(Project, record.project_id)
    membership = session.get(Membership, (record.project_id, record.schedule_actor_id))
    if not membership or not project:
        return False
    return "schedule" in capabilities_for(membership.role, project.custom_permissions)


def assert_captured_publication(session, record, definition, data, slug, check_actor=True):
    if review_enabled(session, record.project_id, definition.key):
        if not approval_matches(session, record, definition, data, slug) or not reviewer_still_eligible(
            session, record
        ):
            raise CmsError("This captured revision is no longer approved. Live content was preserved.")
    if check_actor and not schedule_actor_allowed(session, record):
        raise CmsError("The person who scheduled this entry can no longer publish it. Live content was preserved.")


def submit_for_review(session, identity, record, definition, reviewer_id):
    ensure_access(identity)
    if not review_enabled(session, record.project_id, definition.key):
        raise CmsError("This content type does not require review.")
    if reviewer_id == identity["user"].id:
        raise CmsError("Choose a different reviewer.")
    project = session.get(Project, record.project_id)
    membership = session.get(Membership, (record.project_id, reviewer_id))
    if not membership or "review" not in capabilities_for(membership.role, project.custom_permissions):
        raise CmsError("Choose a reviewer who can approve content.")
    record.review_state = "in_review"
    record.submitted_revision = record.version
    record.reviewer_id = reviewer_id
    record.review_author_id = identity["user"].id
    record.approved_revision = None
    record.approved_slug = None
    record.approved_schema_version = None
    session.flush()


def decide_review(session, identity, record, definition, approve):
    ensure_access(identity)
    if not review_enabled(session, record.project_id, definition.key):
        raise CmsError("This content type does not require review.")
    submitted = session.scalar(
        select(Revision).where(Revision.entry_id == record.id, Revision.number == record.submitted_revision)
    )
    if (
        record.review_state != "in_review"
        or not submitted
        or submitted.snapshot.get("data") != record.data
        or submitted.snapshot.get("slug") != record.slug
    ):
        raise CmsError("Submit the current revision before reviewing it.")
    if identity["user"].id == record.review_author_id:
        raise CmsError("The author cannot approve their own revision.")
    if record.reviewer_id != identity["user"].id:
        raise CmsError("This review is assigned to someone else.")
    if approve:
        record.review_state = "approved"
        record.approved_revision = record.submitted_revision
        record.approved_slug = record.slug
        record.approved_schema_version = definition.version
    else:
        record.review_state = "returned"
        record.approved_revision = None
        record.approved_slug = None
        record.approved_schema_version = None
    session.flush()
