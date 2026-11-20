"""Visuals of the catalog: any picture in, `image.webp` and `thumb.webp` out.

The catalog wants a transparent background, about 512 px on the long side and
under 300 KB for the visual, 128 px and under 40 KB for the thumbnail.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import cast

import numpy as np
from PIL import Image, UnidentifiedImageError

from .reeftank_catalog_still import Still, build_still, check_photo, detect_key
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


# -- photos of a species ------------------------------------------------------------
#
# The photo an image model (or the contributor) gives is not a visual of the
# catalog: it is the source of the degraded atlas, never kept in the catalog.

MAX_PHOTO_BYTES = 12 * 1024 * 1024
PREVIEW_SIDE = 480
PREVIEW_QUALITY = 70


@dataclass(frozen=True)
class Photo:
    """A photo waiting to become an atlas."""

    blob: bytes
    size: tuple[int, int]
    #: Why it is not fit (see reeftank_catalog_still.check_photo); empty when fit
    problems: tuple[str, ...]
    #: Background colour detected in its corners (magenta, green or None)
    key: str | None
    #: Where it comes from: `type` (photo or ai-generated) and, for a model, `model`
    source: dict[str, str]


def _open(blob: bytes) -> Image.Image:
    """The picture of a blob (RGB); raises ImageError."""
    if len(blob) > MAX_PHOTO_BYTES:
        raise ImageError("too_big")
    try:
        with Image.open(io.BytesIO(blob), formats=FORMATS) as source:
            if source.width * source.height > MAX_PIXELS:
                raise ImageError("too_many_pixels")
            source.load()
            return source.convert("RGB")
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ) as err:
        raise ImageError("unreadable") from err


def inspect_photo(blob: bytes, source: dict[str, str], key: str | None = None) -> Photo:
    """Read and check a photo (`key`: the background asked for, else detected)."""
    picture = _open(blob)
    detected = detect_key(np.asarray(picture, dtype=np.float64))
    return Photo(
        blob,
        picture.size,
        tuple(check_photo(picture, key)),
        key or detected,
        source,
    )


def photo_preview(blob: bytes) -> str:
    """A small `data:` URL of a photo, for the card."""
    small = _open(blob)
    small.thumbnail((PREVIEW_SIDE, PREVIEW_SIDE), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    small.save(buffer, "WEBP", quality=PREVIEW_QUALITY)
    return f"data:image/webp;base64,{base64.b64encode(buffer.getvalue()).decode()}"


def build_degraded(
    photo: Photo, entry_id: str, source: dict[str, str], key: str | None
) -> Still:
    """The degraded atlas of a species made from a photo."""
    return build_still(_open(photo.blob), entry_id, source, key=key or photo.key)


def atlas_preview(still: Still) -> str:
    """The thumbnail of an atlas as a `data:` URL."""
    blob = still.files["thumb.webp"]
    return f"data:image/webp;base64,{base64.b64encode(blob).decode()}"
