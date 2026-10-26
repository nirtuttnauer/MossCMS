import hashlib
import hmac
import secrets
import re
from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import select

from fastapi import HTTPException

from .development import DEVELOPMENT_USER_ID
from .models import Audit, Membership, Project, Token, User, now


class CmsError(Exception):
    def __init__(self, message, code="VALIDATION", field_path=None, reason=None):
        super().__init__(message)
        self.code = code
        self.field_path = field_path
        self.reason = reason or ("invalid_value" if field_path else None)

    def extensions(self):
        result = {"code": self.code}
        if self.field_path:
            result["fieldPath"] = [
                int(index) if index else name for name, index in re.findall(r"([^.[\]]+)|\[(\d+)\]", self.field_path)
            ]
            result["reason"] = self.reason
        return result


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise CmsError("Use a password of 12–128 characters.")
    salt = secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return f"scrypt${salt}${value}"


def check_password(password, stored):
    try:
        _, salt, expected = stored.split("$")
        value = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(value, expected)
    except (ValueError, AttributeError):
        return False


def issue_token(session, kind, days=7, **values):
    raw = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32) if kind == "session" else ""
    token = Token(id=digest(raw), kind=kind, csrf=csrf, expires_at=now() + timedelta(days=days), **values)
    session.add(token)
    return raw, csrf


def audit(session, project_id, actor, action, **details):
    session.add(Audit(project_id=project_id, actor=actor, action=action, details=details))


def identify(request, session, delivery=False, project=True):
    if request.app.state.settings.skip_auth and not delivery:
        user = session.get(User, DEVELOPMENT_USER_ID)
        project_id = request.headers.get("x-moss-project") if project else None
        if project and not project_id:
            project_id = session.scalar(select(Project.id).order_by(Project.created_at, Project.id).limit(1))
        if project_id and not session.get(Project, project_id):
            raise HTTPException(404, "Workspace not found.")
        return {
            "user": user,
            "token": SimpleNamespace(csrf=request.app.state.development_csrf),
            "project_id": project_id,
            "role": "admin",
            "delivery": False,
            "actor": user.email,
        }
    authorization = request.headers.get("authorization", "")
    raw = authorization[7:] if authorization.startswith("Bearer ") else request.cookies.get("moss_session", "")
    token = session.get(Token, digest(raw)) if raw else None
    if not token or token.expires_at <= now() or token.kind != ("delivery" if delivery else "session"):
        raise HTTPException(401, "Sign in required." if not delivery else "A valid delivery token is required.")
    if delivery:
        return {
            "project_id": token.project_id,
            "delivery": True,
            "scopes": token.scopes,
            "role": "reader",
            "actor": token.name,
        }
    user = session.get(User, token.user_id)
    if not user:
        raise HTTPException(401, "Session expired.")
    project_id = request.headers.get("x-moss-project") if project else None
    membership = session.get(Membership, (project_id, user.id)) if project_id else None
    if project_id and not membership:
        raise HTTPException(403, "You do not belong to this project.")
    return {
        "user": user,
        "token": token,
        "project_id": project_id,
        "role": membership.role if membership else None,
        "delivery": False,
        "actor": user.email,
    }


def require(context, role="reader", write=False, capability=None):
    if not context.get("project_id"):
        raise CmsError("Select a project.", "FORBIDDEN")
    if context.get("delivery"):
        if write or role != "reader" or capability not in {None, "read"}:
            raise CmsError(
                "Delivery tokens cannot write content." if write else "Insufficient project permissions.",
                "FORBIDDEN",
            )
        return
    from .permissions import ensure_access

    caps = ensure_access(context)
    if capability:
        needed = {capability}
    elif role == "admin":
        needed = {"schema", "team"}
    elif role == "editor":
        needed = {"edit"}
    else:
        needed = {"read"}
    if not needed <= caps:
        raise CmsError("Insufficient project permissions.", "FORBIDDEN")
    if write:
        supplied = context["request"].headers.get("x-moss-csrf", "")
        if not hmac.compare_digest(context["token"].csrf, supplied):
            raise CmsError("Invalid CSRF token. Sign in again.", "FORBIDDEN")


def valid_email(value):
    value = value.strip().lower()
    if len(value) > 254 or "@" not in value or "." not in value.rsplit("@", 1)[-1]:
        raise CmsError("Enter a valid email address.")
    return value
