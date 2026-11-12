"""Drafts-only tokens.

A drafts token reads the current draft of one entry in its own project.
It is not a session and not a delivery token. An expired token, a missing
entry, and an entry in another project are rejected. The token cannot
authorize a write. Reads apply the project's field rules for the reader role.
"""

from copy import deepcopy

from .content import get_entry
from .models import ContentType, Project, Token
from .permissions import field_visible, redact, rule_paths
from .security import DRAFTS_TOKEN_KIND, CmsError, audit, identify, issue_token, require


def issue_draft_token(session, identity, name="Drafts", days=1):
    require(identity, "admin", write=True)
    label = name.strip() if isinstance(name, str) else ""
    if not label or len(label) > 100:
        raise CmsError("Use a drafts token name of 1–100 characters.")
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 365:
        raise CmsError("Choose a drafts token lifetime of 1–365 days.")
    project = session.get(Project, identity["project_id"])
    if project is None:
        raise CmsError("Workspace not found.", "NOT_FOUND")
    raw, _csrf = issue_token(
        session,
        DRAFTS_TOKEN_KIND,
        days=days,
        project_id=project.id,
        name=label,
        role="reader",
        scopes=[],
    )
    audit(session, project.id, identity["actor"], "draft_token.issue", name=label, days=days)
    return raw


def revoke_draft_token(session, identity, token_id):
    require(identity, "admin", write=True)
    token = session.get(Token, token_id)
    if token is None or token.kind != DRAFTS_TOKEN_KIND or token.project_id != identity["project_id"]:
        raise CmsError("Token not found.", "NOT_FOUND")
    session.delete(token)
    audit(session, identity["project_id"], identity["actor"], "draft_token.revoke", tokenId=token_id)
    return True


def read_draft_snapshot(request, session, entry_id):
    identity = {**identify(request, session, drafts=True), "request": request, "session": session}
    require(identity)
    record = get_entry(session, identity, entry_id)
    if record.status == "deleted":
        raise CmsError("Entry not found.", "NOT_FOUND")
    definition = session.get(ContentType, record.type_id)
    if definition is None:
        raise CmsError("Entry not found.", "NOT_FOUND")
    allowed = rule_paths(identity, definition.key, "read")
    data = deepcopy(record.data) if isinstance(record.data, dict) else {}
    data = redact(data, definition.fields, "", allowed)
    title = record.title if field_visible(identity, definition, "title") else record.slug
    return {
        "id": record.id,
        "typeKey": definition.key,
        "slug": record.slug,
        "title": title,
        "data": data,
        "status": record.status,
        "version": record.version,
    }
