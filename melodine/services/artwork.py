"""Smart artwork cropper.

YouTube thumbnails are 16:9 with black letterbox bars; embedded covers must
be square.  This module detects the real content area, center-crops it to
1:1 and rescales to a high-resolution square (default 1000x1000) before the
bytes are handed to the tagger.
"""

from __future__ import annotations

import io

from PIL import Image, ImageOps

from melodine.core.logging import get_logger

logger = get_logger("artwork")

#: Luma below which a pixel is treated as part of a black bar.
BLACK_THRESHOLD = 18
#: If the detected content box covers less than this fraction of the image,
#: the image is probably a legitimately dark cover - fall back to a plain
#: center crop of the full frame.
MIN_CONTENT_FRACTION = 0.30


def crop_to_square(
    image_bytes: bytes,
    size: int = 1000,
    *,
    threshold: int = BLACK_THRESHOLD,
) -> bytes:
    """Convert arbitrary artwork bytes into a ``size`` x ``size`` JPEG square.

    Never raises: on any decoding problem the original bytes are returned
    unchanged so downloads never fail because of artwork.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = ImageOps.exif_transpose(image).convert("RGB")
    except Exception as exc:
        logger.warning("artwork decode failed: %s", exc)
        return image_bytes

    content = _detect_content(image, threshold)
    square = _center_square(content)
    if square.width < size:
        square = square.resize((size, size), Image.LANCZOS)
    else:
        square = square.resize((size, size), Image.LANCZOS)

    buffer = io.BytesIO()
    square.save(buffer, format="JPEG", quality=92, optimize=True)
    return buffer.getvalue()


def _detect_content(image: Image.Image, threshold: int) -> Image.Image:
    """Crop away black letterbox bars; fall back to the full frame when the
    detected box is implausibly small."""
    width, height = image.size
    grayscale = image.convert("L")
    mask = grayscale.point(lambda pixel: 255 if pixel > threshold else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return image

    box_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    if box_area < MIN_CONTENT_FRACTION * width * height:
        return image
    return image.crop(bbox)


def _center_square(image: Image.Image) -> Image.Image:
    """Center-crop any image to a square using its smaller side."""
    width, height = image.size
    if width == height:
        return image
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    return image.crop((left, top, left + side, top + side))
