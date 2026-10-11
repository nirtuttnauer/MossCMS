"""Original and variant media links share an expiry policy and signing format."""

import hashlib
import hmac
import time

MEDIA_TTL_SECONDS = 900


def media_signature(secret, id, expires, width=None):
    value = f"{id}:{expires}" if width is None else f"{id}:{width}:{expires}"
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def media_url(settings, id, width=None):
    expires = int(time.time()) + MEDIA_TTL_SECONDS
    path = f"/media/{id}" if width is None else f"/media/{id}/variant/{width}"
    signature = media_signature(settings.secret, id, expires, width)
    return f"{settings.public_url}{path}?expires={expires}&signature={signature}"


def valid_media_signature(settings, id, expires, signature, width=None):
    current = time.time()
    expected = media_signature(settings.secret, id, expires, width)
    return current <= expires <= current + MEDIA_TTL_SECONDS + 1 and hmac.compare_digest(expected, signature)
