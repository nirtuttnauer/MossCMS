"""Bounded raster decoding at upload time and signed variant metadata."""

import warnings
from io import BytesIO

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from .media_links import media_url

RASTER_MIMES = {"image/jpeg", "image/png", "image/webp"}
MAX_DECODED_PIXELS = 20_000_000
Image.MAX_IMAGE_PIXELS = MAX_DECODED_PIXELS


def process_image(data, mime):
    if mime not in RASTER_MIMES:
        return None, None, []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"} or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Unsupported or animated image")
                if image.width * image.height > MAX_DECODED_PIXELS or max(image.size) > 10_000:
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


def variant_metadata(record, settings):
    return [
        {
            "width": v["width"],
            "height": v["height"],
            "size": v["size"],
            "url": media_url(settings, record.id, v["width"]),
        }
        for v in (record.variants or [])
    ]
