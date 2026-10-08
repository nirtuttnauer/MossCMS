"""Bounded raster decoding at upload time and signed variant metadata."""

import hashlib
import hmac
import time
import warnings
from io import BytesIO

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

RASTER_MIMES = {"image/jpeg", "image/png", "image/webp"}
Image.MAX_IMAGE_PIXELS = 20_000_000


def process_image(data, mime):
    if mime not in RASTER_MIMES:
        return None, None, []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"} or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Unsupported or animated image")
                if image.width * image.height > 20_000_000 or max(image.size) > 10_000:
                    raise ValueError("Image exceeds decoded pixel limits")
                image.load()
                oriented = ImageOps.exif_transpose(image).convert("RGBA" if "A" in image.getbands() else "RGB")
                width, height = oriented.size
                variants = []
                for bound in sorted({min(width, limit) for limit in (320, 640, 1280, 1920)}):
                    scaled = oriented.copy()
                    scaled.thumbnail((bound, max(1, round(height * bound / width))), Image.Resampling.LANCZOS)
                    output = BytesIO()
                    scaled.save(output, format="WEBP", quality=82, method=4)
                    variants.append((scaled.width, scaled.height, output.getvalue()))
                return width, height, variants
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise HTTPException(
            422, "Upload a valid single-frame JPEG, PNG or WebP within 20 million pixels / 10,000 per side."
        )


def variant_url(settings, id, width):
    expires = int(time.time()) + 900
    signature = hmac.new(settings.secret.encode(), f"{id}:{width}:{expires}".encode(), hashlib.sha256).hexdigest()
    return f"{settings.public_url}/media/{id}/variant/{width}?expires={expires}&signature={signature}"


def variant_metadata(record, settings):
    return [
        {
            "width": v["width"],
            "height": v["height"],
            "size": v["size"],
            "url": variant_url(settings, record.id, v["width"]),
        }
        for v in (record.variants or [])
    ]
