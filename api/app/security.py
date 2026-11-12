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
        scheme, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
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


def client_address(request):
    """TCP peer. X-Forwarded-For and Forwarded are not read."""
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client else None
    return host or "unknown"


# Stored token ids are SHA-256 hex. A raw token is url-safe and is not that digest.
DRAFTS_TOKEN_KIND = "drafts"
_REDACTED = "[redacted]"
_RAW_TOKEN = re.compile(r"^[A-Za-z0-9_-]{32,}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9_-]{20,}")
_IDENTIFIER_KEYS = {"tokenid", "invitationid"}


def _normalized_key(key):
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _sensitive_key(key):
    name = _normalized_key(key)
    if name in _IDENTIFIER_KEYS:
        return False
    if name in {"password", "passwd", "secret", "token", "authorization", "csrf", "bearer", "cookie", "apikey", "raw"}:
        return True
    return name.endswith(("password", "passwordhash", "secret", "token", "apikey"))


def _looks_like_raw_token(value):
    return isinstance(value, str) and _RAW_TOKEN.fullmatch(value) is not None and _DIGEST.fullmatch(value) is None


def _scrub_string(value):
    if _looks_like_raw_token(value) or _BEARER.search(value):
        return _REDACTED
    return value


def _redact_audit_value(value, key=""):
    if key and _sensitive_key(key):
        return _REDACTED
    if isinstance(value, dict):
        return {str(name): _redact_audit_value(item, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [_redact_audit_value(item, key) for item in value]
    if isinstance(value, str):
        return _scrub_string(value)
    return value


def audit(session, project_id, actor, action, **details):
    if _looks_like_raw_token(actor):
        actor = _REDACTED
    session.add(Audit(project_id=project_id, actor=actor, action=action, details=_redact_audit_value(details) or {}))


def identify(request, session, delivery=False, project=True, *, drafts=False):
    if drafts and delivery:
        raise HTTPException(401, "A valid drafts token is required.")
    if request.app.state.settings.skip_auth and not delivery and not drafts:
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
    if drafts:
        expected, failure = DRAFTS_TOKEN_KIND, "A valid drafts token is required."
    elif delivery:
        expected, failure = "delivery", "A valid delivery token is required."
    else:
        expected, failure = "session", "Sign in required."
    if not token or token.expires_at <= now() or token.kind != expected or (drafts and not token.project_id):
        raise HTTPException(401, failure)
    if drafts:
        return {
            "project_id": token.project_id,
            "delivery": False,
            "drafts": True,
            "scopes": list(token.scopes or []),
            "role": "reader",
            "actor": token.name or "drafts",
            "token": token,
        }
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
    if context.get("drafts") and (write or role != "reader" or capability not in {None, "read"}):
        raise CmsError("Draft tokens cannot write content.", "FORBIDDEN")
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
    if isinstance(value, str) and ("\n" in value or "\r" in value):
        raise CmsError("Enter a valid email address.")
    value = value.strip().lower()
    domain = value.rsplit("@", 1)[-1]
    if len(value) > 254 or value.count("@") != 1 or "." not in domain:
        raise CmsError("Enter a valid email address.")
    return value
