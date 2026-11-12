"""The skip-auth development user cannot authenticate with a password."""

from app.development import DEVELOPMENT_USER_ID, initialize_development
from app.models import User
from app.security import check_password

DEVELOPMENT_PASSWORD_HASH = "development-bypass-disabled-for-password-login"
REJECTED_PASSWORDS = ("", "development", "password")


def development_identity(factory):
    with factory() as session:
        user = session.get(User, DEVELOPMENT_USER_ID)
        assert user is not None
        return user.name, user.email, user.password_hash


def test_check_password_rejects_the_stored_development_hash(client, app):
    assert app.state.settings.skip_auth is False
    initialize_development(app.state.db)
    name, email, stored = development_identity(app.state.db)
    assert (name, email, stored) == (
        "Local developer",
        "development@mosscms.invalid",
        DEVELOPMENT_PASSWORD_HASH,
    )
    for password in (*REJECTED_PASSWORDS, stored):
        assert check_password(password, stored) is False
    for password in ("development", "password", stored):
        response = client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        assert response.status_code == 401, response.text


def test_second_initialize_development_leaves_existing_user_unchanged(client, app):
    assert app.state.settings.skip_auth is False
    initialize_development(app.state.db)
    planted = development_identity(app.state.db)
    initialize_development(app.state.db)
    assert development_identity(app.state.db) == planted

    existing = ("Kept name", "kept@mosscms.invalid", "kept-hash-not-a-login-secret")
    with app.state.db.begin() as session:
        user = session.get(User, DEVELOPMENT_USER_ID)
        user.name, user.email, user.password_hash = existing
    initialize_development(app.state.db)
    assert development_identity(app.state.db) == existing
