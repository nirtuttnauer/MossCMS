"""Local sessions, one-time invitations, membership administration and recovery."""

import hmac
import threading
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select, text

from .development import DEVELOPMENT_USER_ID
from .models import Membership, OAuthIdentity, Project, Token, User, now
from .security import (
    CmsError,
    audit,
    check_password,
    digest,
    identify,
    issue_token,
    password_hash,
    require,
    valid_email,
)

router = APIRouter()
_attempt_lock = threading.Lock()
_ATTEMPT_WINDOW_SECONDS = 60
_MAX_ATTEMPTS = 8
_ATTEMPT_KEY_CLEANUP_THRESHOLD = 10000


def rate_limit(key, request):
    attempts = request.app.state.login_attempts
    with _attempt_lock:
        current = time.monotonic()
        recent = [x for x in attempts.get(key, []) if current - x < _ATTEMPT_WINDOW_SECONDS]
        if len(recent) >= _MAX_ATTEMPTS:
            raise HTTPException(429, "Too many attempts. Try again in a minute.")
        attempts[key] = [*recent, current]
        if len(attempts) > _ATTEMPT_KEY_CLEANUP_THRESHOLD:
            expired = [k for k, v in attempts.items() if current - v[-1] > _ATTEMPT_WINDOW_SECONDS]
            for k in expired:
                attempts.pop(k, None)


def context(request, session):
    return {
        **identify(request, session, project=request.url.path not in {"/auth/me", "/auth/logout"}),
        "request": request,
        "session": session,
    }


def session_response(request, response, session, user):
    raw, csrf = issue_token(session, "session", user_id=user.id)
    response.set_cookie(
        "moss_session",
        raw,
        httponly=True,
        secure=request.app.state.settings.environment == "production",
        samesite="lax",
        max_age=7 * 86400,
        path="/",
    )
    return {"csrf": csrf, "user": {"id": user.id, "name": user.name, "email": user.email}}


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)


