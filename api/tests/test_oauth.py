"""OAuth callback failures create no account, and logs omit the client secret and authorization code."""

import base64
import logging
from urllib.parse import parse_qs, urlsplit

import httpx
from sqlalchemy import select

from app.models import OAuthIdentity, Token, User

CLIENT_SECRET = "moss-oauth-client-secret-marker"
AUTH_CODE = "moss-oauth-authorization-code-marker"
ACCESS_TOKEN = "moss-access-token-marker"


def _accounts(app):
    with app.state.db() as session:
        users = [(row.email, row.id) for row in session.scalars(select(User).order_by(User.email))]
        identities = [
            (row.provider, row.subject, row.user_id)
            for row in session.scalars(select(OAuthIdentity).order_by(OAuthIdentity.provider, OAuthIdentity.subject))
        ]
        invites = [
            row.email for row in session.scalars(select(Token).where(Token.kind == "invite").order_by(Token.email))
        ]
    return users, identities, invites


def _record_text(record):
    parts = [record.getMessage()]
    if record.exc_info and record.exc_info[1] is not None:
        parts.append(str(record.exc_info[1]))
    return "\n".join(parts)


def _log_problems(caplog):
    """Application and provider-client logs must not carry the secret or the authorization code.

    The test client records the callback URL it was given. That harness line is the request
    under test, not the service log.
    """
    problems = []
    for record in caplog.records:
        message = _record_text(record)
        if CLIENT_SECRET in message:
            problems.append(record.name)
        if AUTH_CODE not in message:
            continue
        harness = record.name == "httpx" and "testserver" in message and "idp.test" not in message
        if not harness:
            problems.append(record.name)
    return problems


def _transport(calls, *, accept_code=True):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.endswith("/access_token") or request.url.path.endswith("/token"):
            body = request.content.decode()
            if not accept_code or AUTH_CODE not in body:
                return httpx.Response(400, json={"error": "invalid_grant", "error_description": "rejected"})
            return httpx.Response(200, json={"access_token": ACCESS_TOKEN, "token_type": "bearer"})
        if request.url.path == "/user":
            return httpx.Response(200, json={"id": 42, "login": "ada", "name": "Ada"})
        if request.url.path == "/user/emails":
            return httpx.Response(200, json=[{"email": "admin@example.com", "verified": True, "primary": True}])
        if request.url.path.endswith("/openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "issuer": "https://idp.test",
                    "authorization_endpoint": "https://idp.test/authorize",
                    "token_endpoint": "https://idp.test/oauth/token",
                    "userinfo_endpoint": "https://idp.test/userinfo",
                },
            )
        return httpx.Response(404, json={"error": "not-found"})

    return httpx.MockTransport(handler)


def _register_github(app, transport):
    app.state.oauth_providers = [{"id": "github", "name": "GitHub"}]
    app.state.oauth.register(
        "github",
        client_id="moss-oauth-client",
        client_secret=CLIENT_SECRET,
        access_token_url="https://idp.test/login/oauth/access_token",
        authorize_url="https://idp.test/login/oauth/authorize",
        api_base_url="https://idp.test/",
        client_kwargs={"scope": "read:user user:email", "transport": transport},
    )


def _register_oidc(app, transport):
    app.state.oauth_providers = [{"id": "oidc", "name": "Single sign-on"}]
    app.state.oauth.register(
        "oidc",
        client_id="moss-oauth-client",
        client_secret=CLIENT_SECRET,
        server_metadata_url="https://idp.test/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256", "transport": transport},
    )


def _state_from(location):
    assert CLIENT_SECRET not in location
    assert AUTH_CODE not in location
    return parse_qs(urlsplit(location).query)["state"][0]


def _basic_credentials(request):
    encoded = request.headers["authorization"].split(" ", 1)[1]
    return base64.b64decode(encoded)


def _callback(client, **params):
    response = client.get("/auth/oauth/github/callback", params=params, follow_redirects=False)
    assert response.status_code == 303, response.text
    location = response.headers["location"]
    assert location.startswith("/#login?error=")
    assert CLIENT_SECRET not in location
    assert AUTH_CODE not in location
    return response


def test_unknown_provider_is_not_found(client, admin):
    assert client.get("/auth/oauth/unknown/start", follow_redirects=False).status_code == 404
    assert client.post("/auth/oauth/unknown/link", headers=admin).status_code == 404
    callback = client.get("/auth/oauth/unknown/callback", params={"code": AUTH_CODE}, follow_redirects=False)
    assert callback.status_code == 404
    assert CLIENT_SECRET not in callback.text
    assert AUTH_CODE not in callback.text


