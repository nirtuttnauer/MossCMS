"""OAuth authorization-code login, OIDC verification, and explicit account linking."""

import os
from urllib.parse import quote

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from .accounts import context, session_response
from .models import Membership, OAuthIdentity, Token, User, now
from .security import CmsError, audit, digest, require, valid_email

router = APIRouter()


def configure_oauth(app):
    oauth = OAuth()
    providers: list[dict[str, str]] = []
    if app.state.settings.skip_auth:
        app.state.oauth, app.state.oauth_providers = oauth, providers
        return
    if os.getenv("MOSS_OIDC_CLIENT_ID"):
        if not os.getenv("MOSS_OIDC_CLIENT_SECRET") or not os.getenv("MOSS_OIDC_DISCOVERY_URL"):
            raise RuntimeError("OIDC requires a client ID, client secret, and discovery URL.")
        if app.state.settings.environment == "production" and not os.environ["MOSS_OIDC_DISCOVERY_URL"].startswith(
            "https://"
        ):
            raise RuntimeError("Production OIDC discovery requires HTTPS.")
        oauth.register(
            "oidc",
            client_id=os.environ["MOSS_OIDC_CLIENT_ID"],
            client_secret=os.environ["MOSS_OIDC_CLIENT_SECRET"],
            server_metadata_url=os.environ["MOSS_OIDC_DISCOVERY_URL"],
            client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
        )
        providers.append({"id": "oidc", "name": os.getenv("MOSS_OIDC_NAME", "Single sign-on")})
    if os.getenv("MOSS_GITHUB_CLIENT_ID"):
        if not os.getenv("MOSS_GITHUB_CLIENT_SECRET"):
            raise RuntimeError("GitHub OAuth requires a client secret.")
        oauth.register(
            "github",
            client_id=os.environ["MOSS_GITHUB_CLIENT_ID"],
            client_secret=os.environ["MOSS_GITHUB_CLIENT_SECRET"],
            access_token_url="https://github.com/login/oauth/access_token",
            authorize_url="https://github.com/login/oauth/authorize",
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "read:user user:email"},
        )
        providers.append({"id": "github", "name": "GitHub"})
    app.state.oauth = oauth
    app.state.oauth_providers = providers


def client_for(request, provider):
    if provider not in {p["id"] for p in request.app.state.oauth_providers}:
        raise HTTPException(404, "Sign-in provider is not configured.")
    return request.app.state.oauth.create_client(provider)


@router.get("/auth/oauth/{provider}/start")
async def start(provider: str, request: Request, invite: str = ""):
    client = client_for(request, provider)
    request.session["oauth_link_user"] = None
    request.session["oauth_invite"] = invite[:200]
    callback = request.app.state.settings.public_url + f"/auth/oauth/{provider}/callback"
    return await client.authorize_redirect(request, callback)


@router.post("/auth/oauth/{provider}/link")
async def link(provider: str, request: Request):
    client = client_for(request, provider)
    with request.app.state.db() as session:
        c = context(request, session)
        require(c, write=True)
        request.session["oauth_link_user"] = c["user"].id
    request.session["oauth_invite"] = ""
    callback = request.app.state.settings.public_url + f"/auth/oauth/{provider}/callback"
    response = await client.authorize_redirect(request, callback)
    return {"url": response.headers["location"]}


@router.get("/auth/oauth/{provider}/callback")
async def callback(provider: str, request: Request):
    try:
        client = client_for(request, provider)
        # Authlib validates OAuth state; OIDC additionally validates ID-token signature, issuer, audience and nonce.
        token = await client.authorize_access_token(request)
        if provider == "github":
            profile = (await client.get("user", token=token)).json()
            emails = (await client.get("user/emails", token=token)).json()
            verified = [e for e in emails if e.get("verified")]
            verified.sort(key=lambda e: not e.get("primary"))
            if not verified:
                raise CmsError("A verified email address is required.")
            email, subject = valid_email(verified[0]["email"]), str(profile["id"])
            name = profile.get("name") or profile.get("login") or email
        else:
            profile = token.get("userinfo")
            if not profile or profile.get("email_verified") is not True:
                raise CmsError("Your sign-in provider must return a verified email address.")
            email, subject = valid_email(profile["email"]), str(profile["sub"])
            name = profile.get("name") or email
        link_user = request.session.pop("oauth_link_user", None)
        invite_raw = request.session.pop("oauth_invite", "")
        response = RedirectResponse("/#content", status_code=303)
        with request.app.state.db.begin() as session:
            identity = session.scalar(
                select(OAuthIdentity).where(OAuthIdentity.provider == provider, OAuthIdentity.subject == subject)
            )
            invitation = (
                session.scalar(select(Token).where(Token.id == digest(invite_raw)).with_for_update())
                if invite_raw
                else None
            )
            if invitation and (
                invitation.kind != "invite" or invitation.expires_at <= now() or invitation.email != email
            ):
                raise CmsError("Invitation is expired or belongs to another email.")
            if link_user:
                c = context(request, session)
                if c["user"].id != link_user:
                    raise CmsError("Sign in again before linking a provider.")
                if identity and identity.user_id != link_user:
                    raise CmsError("This provider account is already linked to another user.")
                user = c["user"]
            elif identity:
                user = session.get(User, identity.user_id)
            else:
                if session.scalar(select(User.id).where(User.email == email)):
                    raise CmsError("Sign in with your existing account, then connect this provider in Settings.")
                if not invitation:
                    raise CmsError("Ask a workspace administrator for an invitation before signing in.")
                user = User(email=email, name=str(name)[:100], password_hash="oauth-only")
                session.add(user)
                session.flush()
            if not identity:
                session.add(OAuthIdentity(user_id=user.id, provider=provider, subject=subject))
            if invitation:
                if not session.get(Membership, (invitation.project_id, user.id)):
                    session.add(Membership(project_id=invitation.project_id, user_id=user.id, role=invitation.role))
                session.delete(invitation)
            audit(session, None, user.email, "account.oauth", provider=provider, linked=bool(link_user))
            session_response(request, response, session, user)
        return response
    except Exception as exc:
        message = str(exc) if isinstance(exc, (CmsError, HTTPException)) else "Provider sign-in failed. Try again."
        return RedirectResponse("/#login?error=" + quote(message), status_code=303)
