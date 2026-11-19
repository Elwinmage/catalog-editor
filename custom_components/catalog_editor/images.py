"""Visuals of the catalog: any picture in, `image.webp` and `thumb.webp` out.

The catalog wants a transparent background, about 512 px on the long side and
under 300 KB for the visual, 128 px and under 40 KB for the thumbnail.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import cast

from PIL import Image, UnidentifiedImageError

from .rules import ASSET_FILES

IMAGE_SIDE = 512
THUMB_SIDE = 128
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 25_000_000
FORMATS = ("PNG", "JPEG", "WEBP")
QUALITIES = (90, 80, 70, 60, 50, 40)
#: Each retry shrinks the picture by this factor when no quality is low enough
SHRINK = 0.8
MAX_SHRINKS = 4


class ImageError(Exception):
    """A picture that cannot be turned into a visual; the message is a code."""


@dataclass(frozen=True)
class Visual:
    """A processed picture."""

    image: bytes
    thumb: bytes
    has_alpha: bool
    size: tuple[int, int]


def _encode(picture: Image.Image, limit: int) -> bytes:
    for _ in range(MAX_SHRINKS + 1):
        for quality in QUALITIES:
            buffer = io.BytesIO()
            picture.save(buffer, "WEBP", quality=quality, method=6)
            if buffer.tell() <= limit:
                return buffer.getvalue()
        width, height = picture.size
        picture = picture.resize(
            (max(1, round(width * SHRINK)), max(1, round(height * SHRINK))),
            Image.Resampling.LANCZOS,
        )
    raise ImageError("cannot_fit")


def _fit(picture: Image.Image, side: int) -> Image.Image:
    fitted = picture.copy()
    fitted.thumbnail((side, side), Image.Resampling.LANCZOS)  # never enlarges
    return fitted


def process_image(blob: bytes) -> Visual:
    """Normalise an uploaded picture (PNG, JPEG or WebP). Raises ImageError."""
    if len(blob) > MAX_UPLOAD_BYTES:
        raise ImageError("too_big")
    try:
        with Image.open(io.BytesIO(blob), formats=FORMATS) as source:
            if source.width * source.height > MAX_PIXELS:
                raise ImageError("too_many_pixels")
            source.load()
            picture = source.convert("RGBA")
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ) as err:
        raise ImageError("unreadable") from err
    lowest = cast("tuple[int, int]", picture.getchannel("A").getextrema())[0]
    has_alpha = lowest < 255
    image = _fit(picture, IMAGE_SIDE)
    thumb = _fit(picture, THUMB_SIDE)
    return Visual(
        _encode(image, ASSET_FILES["image.webp"]),
        _encode(thumb, ASSET_FILES["thumb.webp"]),
        has_alpha,
        image.size,
    )
