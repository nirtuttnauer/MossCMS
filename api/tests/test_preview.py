import json
import logging
import unicodedata
from datetime import timedelta

from app.models import PreviewGrant, now
from app.security import digest
from conftest import define, entry, gql
from test_cms import delivery, invited

# Shin-dot (ccc 24) is stored ahead of qamats (ccc 18), and dagesh (ccc 21) ahead of
# sheva (ccc 10). NFC would reorder those marks. Redemption must keep this order.
HEBREW_TITLE = "\u05e9\u05c1\u05b8\u05dc\u05d5\u05b9\u05dd"
HEBREW_BODY = "\u05d1\u05bc\u05b0\u05e8\u05b5\u05d0\u05e9\u05c1\u05b4\u05d9\u05ea \u05d1\u05b8\u05e8\u05b8\u05d0 \u05d0\u05b1\u05dc\u05b9\u05d4\u05b4\u05d9\u05dd"
PRIVATE_FIELD = "draft-private-field"

CREATE = "mutation($id:ID!,$version:Int!){createPreviewGrant(id:$id,version:$version)}"


def test_preview_is_frozen_private_projected_and_revocable(app, client, admin):
    define(client, admin)
    saved = entry(client, admin, data={"title": "Draft", "body": "Preview", "secret": "Private"})["data"]["saveEntry"]
    grant = gql(client, admin, CREATE, {"id": saved["id"], "version": saved["version"]})["data"]["createPreviewGrant"]
    entry(client, admin, data={"title": "Later", "body": "New"}, id=saved["id"], version=saved["version"])
    token = delivery(client, admin, ["article"])
    response = client.post("/api/preview/redeem", headers=token, json={"token": grant["token"]})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert "noindex" in response.headers["x-robots-tag"]
    assert response.json()["entry"]["data"] == {"title": "Draft", "body": "Preview"}
    assert gql(client, token, "{entries{total}}", delivery=True)["data"]["entries"]["total"] == 0
    gql(client, admin, "mutation($id:ID!){revokePreviewGrant(id:$id)}", {"id": grant["id"]})
    assert client.post("/api/preview/redeem", headers=token, json={"token": grant["token"]}).status_code == 403
    assert client.post("/api/preview/redeem", headers=token, json={"token": "x" * 32}).status_code == 403


def test_preview_issue_and_redemption_enforce_roles_scopes_expiry(app, client, admin):
    define(client, admin)
    define(client, admin, "other")
    saved = entry(client, admin)["data"]["saveEntry"]
    reader, headers, _ = invited(app, client, admin, "reader", "reader@example.com")
    args = {"id": saved["id"], "version": saved["version"]}
    assert gql(reader, headers, CREATE, args)["errors"][0]["extensions"]["code"] == "FORBIDDEN"
    token = delivery(client, admin, ["other"])
    assert "errors" in gql(client, token, CREATE, args, delivery=True)
    grant = gql(client, admin, CREATE, args)["data"]["createPreviewGrant"]
    assert client.post("/api/preview/redeem", headers=token, json={"token": grant["token"]}).status_code == 404
    token = delivery(client, admin, ["article"])
    with app.state.db.begin() as session:
        session.get(PreviewGrant, digest(grant["token"])).expires_at = now() - timedelta(seconds=1)
    assert client.post("/api/preview/redeem", headers=token, json={"token": grant["token"]}).status_code == 403


def test_private_title_never_leaks_in_delivery_metadata_search_or_sort(client, admin):
    define(client, admin, fields=[{"name": "title", "type": "text", "private": True}, {"name": "body", "type": "text"}])
    entry(client, admin, slug="a", data={"title": "Zebra secret", "body": "Public"}, status="published")
    entry(client, admin, slug="z", data={"title": "Alpha secret", "body": "Public"}, status="published")
    token = delivery(client, admin)
    result = gql(
        client,
        token,
        '{entries(sort:"title_asc"){nodes{slug title data}} hidden:entries(search:"secret"){total}}',
        delivery=True,
    )["data"]
    assert result["hidden"]["total"] == 0
    assert [n["title"] for n in result["entries"]["nodes"]] == ["a", "z"]
    assert all("title" not in n["data"] for n in result["entries"]["nodes"])


