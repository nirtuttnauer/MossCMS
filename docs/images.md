# Website images

Blog posts and projects may contain `cover: {asset, alt, focalX, focalY, fit}`.
Projects may also contain an ordered `gallery` list with those properties and an
optional Markdown `caption`. `asset` is a durable same-workspace asset ID, never
a signed URL. Alt defaults to empty (decorative); authors should describe meaningful
images. `fit` is `cover` (default) or `contain`; focal coordinates are percentages
0–100, default 50. Renderers clamp coordinates. Existing records need no migration.
Rerunning setup only adds optional fields and retains custom fields and content.

Raster processing accepts JPEG, PNG and WebP, at most 20 million decoded pixels,
10,000 pixels per dimension and the configured upload byte limit. Animated images
and SVG remain original downloads with no raster variants or inline website display.
Invalid raster data is rejected. EXIF orientation is applied and metadata removed
from variants. Original uploads are retained for compatibility. Missing, removed,
non-image or out-of-workspace assets render no image; text remains usable.
Variants are bounded widths 320, 640, 1280 and 1920, without upscaling, encoded WebP.
They share the original asset's access rules and deletion lifecycle. Gallery order
is the stored list order. Asset resolution is limited to 50 visible image IDs per entry.
