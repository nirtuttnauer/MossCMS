from io import BytesIO
from urllib.parse import urlsplit
from unittest.mock import Mock, patch
from pathlib import Path

import pytest
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import select
from app.images import MAX_DECODED_PIXELS, process_image
from app.models import Asset


def png(width=800, height=400):
    output = BytesIO()
    Image.new("RGB", (width, height), "red").save(output, format="PNG")
    return output.getvalue()


@pytest.mark.parametrize("mime,format", [("image/jpeg", "JPEG"), ("image/png", "PNG"), ("image/webp", "WEBP")])
def test_supported_rasters_decode_and_generate_webp(mime, format):
    output = BytesIO()
    Image.new("RGB", (4, 2), "red").save(output, format=format)
    width, height, variants = process_image(output.getvalue(), mime)
    assert (width, height) == (4, 2)
    assert len(variants) == 1
    variant_width, variant_height, data = variants[0]
    assert (variant_width, variant_height) == (4, 2)
    with Image.open(BytesIO(data)) as image:
        assert image.format == "WEBP"
        assert image.size == (4, 2)


@pytest.mark.parametrize("mime", ["text/plain", "image/svg+xml", "image/gif", "application/octet-stream"])
def test_other_mimes_pass_through_without_decoding(mime):
    with patch("app.images.Image.open") as open_image:
        assert process_image(b"opaque contents", mime) == (None, None, [])
    open_image.assert_not_called()


@pytest.mark.parametrize("size,accepted", [((5000, 4000), True), ((5000, 4001), False)])
def test_decoded_pixel_boundary_before_loading(size, accepted):
    assert Image.MAX_IMAGE_PIXELS == MAX_DECODED_PIXELS == 20_000_000
    image = Mock(format="PNG", n_frames=1, width=size[0], height=size[1], size=size)
    image.getbands.return_value = ("R", "G", "B")
    oriented = Mock(size=size)
    oriented.copy.return_value = Image.new("RGB", (1, 1))
    with patch("app.images.Image.open") as open_image, patch("app.images.ImageOps.exif_transpose") as transpose:
        open_image.return_value.__enter__.return_value = image
        transpose.return_value.convert.return_value = oriented
        if accepted:
            width, height, variants = process_image(b"mocked image", "image/png")
            assert (width, height) == size
            assert len(variants) == 4
            image.load.assert_called_once_with()
            transpose.assert_called_once_with(image)
        else:
            with pytest.raises(HTTPException) as error:
                process_image(b"mocked image", "image/png")
            assert error.value.status_code == 422
            image.load.assert_not_called()
            transpose.assert_not_called()


@pytest.mark.parametrize("format,frames", [("GIF", 1), ("PNG", 2), ("WEBP", 2)])
def test_unsupported_or_animated_decoding_rejected_before_loading(format, frames):
    image = Mock(format=format, n_frames=frames, width=1, height=1, size=(1, 1))
    with patch("app.images.Image.open") as open_image:
        open_image.return_value.__enter__.return_value = image
        with pytest.raises(HTTPException) as error:
            process_image(b"mocked image", "image/png")
    assert error.value.status_code == 422
    image.load.assert_not_called()


def test_local_variants_signed_bounded_and_missing(app, client, admin):
    result = client.post("/api/assets", headers=admin, files={"file": ("image.png", png(), "image/png")})
    assert result.status_code == 200, result.text
    asset = result.json()
    assert (asset["width"], asset["height"]) == (800, 400)
    assert [v["width"] for v in asset["variants"]] == [320, 640, 800]
    url = urlsplit(asset["variants"][0]["url"])
    assert client.get(url.path + "?" + url.query).headers["content-type"] == "image/webp"
    assert client.get(url.path.replace("320", "640") + "?" + url.query).status_code == 403
    with app.state.db() as session:
        record = session.get(Asset, asset["id"])
        (app.state.settings.storage_dir / record.variants[0]["key"]).unlink()
    assert client.get(url.path + "?" + url.query).status_code == 404
    assert (
        client.post("/api/assets", headers=admin, files={"file": ("bad.png", b"invalid", "image/png")}).status_code
        == 422
    )
    assert (
        client.post("/api/assets", headers=admin, files={"file": ("wide.png", png(10001, 1), "image/png")}).status_code
        == 422
    )


def test_s3_upload_and_presign_use_same_variant_contract(app, client, admin):
    app.state.settings.s3_bucket = "test-bucket"
    store = Mock()
    store.generate_presigned_url.return_value = "https://storage.example/signed"
    with patch("app.storage.boto3.client", return_value=store):
        result = client.post("/api/assets", headers=admin, files={"file": ("image.png", png(), "image/png")}).json()
        assert store.put_object.call_count == 4
        assert all(call.kwargs["Bucket"] == "test-bucket" for call in store.put_object.call_args_list)
        url = urlsplit(result["variants"][0]["url"])
        response = client.get(url.path + "?" + url.query, follow_redirects=False)
        assert response.status_code == 307
        assert store.generate_presigned_url.call_args.kwargs["ExpiresIn"] <= 900


def test_asset_pagination_search_and_image_only_validation(client, admin):
    from conftest import gql, define, entry

    ids = []
    for name in ["Alpha.png", "Beta.png", "Gamma.png"]:
        ids.append(
            client.post("/api/assets", headers=admin, files={"file": (name, png(1, 1), "image/png")}).json()["id"]
        )
    document = client.post("/api/assets", headers=admin, files={"file": ("file.txt", b"text", "text/plain")}).json()[
        "id"
    ]
    query = "query($after:String){assetPage(first:2,imagesOnly:true,after:$after)}"
    first = gql(client, admin, query)["data"]["assetPage"]
    second = gql(client, admin, query, {"after": first["endCursor"]})["data"]["assetPage"]
    assert {a["id"] for a in first["nodes"] + second["nodes"]} == set(ids)
    assert gql(client, admin, '{assetPage(search:"Beta"){}}').get("errors")  # JSON scalar must not have selection
    assert len(gql(client, admin, '{assetPage(search:"Beta")}')["data"]["assetPage"]["nodes"]) == 1
    define(
        client, admin, fields=[{"name": "title", "type": "text"}, {"name": "cover", "type": "asset", "imageOnly": True}]
    )
    assert "errors" in entry(client, admin, data={"title": "Test", "cover": document})


def test_failed_local_upload_removes_temporary_and_completed_objects(app, client, admin, monkeypatch):
    original = Path.write_bytes
    writes = 0

    def fail_second_write(path, data):
        nonlocal writes
        writes += 1
        result = original(path, data)
        if writes == 2:
            raise OSError("Simulated partial write failure")
        return result

    monkeypatch.setattr(Path, "write_bytes", fail_second_write)
    response = client.post("/api/assets", headers=admin, files={"file": ("image.png", png(), "image/png")})
    assert response.status_code == 500
    assert not [path for path in app.state.settings.storage_dir.rglob("*") if path.is_file()]
    with app.state.db() as session:
        assert session.scalars(select(Asset)).all() == []
