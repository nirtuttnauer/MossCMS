from datetime import timedelta
from app.models import PreviewGrant, now
from app.security import digest
from conftest import define, entry, gql
from test_cms import delivery, invited

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
