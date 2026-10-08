from io import BytesIO
from urllib.parse import urlsplit
from unittest.mock import Mock, patch
from PIL import Image
from app.models import Asset


def png(width=800, height=400):
    output = BytesIO()
    Image.new("RGB", (width, height), "red").save(output, format="PNG")
    return output.getvalue()


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