class Named(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be blank.")
        return value


class Setup(Login, Named):
    name: str = Field(min_length=1, max_length=100)
    token: str = Field(max_length=256)


class Invitation(BaseModel):
    email: str = Field(max_length=254)
    role: str = "editor"


class Accept(Setup):
    pass


class ChangeRole(BaseModel):
    role: str


class ProjectInput(Named):
    name: str = Field(min_length=1, max_length=100)


class DeliveryInput(Named):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[str] = Field(default_factory=list, max_length=40)
    days: int = Field(default=90, ge=1, le=365)


@router.get("/auth/status")
def status(request: Request):
    with request.app.state.db() as session:
        initialized = (
            request.app.state.settings.skip_auth
            or session.scalar(select(User.id).where(User.id != DEVELOPMENT_USER_ID).limit(1)) is not None
        )
    return {
        "initialized": initialized,
        "providers": request.app.state.oauth_providers,
        "authSkipped": request.app.state.settings.skip_auth,
    }


@router.post("/auth/setup")
def setup(body: Setup, request: Request, response: Response):
    rate_limit("setup:" + (request.client.host if request.client else "unknown"), request)
    if not hmac.compare_digest(body.token, request.app.state.settings.setup_token):
        raise HTTPException(403, "Invalid setup token.")
    with request.app.state.db.begin() as session:
        if session.bind.dialect.name == "postgresql":
            session.execute(text("SELECT pg_advisory_xact_lock(741582902)"))
        if session.scalar(select(User.id).where(User.id != DEVELOPMENT_USER_ID).limit(1)):
            raise HTTPException(409, "Setup is already complete.")
        user = User(email=valid_email(body.email), name=body.name.strip(), password_hash=password_hash(body.password))
        session.add(user)
        project = session.scalar(select(Project).order_by(Project.created_at).limit(1))
        if not project:
            project = Project(name="My workspace")
            session.add(project)
        session.flush()
        session.add(Membership(project_id=project.id, user_id=user.id, role="admin"))
        audit(session, project.id, user.email, "account.setup")
        return session_response(request, response, session, user)


@router.post("/auth/login")
def login(body: Login, request: Request, response: Response):
    rate_limit("login:" + (request.client.host if request.client else "unknown"), request)
    with request.app.state.db.begin() as session:
        user = session.scalar(select(User).where(User.email == valid_email(body.email)))
        if not user or not check_password(body.password, user.password_hash):
            # Perform the same expensive operation for unknown accounts.
            if not user:
                password_hash("dummy-password-that-is-never-accepted")
            raise HTTPException(401, "Invalid email or password.")
        audit(session, None, user.email, "account.login")
        return session_response(request, response, session, user)


@router.get("/auth/me")
def me(request: Request):
    with request.app.state.db() as session:
        c = context(request, session)
        projects = session.execute(
            select(Project, Membership.role)
            .join(Membership)
            .where(Membership.user_id == c["user"].id)
            .order_by(Project.name)
        ).all()
        if request.app.state.settings.skip_auth:
            projects = [(p, "admin") for p in session.scalars(select(Project).order_by(Project.name)).all()]
        identities = session.scalars(select(OAuthIdentity.provider).where(OAuthIdentity.user_id == c["user"].id)).all()
        return {
            "user": {"id": c["user"].id, "email": c["user"].email, "name": c["user"].name},
            "csrf": c["token"].csrf,
            "projects": [
                {
                    "id": p.id,
                    "name": p.name,
                    "role": role,
                    "previewOrigin": p.preview_origin,
                    "defaultLocale": p.default_locale,
                    "locales": p.locales,
                }
                for p, role in projects
            ],
            "providers": identities,
            "authSkipped": request.app.state.settings.skip_auth,
        }


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    if request.app.state.settings.skip_auth:
        response.delete_cookie("moss_session", path="/")
        return {"ok": True}
    with request.app.state.db.begin() as session:
        c = context(request, session)
        if not hmac.compare_digest(c["token"].csrf, request.headers.get("x-moss-csrf", "")):
            raise HTTPException(403, "Invalid CSRF token.")
        session.delete(c["token"])
    response.delete_cookie("moss_session", path="/")
    return {"ok": True}


@router.post("/auth/accept")
def accept(body: Accept, request: Request, response: Response):
    rate_limit("accept:" + (request.client.host if request.client else "unknown"), request)
    with request.app.state.db.begin() as session:
        token = session.scalar(select(Token).where(Token.id == digest(body.token)).with_for_update())
        if not token or token.kind not in {"invite", "reset"} or token.expires_at <= now():
            raise HTTPException(400, "This invitation or recovery link is invalid or expired.")
        email = valid_email(body.email)
        if email != token.email:
            raise HTTPException(400, "Use the invited account email.")
        user = session.scalar(select(User).where(User.email == email))
        if token.kind == "invite" and user:
            c = context(request, session)
            if c["user"].id != user.id or not hmac.compare_digest(
                c["token"].csrf, request.headers.get("x-moss-csrf", "")
            ):
                raise HTTPException(403, "Sign in to the invited account before accepting.")
        elif token.kind == "reset":
            if not user or user.id != token.user_id:
                raise HTTPException(400, "Invalid recovery link.")
            user.password_hash = password_hash(body.password)
            session.execute(delete(Token).where(Token.kind == "session", Token.user_id == user.id))
        else:
            user = User(email=email, name=body.name.strip(), password_hash=password_hash(body.password))
            session.add(user)
            session.flush()
        if token.kind == "invite":
            membership = session.get(Membership, (token.project_id, user.id))
            if membership:
                raise HTTPException(409, "This account already belongs to the project.")
            session.add(Membership(project_id=token.project_id, user_id=user.id, role=token.role))
        audit(session, token.project_id, user.email, "account." + token.kind + ".accept")
        session.delete(token)
        return session_response(request, response, session, user)


@router.get("/api/team")
def team(request: Request):
    with request.app.state.db() as session:
        c = context(request, session)
        require(c)
        rows = session.execute(
            select(User, Membership.role)
            .join(Membership)
            .where(Membership.project_id == c["project_id"])
            .order_by(User.name)
        ).all()
        pending = session.scalars(
            select(Token).where(Token.project_id == c["project_id"], Token.kind == "invite", Token.expires_at > now())
        ).all()
        return {
            "members": [{"id": user.id, "name": user.name, "email": user.email, "role": role} for user, role in rows],
            "invitations": [
                {"id": t.id, "email": t.email, "role": t.role, "expiresAt": t.expires_at.isoformat() + "Z"}
                for t in pending
            ],
        }


@router.post("/api/team/invitations")
def invite(body: Invitation, request: Request):
    with request.app.state.db.begin() as session:
        c = context(request, session)
        require(c, "admin", write=True)
        if body.role not in {"admin", "editor", "reader"}:
            raise CmsError("Choose admin, editor, or reader.")
        email = valid_email(body.email)
        user = session.scalar(select(User).where(User.email == email))
        if user and session.get(Membership, (c["project_id"], user.id)):
            raise CmsError("This user is already a member.")
        session.execute(
            delete(Token).where(Token.project_id == c["project_id"], Token.kind == "invite", Token.email == email)
        )
        raw, _ = issue_token(session, "invite", project_id=c["project_id"], email=email, role=body.role)
        audit(session, c["project_id"], c["actor"], "team.invite", email=email, role=body.role)
        return {"url": request.app.state.settings.public_url + "/#invite/" + raw}


def checked_membership(session, c, user_id):
    require(c, "admin", write=True)
    # Lock the project so simultaneous changes cannot remove both remaining administrators.
    session.scalar(select(Project).where(Project.id == c["project_id"]).with_for_update())
    member = session.get(Membership, (c["project_id"], user_id))
    if not member:
        raise CmsError("Member not found.", "NOT_FOUND")
    if (
        member.role == "admin"
        and session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.project_id == c["project_id"], Membership.role == "admin")
        )
        <= 1
    ):
        raise CmsError("Keep at least one project administrator.", "CONFLICT")
    return member


