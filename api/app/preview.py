"""Editor-issued capabilities, redeemed only alongside a matching delivery token."""

import secrets
from datetime import timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import content
from .graphql import asset_node
from .models import Asset, Membership, PreviewGrant, Project, Revision, now
from .security import CmsError, audit, digest, identify, require

router = APIRouter()


def create_grant(session, identity, id, version):
    require(identity, "editor", write=True)
    record = content.get_entry(session, identity, id)
    if record.status == "deleted" or record.version != version:
        raise CmsError("Save/reload the working revision before previewing.", "CONFLICT")
    raw = secrets.token_urlsafe(32)
    grant = PreviewGrant(
        id=digest(raw),
        project_id=record.project_id,
        entry_id=id,
        user_id=identity["user"].id,
        revision=version,
        type_key=session.get(content.ContentType, record.type_id).key,
        expires_at=now() + timedelta(minutes=15),
    )
    session.add(grant)
    audit(session, record.project_id, identity["actor"], "preview.issue", entryId=id, revision=version)
    origin = session.get(Project, record.project_id).preview_origin
    url = (
        f"{origin}/preview#grant={raw}"
        if origin and grant.type_key in {"sitePage", "sitePost", "siteProject", "siteSlide", "siteProfile"}
        else None
    )
    return {
        "previewUrl": url,
        "id": grant.id,
        "token": raw,
        "expiresAt": grant.expires_at.isoformat() + "Z",
        "revision": version,
    }


def revoke_grant(session, identity, id):
    require(identity, "editor", write=True)
    grant = session.get(PreviewGrant, id)
    if not grant or grant.project_id != identity["project_id"]:
        raise CmsError("Preview grant not found.", "NOT_FOUND")
    if grant.user_id != identity["user"].id and identity["role"] != "admin":
        raise CmsError("Only the issuing editor or an administrator can revoke this preview.", "FORBIDDEN")
    grant.revoked_at = now()
    audit(session, grant.project_id, identity["actor"], "preview.revoke", entryId=grant.entry_id)
    return True


class Redemption(BaseModel):
    token: str = Field(min_length=20, max_length=100)


@router.post("/api/preview/redeem")
def redeem(body: Redemption, request: Request):
    with request.app.state.db() as session:
        identity = identify(request, session, delivery=True)
        require(identity)
        grant = session.get(PreviewGrant, digest(body.token))
        if not grant or grant.revoked_at or grant.expires_at <= now() or grant.project_id != identity["project_id"]:
            raise CmsError("Preview grant expired, revoked or out of scope.", "FORBIDDEN")
        membership = session.get(Membership, (grant.project_id, grant.user_id))
        if not membership or membership.role not in {"admin", "editor"}:
            raise CmsError("Preview issuer no longer has editing access.", "FORBIDDEN")
        definition = content.get_type(session, identity, grant.type_key)
        # A preview never inherits the draft visibility of ordinary editorial context.
        record = session.get(content.Entry, grant.entry_id)
        if not record or record.status == "deleted" or record.type_id != definition.id:
            raise CmsError("Preview entry is no longer available.", "NOT_FOUND")
        saved = session.scalar(
            select(Revision).where(Revision.entry_id == grant.entry_id, Revision.number == grant.revision)
        )
        if not saved:
            raise CmsError("Preview revision is unavailable.", "NOT_FOUND")
        data = saved.snapshot["data"]
        content.validate_data(definition.fields, data, session, grant.project_id)
        data = content.public_data(definition.fields, data)
        ids = content.image_asset_ids(definition.fields, data)
        assets = session.scalars(content.scoped(session, Asset, identity).where(Asset.id.in_(ids))).all()
        settings = request.app.state.settings
        payload = {
            "entry": {
                "id": grant.entry_id,
                "typeKey": grant.type_key,
                "slug": saved.snapshot["slug"],
                "data": data,
                "resolvedAssets": [asset_node(a, settings).__dict__ for a in assets if a.mime.startswith("image/")],
            },
            "revision": grant.revision,
            "expiresAt": grant.expires_at.isoformat() + "Z",
        }
    return JSONResponse(
        payload,
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer"},
    )
