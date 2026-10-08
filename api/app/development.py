"""Temporary local administrator identity, enabled only by MOSS_SKIP_AUTH."""

from sqlalchemy import select

from .models import Project, User

DEVELOPMENT_USER_ID = "00000000-0000-4000-8000-000000000001"


def initialize_development(factory):
    with factory.begin() as session:
        if not session.get(User, DEVELOPMENT_USER_ID):
            session.add(
                User(
                    id=DEVELOPMENT_USER_ID,
                    email="development@mosscms.invalid",
                    name="Local developer",
                    password_hash="development-bypass-disabled-for-password-login",
                )
            )
        if not session.scalar(select(Project.id).limit(1)):
            session.add(Project(name="My workspace"))
