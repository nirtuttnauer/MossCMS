from urllib.parse import parse_qs, urlsplit

from app.media_links import valid_media_signature
from app.models import Asset, Project
from conftest import define, entry, gql
from test_cms import delivery
from test_preview import CREATE

ASSETS = "{entries{nodes{resolvedAssets{id name mime size url width height variants}}}}"
FIELDS = [
    {"name": "title", "type": "text"},
    {"name": "body", "type": "richText"},
    {"name": "cover", "type": "asset"},
    {"name": "secret", "type": "richText", "private": True},
]


def add_asset(session, project_id, id, mime="image/png"):
    session.add(
        Asset(
            id=id,
            project_id=project_id,
            name=f"{id}.asset",
            key=id,
            storage="local",
            mime=mime,
            size=25,
            width=640,
            height=320,
            variants=[{"width": 320, "height": 160, "size": 10, "key": f"{id}-320"}],
        )
    )


def resolved(client, headers, delivery=False):
    result = gql(client, headers, ASSETS, delivery=delivery)
    assert "errors" not in result, result
    return result["data"]["entries"]["nodes"][0]["resolvedAssets"]


def grant(client, admin, saved):
    result = gql(client, admin, CREATE, {"id": saved["id"], "version": saved["version"]})
    assert "errors" not in result, result
    return result["data"]["createPreviewGrant"]["token"]


def test_editorial_uses_draft_and_delivery_uses_live_asset_metadata(app, client, admin):
    define(client, admin, fields=FIELDS)
    with app.state.db.begin() as session:
        for id in ["live", "draft", "private"]:
            add_asset(session, admin["x-moss-project"], id)
    saved = entry(
        client,
        admin,
        data={"title": "Post", "cover": "live", "secret": "![Hidden](asset:private)"},
        status="published",
    )["data"]["saveEntry"]
    updated = entry(
        client,
        admin,
        data={"title": "Draft", "cover": "draft", "secret": "![Hidden](asset:private)"},
        id=saved["id"],
        version=saved["version"],
    )
    assert "errors" not in updated, updated
    assert [a["id"] for a in resolved(client, admin)] == ["draft"]
    assets = resolved(client, delivery(client, admin, ["article"]), delivery=True)
    assert [a["id"] for a in assets] == ["live"]
    asset = assets[0]
    assert (asset["name"], asset["mime"], asset["size"], asset["width"], asset["height"]) == (
        "live.asset",
        "image/png",
        25,
        640,
        320,
    )
    variant = asset["variants"][0]
    assert (variant["width"], variant["height"], variant["size"]) == (320, 160, 10)
    for url, width in [(asset["url"], None), (variant["url"], 320)]:
        parsed = urlsplit(url)
        assert parsed.path == ("/media/live" if width is None else "/media/live/variant/320")
        params = parse_qs(parsed.query)
        assert valid_media_signature(
            app.state.settings, "live", int(params["expires"][0]), params["signature"][0], width
        )


def test_preview_uses_frozen_public_assets_and_scopes_rich_text_ids(app, client, admin):
    define(client, admin, fields=FIELDS)
    with app.state.db.begin() as session:
        session.add(Project(id="foreign", name="Other workspace"))
        session.flush()
        for id, mime in [
            ("frozen", "image/gif"),
            ("later", "image/png"),
            ("private", "image/png"),
            ("doc", "text/plain"),
        ]:
            add_asset(session, admin["x-moss-project"], id, mime)
        add_asset(session, "foreign", "foreign-image")
    body = "![Frozen](asset:frozen) ![Foreign](asset:foreign-image) ![Doc](asset:doc) ![Missing](asset:missing)"
    saved = entry(client, admin, data={"title": "Frozen", "body": body, "secret": "![Hidden](asset:private)"})["data"][
        "saveEntry"
    ]
    raw = grant(client, admin, saved)
    assert [a["id"] for a in resolved(client, admin)] == ["frozen"]
    updated = entry(
        client,
        admin,
        data={"title": "Later", "body": "![Later](asset:later)"},
        id=saved["id"],
        version=saved["version"],
    )
    assert "errors" not in updated, updated
    response = client.post("/api/preview/redeem", headers=delivery(client, admin, ["article"]), json={"token": raw})
    assert response.status_code == 200, response.text
    preview = response.json()["entry"]
    assert preview["data"] == {"title": "Frozen", "body": body, "cover": None}
    assert [a["id"] for a in preview["resolvedAssets"]] == ["frozen"]
    assert preview["resolvedAssets"][0]["mime"] == "image/gif"
    assert preview["resolvedAssets"][0]["variants"][0]["width"] == 320
    assert "signature=" in preview["resolvedAssets"][0]["url"]


def test_sorted_50_id_bound_applies_before_workspace_and_mime_filtering(app, client, admin):
    define(client, admin)
    with app.state.db.begin() as session:
        session.add(Project(id="foreign", name="Other workspace"))
        session.flush()
        for index in range(55):
            add_asset(
                session,
                "foreign" if index == 2 else admin["x-moss-project"],
                f"asset-{index:02}",
                "text/plain" if index < 2 else "image/png",
            )
    body = " ".join(f"![Image](asset:asset-{i:02})" for i in reversed(range(55)))
    saved = entry(client, admin, data={"title": "Bounded", "body": body}, status="published")["data"]["saveEntry"]
    raw = grant(client, admin, saved)
    token = delivery(client, admin)
    expected = {f"asset-{i:02}" for i in range(3, 50)}
    assert {a["id"] for a in resolved(client, admin)} == expected
    assert {a["id"] for a in resolved(client, token, delivery=True)} == expected
    response = client.post("/api/preview/redeem", headers=token, json={"token": raw})
    assert response.status_code == 200, response.text
    assert {a["id"] for a in response.json()["entry"]["resolvedAssets"]} == expected


def test_asset_picker_images_only_retains_three_raster_mimes(app, client, admin):
    with app.state.db.begin() as session:
        for id, mime in [
            ("png", "image/png"),
            ("jpeg", "image/jpeg"),
            ("webp", "image/webp"),
            ("gif", "image/gif"),
            ("doc", "text/plain"),
        ]:
            add_asset(session, admin["x-moss-project"], id, mime)
    result = gql(client, admin, "{assetPage(imagesOnly:true)}")
    assert "errors" not in result, result
    assert {a["id"] for a in result["data"]["assetPage"]["nodes"]} == {"png", "jpeg", "webp"}