def test_preview_origin_configuration_is_admin_only_and_origin_scoped(app, client, admin):
    for origin in ["javascript:alert(1)", "https://example.com/path", "https://a@b.com", "https://example.com?q=x"]:
        assert client.patch("/api/project/preview", headers=admin, json={"origin": origin}).status_code == 422
    assert (
        client.patch("/api/project/preview", headers=admin, json={"origin": "https://site.example/"}).status_code == 200
    )
    define(client, admin, "sitePost")
    saved = entry(client, admin, key="sitePost")["data"]["saveEntry"]
    grant = gql(client, admin, CREATE, {"id": saved["id"], "version": saved["version"]})["data"]["createPreviewGrant"]
    assert grant["previewUrl"] == "https://site.example/preview#grant=" + grant["token"]
    reader, headers, _ = invited(app, client, admin, "reader", "preview-reader@example.com")
    assert (
        reader.patch("/api/project/preview", headers=headers, json={"origin": "https://other.example"}).status_code
        == 403
    )


def test_development_preview_issuer_is_allowed_only_with_explicit_bypass(tmp_path):
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app

    local = create_app(
        Settings(
            skip_auth=True,
            secret="s" * 40,
            setup_token="t" * 30,
            database_url=f"sqlite:///{tmp_path}/local.db",
            storage_dir=tmp_path / "media",
        )
    )
    with TestClient(local) as client:
        me = client.get("/auth/me").json()
        headers = {"x-moss-project": me["projects"][0]["id"], "x-moss-csrf": me["csrf"]}
        define(client, headers)
        saved = entry(client, headers)["data"]["saveEntry"]
        grant = gql(client, headers, CREATE, {"id": saved["id"], "version": saved["version"]})["data"][
            "createPreviewGrant"
        ]
        token = delivery(client, headers)
        assert client.post("/api/preview/redeem", headers=token, json={"token": grant["token"]}).status_code == 200


def _visible_text(value):
    if isinstance(value, str):
        pieces = [value]
        try:
            pieces.append(json.dumps(json.loads(value), ensure_ascii=False))
        except json.JSONDecodeError:
            pass
        return "\n".join(pieces)
    return json.dumps(value, ensure_ascii=False)


def _hides(value, *needles):
    blob = _visible_text(value)
    for needle in needles:
        assert needle not in blob