@router.patch("/api/team/{user_id}")
def change_role(user_id: str, body: ChangeRole, request: Request):
    with request.app.state.db.begin() as session:
        c = context(request, session)
        if body.role not in {"admin", "editor", "reader"}:
            raise CmsError("Choose admin, editor, or reader.")
        if body.role == "admin":
            require(c, "admin", write=True)
            member = session.get(Membership, (c["project_id"], user_id))
            if not member:
                raise CmsError("Member not found.", "NOT_FOUND")
        else:
            member = checked_membership(session, c, user_id)
        member.role = body.role
        audit(session, c["project_id"], c["actor"], "team.role", userId=user_id, role=body.role)
    return {"ok": True}


@router.delete("/api/team/invitations/{token_id}")
def revoke_invite(token_id: str, request: Request):
    with request.app.state.db.begin() as session:
        c = context(request, session)
        require(c, "admin", write=True)
        token = session.get(Token, token_id)
        if not token or token.project_id != c["project_id"] or token.kind != "invite":
            raise CmsError("Invitation not found.", "NOT_FOUND")
        session.delete(token)
        audit(session, c["project_id"], c["actor"], "team.invitation.revoke", invitationId=token_id)
    return {"ok": True}


@router.delete("/api/team/{user_id}")
def remove_member(user_id: str, request: Request):
    with request.app.state.db.begin() as session:
        c = context(request, session)
        member = checked_membership(session, c, user_id)
        session.delete(member)
        audit(session, c["project_id"], c["actor"], "team.remove", userId=user_id)
    return {"ok": True}


@router.post("/api/projects")
def create_project(body: ProjectInput, request: Request):
    with request.app.state.db.begin() as session:
        c = context(request, session)
        if not hmac.compare_digest(c["token"].csrf, request.headers.get("x-moss-csrf", "")):
            raise CmsError("Invalid CSRF token.", "FORBIDDEN")
        project = Project(name=body.name.strip())
        session.add(project)
        session.flush()
        if not request.app.state.settings.skip_auth:
            session.add(Membership(project_id=project.id, user_id=c["user"].id, role="admin"))
        audit(session, project.id, c["actor"], "project.create")
        return {"id": project.id, "name": project.name}


