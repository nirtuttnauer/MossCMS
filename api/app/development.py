"""Temporary local administrator identity, enabled only by MOSS_SKIP_AUTH.

The identity is not a delivery credential. After validation, a production
settings object keeps skip_auth off when the flag is changed.
"""

import sys
from pathlib import Path
from types import FrameType

from sqlalchemy import select

from .config import Settings
from .models import Project, User

DEVELOPMENT_USER_ID = "00000000-0000-4000-8000-000000000001"
DEVELOPMENT_USER_EMAIL = "development@mosscms.invalid"
_SEAL = "_moss_development_seal"


def _stored(settings):
    try:
        return vars(settings)
    except TypeError:
        return {}


def _raw_skip_auth(settings) -> bool:
    return bool(_stored(settings).get("skip_auth", False))


def _sealed_environment(settings):
    seal = _stored(settings).get(_SEAL)
    if isinstance(seal, dict):
        return seal.get("environment")
    return None


def _caller_is_delivery_identify() -> bool:
    """True when security.identify is reading skip_auth for a delivery request."""
    current: FrameType | None = sys._getframe(1)
    while current is not None:
        code = current.f_code
        if Path(code.co_filename).name == "development.py":
            current = current.f_back
            continue
        return (
            code.co_name == "identify"
            and Path(code.co_filename).name == "security.py"
            and bool(current.f_locals.get("delivery"))
        )
    return False


def _skip_auth_visible(settings) -> bool:
    """Raw flag, hidden once a non-development process has passed validation."""
    if not _raw_skip_auth(settings):
        return False
    sealed = _sealed_environment(settings)
    if sealed is None:
        return True
    if sealed != "development":
        return False
    return getattr(settings, "environment", None) == "development"


class _SkipAuth:
    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        if _caller_is_delivery_identify():
            return False
        return _skip_auth_visible(obj)

    def __set__(self, obj, value) -> None:
        obj.__dict__["skip_auth"] = bool(value)


def development_actor(settings, *, delivery: bool = False) -> str:
    """Return the development user id, or refuse delivery and a production flip."""
    if delivery:
        raise RuntimeError("The development identity cannot act as a delivery token.")
    if _raw_skip_auth(settings) and (sealed := _sealed_environment(settings)) is not None and sealed != "development":
        raise RuntimeError("MOSS_SKIP_AUTH cannot be enabled after process start in production.")
    if _skip_auth_visible(settings) and getattr(settings, "environment", None) == "development":
        return DEVELOPMENT_USER_ID
    raise RuntimeError("MOSS_SKIP_AUTH is not enabled for this process.")


def initialize_development(factory):
    with factory.begin() as session:
        if not session.get(User, DEVELOPMENT_USER_ID):
            session.add(
                User(
                    id=DEVELOPMENT_USER_ID,
                    email=DEVELOPMENT_USER_EMAIL,
                    name="Local developer",
                    password_hash="development-bypass-disabled-for-password-login",
                )
            )
        if not session.scalar(select(Project.id).limit(1)):
            session.add(Project(name="My workspace"))


def _install() -> None:
    if getattr(Settings, "_moss_development_guard", False):
        return
    original = Settings.validate

    def validate(self):
        result = original(self)
        stored = _stored(self)
        if _SEAL not in stored:
            stored[_SEAL] = {"environment": self.environment}
        return result

    setattr(Settings, "skip_auth", _SkipAuth())
    setattr(Settings, "validate", validate)
    setattr(Settings, "_moss_development_guard", True)


_install()