def test_hebrew_niqqud_draft_round_trips_on_redemption_and_stays_off_delivery(client, admin, caplog):
    assert unicodedata.normalize("NFC", HEBREW_TITLE) != HEBREW_TITLE
    assert unicodedata.normalize("NFC", HEBREW_BODY) != HEBREW_BODY
    assert any(unicodedata.combining(char) for char in HEBREW_TITLE)
    assert any(unicodedata.combining(char) for char in HEBREW_BODY)
    define(client, admin)
    saved = entry(
        client,
        admin,
        slug="hebrew-draft",
        data={"title": HEBREW_TITLE, "body": HEBREW_BODY, "secret": PRIVATE_FIELD},
    )["data"]["saveEntry"]
    assert saved["data"]["title"] == HEBREW_TITLE
    assert saved["data"]["body"] == HEBREW_BODY
    assert (
        gql(client, admin, "query($id:ID!){entry(id:$id){title}}", {"id": saved["id"]})["data"]["entry"]["title"]
        == HEBREW_TITLE
    )
    with caplog.at_level(logging.DEBUG, logger="mosscms"):
        grant = gql(client, admin, CREATE, {"id": saved["id"], "version": saved["version"]})["data"][
            "createPreviewGrant"
        ]
        entry(
            client,
            admin,
            slug="hebrew-draft",
            data={"title": "Later", "body": "Replaced", "secret": PRIVATE_FIELD},
            id=saved["id"],
            version=saved["version"],
        )
        token = delivery(client, admin, ["article"])
        delivery_secret = token["Authorization"].removeprefix("Bearer ")
        response = client.post("/api/preview/redeem", headers=token, json={"token": grant["token"]})
        assert response.status_code == 200, response.text
        redeemed = response.json()
        assert redeemed["entry"]["data"] == {"title": HEBREW_TITLE, "body": HEBREW_BODY}
        assert redeemed["revision"] == saved["version"]
        assert redeemed["entry"]["slug"] == "hebrew-draft"
        assert response.headers["cache-control"] == "no-store"
        assert "noindex" in response.headers["x-robots-tag"]
        _hides(response.text, PRIVATE_FIELD, "Replaced", grant["token"], delivery_secret)
        hidden = gql(
            client,
            token,
            "query($id:ID!){entry(id:$id){title data slug}}",
            {"id": saved["id"]},
            delivery=True,
        )
        assert hidden["data"] is None
        assert hidden["errors"][0]["extensions"]["code"] == "NOT_FOUND"
        _hides(hidden, HEBREW_TITLE, HEBREW_BODY, PRIVATE_FIELD, grant["token"], delivery_secret)
        searched = gql(
            client,
            token,
            "query($search:String!){entries(search:$search){total nodes{title data slug}}}",
            {"search": HEBREW_TITLE},
            delivery=True,
        )
        assert searched["data"]["entries"] == {"total": 0, "nodes": []}
        _hides(searched, HEBREW_TITLE, HEBREW_BODY, PRIVATE_FIELD, grant["token"], delivery_secret)
        listed_gql = gql(
            client,
            token,
            "{entries{total nodes{title data slug}}}",
            delivery=True,
        )
        assert listed_gql["data"]["entries"] == {"total": 0, "nodes": []}
        _hides(listed_gql, HEBREW_TITLE, HEBREW_BODY, PRIVATE_FIELD, grant["token"], delivery_secret)
        history = gql(
            client,
            token,
            "query($id:ID!){revisions(id:$id){snapshot}}",
            {"id": saved["id"]},
            delivery=True,
        )
        assert history["errors"][0]["extensions"]["code"] == "FORBIDDEN"
        _hides(history, HEBREW_TITLE, HEBREW_BODY, PRIVATE_FIELD, grant["token"], delivery_secret)
        by_id = client.get(f"/delivery/entries/{saved['id']}", headers=token)
        assert by_id.status_code == 404
        _hides(by_id.text, HEBREW_TITLE, HEBREW_BODY, PRIVATE_FIELD, grant["token"], delivery_secret)
        listed = client.get(
            "/delivery/entries",
            headers=token,
            params={"typeKey": "article", "total": "true", "search": HEBREW_TITLE},
        )
        assert listed.status_code == 200
        assert listed.json() == {"nodes": [], "endCursor": None, "hasNextPage": False, "total": 0}
        _hides(listed.text, HEBREW_TITLE, HEBREW_BODY, PRIVATE_FIELD, grant["token"], delivery_secret)
        assets = client.get(f"/delivery/entries/{saved['id']}/resolved-assets", headers=token)
        assert assets.status_code == 404
        _hides(assets.text, HEBREW_TITLE, HEBREW_BODY, PRIVATE_FIELD, grant["token"], delivery_secret)
        refused = client.post("/api/preview/redeem", headers=token, json={"token": "x" * 32})
        assert refused.status_code == 403
        _hides(refused.text, HEBREW_TITLE, HEBREW_BODY, PRIVATE_FIELD, grant["token"], delivery_secret)
    logged_records = [record for record in caplog.records if record.name.startswith("mosscms")]
    logged = "\n".join(record.getMessage() for record in logged_records)
    assert any("/api/preview/redeem" in record.getMessage() for record in logged_records)
    assert grant["token"] not in logged
    assert delivery_secret not in logged