@router.patch("/api/project")
def rename_project(body: ProjectInput, request: Request):
    with request.app.state.db.begin() as session:
        c = context(request, session)
        require(c, "admin", write=True)
        project = session.get(Project, c["project_id"])
        project.name = body.name.strip()
        audit(session, project.id, c["actor"], "project.rename", name=project.name)
    return {"ok": True}


@router.get("/api/tokens")
def delivery_tokens(request: Request):
    with request.app.state.db() as session:
        c = context(request, session)
        require(c, "admin")
        rows = session.scalars(select(Token).where(Token.project_id == c["project_id"], Token.kind == "delivery")).all()
        return [
            {"id": t.id, "name": t.name, "scopes": t.scopes, "expiresAt": t.expires_at.isoformat() + "Z"} for t in rows
        ]


@router.post("/api/tokens")
def create_delivery_token(body: DeliveryInput, request: Request):
    from .content import get_type

    with request.app.state.db.begin() as session:
        c = context(request, session)
        require(c, "admin", write=True)
        for key in body.scopes:
            get_type(session, c, key)
        raw, _ = issue_token(
            session, "delivery", days=body.days, project_id=c["project_id"], name=body.name, scopes=body.scopes
        )
        audit(session, c["project_id"], c["actor"], "token.create", name=body.name, scopes=body.scopes)
        return {"token": raw}


@router.delete("/api/tokens/{token_id}")
def revoke_token(token_id: str, request: Request):
    with request.app.state.db.begin() as session:
        c = context(request, session)
        require(c, "admin", write=True)
        token = session.get(Token, token_id)
        if not token or token.kind != "delivery" or token.project_id != c["project_id"]:
            raise CmsError("Token not found.", "NOT_FOUND")
        session.delete(token)
        audit(session, c["project_id"], c["actor"], "token.revoke", tokenId=token_id)
    return {"ok": True}


class PreviewOriginInput(BaseModel):
    origin: str = Field(max_length=2048)


@router.patch("/api/project/preview")
def configure_preview(body: PreviewOriginInput, request: Request):
    from urllib.parse import urlsplit

    origin = body.origin.strip().rstrip("/")
    if origin:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
            or (request.app.state.settings.environment == "production" and parsed.scheme != "https")
        ):
            raise CmsError("Enter a website origin such as https://example.com (no path).", "VALIDATION")
    with request.app.state.db.begin() as session:
        c = context(request, session)
        require(c, "admin", write=True)
        project = session.get(Project, c["project_id"])
        project.preview_origin = origin or None
        audit(session, project.id, c["actor"], "project.preview", origin=origin)
    return {"ok": True}


class LocaleInput(BaseModel):
    defaultLocale: str = Field(max_length=20)
    locales: list[str] = Field(min_length=1, max_length=40)


@router.patch("/api/project/locales")
@router.patch("/api/projects/{project_id}")
def configure_locales(body: LocaleInput, request: Request, project_id: str | None = None):
    from .schema import LOCALE

    with request.app.state.db.begin() as session:
        c = context(request, session)
        require(c, "admin", write=True)
        if project_id is not None and project_id != c["project_id"]:
            raise CmsError("Select the workspace whose locales you are changing.", "FORBIDDEN")
        if (
            not LOCALE.fullmatch(body.defaultLocale)
            or any(not LOCALE.fullmatch(locale) for locale in body.locales)
            or len({locale.lower() for locale in body.locales}) != len(body.locales)
            or body.defaultLocale not in body.locales
        ):
            raise CmsError("Choose valid, unique locale codes and include the default locale in the suggestions.")
        project = session.get(Project, c["project_id"])
        project.default_locale, project.locales = body.defaultLocale, body.locales
        audit(
            session, project.id, c["actor"], "project.locales", defaultLocale=body.defaultLocale, locales=body.locales
        )
        return {"id": project.id, "defaultLocale": project.default_locale, "locales": project.locales}
