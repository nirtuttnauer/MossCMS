import hashlib
import hmac
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from app.media_links import media_signature, media_url, valid_media_signature


@pytest.mark.parametrize("width", [None, 320])
def test_signed_urls_preserve_original_and_variant_contracts(monkeypatch, width):
    monkeypatch.setattr("app.media_links.time.time", lambda: 1000000)
    settings = SimpleNamespace(secret="secret", public_url="https://cms.example")
    url = urlsplit(media_url(settings, "asset", width))
    assert url.path == ("/media/asset" if width is None else "/media/asset/variant/320")
    values = parse_qs(url.query)
    assert values["expires"] == ["1000900"]
    signed = b"asset:1000900" if width is None else b"asset:320:1000900"
    expected = hmac.new(b"secret", signed, hashlib.sha256).hexdigest()
    assert values["signature"] == [expected]
    assert valid_media_signature(settings, "asset", 1000900, expected, width)
    assert not valid_media_signature(settings, "other-asset", 1000900, expected, width)
    assert not valid_media_signature(settings, "asset", 1000900, expected, 640)
    assert not valid_media_signature(SimpleNamespace(secret="rotated"), "asset", 1000900, expected, width)


@pytest.mark.parametrize("expires,valid", [(999999, False), (1000000, True), (1000901, True), (1000902, False)])
def test_signature_expiry_bounds(monkeypatch, expires, valid):
    monkeypatch.setattr("app.media_links.time.time", lambda: 1000000)
    settings = SimpleNamespace(secret="secret")
    signature = media_signature(settings.secret, "asset", expires)
    assert valid_media_signature(settings, "asset", expires, signature) is valid
    assert not valid_media_signature(settings, "asset", expires, "invalid")