def test_missing_or_mismatched_state_creates_no_account(app, client, admin, caplog):
    calls = []
    _register_github(app, _transport(calls))
    invite = client.post(
        "/api/team/invitations", headers=admin, json={"email": "invited@example.com", "role": "reader"}
    ).json()["url"]
    caplog.set_level(logging.DEBUG)
    before = _accounts(app)
    assert before[2] == ["invited@example.com"]
    start = client.get("/auth/oauth/github/start", params={"invite": invite.split("/")[-1]}, follow_redirects=False)
    assert start.status_code == 302, start.text
    state = _state_from(start.headers["location"])
    assert state
    for params in ({}, {"code": AUTH_CODE}, {"code": AUTH_CODE, "state": "mismatched-oauth-state"}):
        response = _callback(client, **params)
        assert _accounts(app) == before
        assert calls == []
        assert _log_problems(caplog) == [], response.headers["location"]


def test_missing_code_and_rejected_exchange_create_no_account(app, client, admin, caplog):
    calls = []
    _register_github(app, _transport(calls, accept_code=False))
    invite = client.post(
        "/api/team/invitations", headers=admin, json={"email": "invited@example.com", "role": "reader"}
    ).json()["url"]
    caplog.set_level(logging.DEBUG)
    before = _accounts(app)
    start = client.get("/auth/oauth/github/start", params={"invite": invite.split("/")[-1]}, follow_redirects=False)
    state = _state_from(start.headers["location"])
    missing = _callback(client, state=state)
    assert _accounts(app) == before
    assert calls == []
    assert _log_problems(caplog) == [], missing.headers["location"]

    start = client.get("/auth/oauth/github/start", params={"invite": invite.split("/")[-1]}, follow_redirects=False)
    state = _state_from(start.headers["location"])
    rejected = _callback(client, code=AUTH_CODE, state=state)
    assert _accounts(app) == before
    body = calls[-1].content.decode()
    assert AUTH_CODE in body
    assert CLIENT_SECRET.encode() in _basic_credentials(calls[-1])
    assert AUTH_CODE not in str(calls[-1].url)
    assert CLIENT_SECRET not in str(calls[-1].url)
    assert _log_problems(caplog) == [], rejected.headers["location"]


def test_failed_link_adds_no_identity(app, client, admin, caplog):
    calls = []
    _register_github(app, _transport(calls))
    caplog.set_level(logging.DEBUG)
    before = _accounts(app)
    link = client.post("/auth/oauth/github/link", headers=admin)
    assert link.status_code == 200, link.text
    state = _state_from(link.json()["url"])
    response = _callback(client, code=AUTH_CODE, state="mismatched-oauth-state")
    assert state
    assert calls == []
    assert _accounts(app) == before
    assert _log_problems(caplog) == [], response.headers["location"]


def test_mocked_success_links_account_without_logging_secret_or_code(app, client, admin, caplog):
    calls = []
    _register_github(app, _transport(calls))
    caplog.set_level(logging.DEBUG)
    before = _accounts(app)
    link = client.post("/auth/oauth/github/link", headers=admin)
    assert link.status_code == 200, link.text
    state = _state_from(link.json()["url"])
    response = client.get(
        "/auth/oauth/github/callback", params={"code": AUTH_CODE, "state": state}, follow_redirects=False
    )
    assert response.status_code == 303, response.text
    assert response.headers["location"] == "/#content"
    users, identities, invites = _accounts(app)
    assert users == before[0]
    assert invites == before[2]
    assert identities == [("github", "42", before[0][0][1])]
    token_calls = [call for call in calls if str(call.url).endswith("/access_token")]
    assert len(token_calls) == 1
    assert AUTH_CODE in token_calls[0].content.decode()
    assert CLIENT_SECRET.encode() in _basic_credentials(token_calls[0])
    assert all(CLIENT_SECRET not in str(call.url) and AUTH_CODE not in str(call.url) for call in calls)
    assert _log_problems(caplog) == []
    account = client.get("/auth/me").json()
    assert account["providers"] == ["github"]
    assert account["user"]["email"] == "admin@example.com"


def test_oidc_bad_state_does_not_create_account_or_call_token_endpoint(app, client, admin, caplog):
    calls = []
    _register_oidc(app, _transport(calls))
    caplog.set_level(logging.DEBUG)
    before = _accounts(app)
    missing = client.get("/auth/oauth/oidc/callback", params={"code": AUTH_CODE}, follow_redirects=False)
    assert missing.status_code == 303
    assert missing.headers["location"].startswith("/#login?error=")
    assert calls == []
    assert _accounts(app) == before
    start = client.get("/auth/oauth/oidc/start", follow_redirects=False)
    assert start.status_code == 302, start.text
    state = _state_from(start.headers["location"])
    token_calls = [call for call in calls if call.url.path.endswith("/token")]
    mismatched = client.get(
        "/auth/oauth/oidc/callback",
        params={"code": AUTH_CODE, "state": "mismatched-oauth-state"},
        follow_redirects=False,
    )
    assert mismatched.status_code == 303
    assert [call for call in calls if call.url.path.endswith("/token")] == token_calls
    assert state
    assert _accounts(app) == before
    assert _log_problems(caplog) == []
    assert client.get("/auth/oauth/other/start", follow_redirects=False).status_code == 404
