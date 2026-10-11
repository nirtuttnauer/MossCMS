from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from app.models import Asset
from app.storage import _presigned_expiry_seconds, media, variant


@pytest.mark.parametrize(
    "expires,expected",
    [(99, 1), (100, 1), (101, 1), (102, 2), (999, 899), (1000, 900), (1001, 900)],
)
def test_presigned_expiry_clamps_remaining_whole_seconds(expires, expected):
    with patch("app.storage.time.time", return_value=100.75) as clock:
        assert _presigned_expiry_seconds(expires) == expected
    clock.assert_called_once_with()


@pytest.fixture
def storage_request(tmp_path):
    settings = SimpleNamespace(
        s3_bucket="synthetic-bucket", s3_endpoint="https://storage.example", storage_dir=tmp_path
    )
    session = MagicMock()
    session.__enter__.return_value = session
    db = Mock(return_value=session)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings, db=db)))
    return request, session


def call_route(is_variant, request):
    if is_variant:
        return variant("asset-id", 320, 800, "synthetic-signature", request)
    return media("asset-id", 800, "synthetic-signature", request)


def stored_asset(storage="s3"):
    return SimpleNamespace(
        storage=storage,
        key="project/original",
        name="download.pdf",
        mime="application/pdf",
        variants=[{"width": 320, "key": "project/320.webp"}],
    )


@pytest.mark.parametrize("is_variant", [False, True])
def test_s3_route_preserves_signing_contract_and_evaluation_order(storage_request, is_variant):
    request, session = storage_request
    events = []
    session.get.side_effect = lambda *args: events.append("get") or stored_asset()
    request.app.state.db.side_effect = lambda: events.append("db") or session
    store = Mock()
    store.generate_presigned_url.side_effect = lambda *args, **kwargs: (
        events.append("presign") or "https://signed.example"
    )
    session.__exit__.side_effect = lambda *args: events.append("close")
    with (
        patch(
            "app.storage.valid_media_signature", side_effect=lambda *args: events.append("validate") or True
        ) as valid,
        patch(
            "app.storage.boto3.client", side_effect=lambda *args, **kwargs: events.append("client") or store
        ) as client,
        patch("app.storage.time.time", side_effect=lambda: events.append("clock") or 100.75) as clock,
    ):
        response = call_route(is_variant, request)
    valid.assert_called_once_with(
        request.app.state.settings, "asset-id", 800, "synthetic-signature", *([320] if is_variant else [])
    )
    session.get.assert_called_once_with(Asset, "asset-id")
    client.assert_called_once_with("s3", endpoint_url="https://storage.example")
    params = {"Bucket": "synthetic-bucket"}
    params.update(
        {"Key": "project/320.webp", "ResponseContentType": "image/webp"}
        if is_variant
        else {"Key": "project/original", "ResponseContentDisposition": "attachment"}
    )
    store.generate_presigned_url.assert_called_once_with("get_object", Params=params, ExpiresIn=700)
    clock.assert_called_once_with()
    assert events == ["validate", "db", "get", "client", "clock", "presign", "close"]
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 307
    assert response.headers["location"] == "https://signed.example"


@pytest.mark.parametrize("is_variant", [False, True])
def test_invalid_link_exits_before_storage_access(storage_request, is_variant):
    request, session = storage_request
    with (
        patch("app.storage.valid_media_signature", return_value=False),
        patch("app.storage.boto3.client") as client,
        patch("app.storage.time.time") as clock,
        pytest.raises(HTTPException) as raised,
    ):
        call_route(is_variant, request)
    assert raised.value.status_code == 403
    noun = "variant" if is_variant else "asset"
    assert raised.value.detail == f"This {noun} link is expired or invalid."
    request.app.state.db.assert_not_called()
    session.get.assert_not_called()
    client.assert_not_called()
    clock.assert_not_called()


@pytest.mark.parametrize("is_variant", [False, True])
def test_missing_asset_exits_before_presigning(storage_request, is_variant):
    request, session = storage_request
    session.get.return_value = None
    with (
        patch("app.storage.valid_media_signature", return_value=True),
        patch("app.storage.boto3.client") as client,
        patch("app.storage.time.time") as clock,
        pytest.raises(HTTPException) as raised,
    ):
        call_route(is_variant, request)
    assert raised.value.status_code == 404
    assert raised.value.detail == ("Image variant not found." if is_variant else "Asset not found.")
    session.__exit__.assert_called_once()
    client.assert_not_called()
    clock.assert_not_called()


@pytest.mark.parametrize("variants", [None, [{"width": 640, "key": "project/640.webp"}]])
def test_missing_requested_variant_exits_before_presigning(storage_request, variants):
    request, session = storage_request
    asset = stored_asset()
    asset.variants = variants
    session.get.return_value = asset
    with (
        patch("app.storage.valid_media_signature", return_value=True),
        patch("app.storage.boto3.client") as client,
        patch("app.storage.time.time") as clock,
        pytest.raises(HTTPException) as raised,
    ):
        call_route(True, request)
    assert raised.value.status_code == 404
    assert raised.value.detail == "Image variant not found."
    client.assert_not_called()
    clock.assert_not_called()


@pytest.mark.parametrize("is_variant", [False, True])
def test_local_response_preserves_headers_and_download_behavior(storage_request, is_variant):
    request, session = storage_request
    asset = stored_asset("local")
    session.get.return_value = asset
    key = "project/320.webp" if is_variant else asset.key
    target = request.app.state.settings.storage_dir / key
    target.parent.mkdir(parents=True)
    target.write_bytes(b"synthetic-file")
    with (
        patch("app.storage.valid_media_signature", return_value=True),
        patch("app.storage.boto3.client") as client,
        patch("app.storage.time.time") as clock,
    ):
        response = call_route(is_variant, request)
    assert isinstance(response, FileResponse)
    assert response.path == target
    assert response.media_type == ("image/webp" if is_variant else "application/pdf")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "private, max-age=60"
    if is_variant:
        assert response.filename is None
        assert "Content-Disposition" not in response.headers
    else:
        assert response.filename == "download.pdf"
        assert response.headers["Content-Disposition"] == 'attachment; filename="download.pdf"'
    client.assert_not_called()
    clock.assert_not_called()


@pytest.mark.parametrize("is_variant", [False, True])
def test_missing_local_file_preserves_restore_error(storage_request, is_variant):
    request, session = storage_request
    session.get.return_value = stored_asset("local")
    with (
        patch("app.storage.valid_media_signature", return_value=True),
        patch("app.storage.boto3.client") as client,
        patch("app.storage.time.time") as clock,
        pytest.raises(HTTPException) as raised,
    ):
        call_route(is_variant, request)
    assert raised.value.status_code == 404
    noun = "Image variant" if is_variant else "Asset file"
    assert raised.value.detail == f"{noun} is missing. Restore it from backup."
    client.assert_not_called()
    clock.assert_not_called()
