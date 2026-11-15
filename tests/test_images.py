"""Processing of uploaded pictures."""

from __future__ import annotations

import io
import os

import pytest
from PIL import Image

from custom_components.reeftech_catalog_editor import images


def encode(picture: Image.Image, fmt: str) -> bytes:
    buffer = io.BytesIO()
    picture.save(buffer, fmt)
    return buffer.getvalue()


def test_png_with_transparency():
    picture = Image.new("RGBA", (1024, 600), (255, 0, 0, 0))
    picture.paste((0, 128, 255, 255), (100, 100, 900, 500))
    visual = images.process_image(encode(picture, "PNG"))
    assert visual.has_alpha and visual.size == (512, 300)
    assert len(visual.image) <= 300_000 and len(visual.thumb) <= 40_000
    thumb = Image.open(io.BytesIO(visual.thumb))
    assert thumb.format == "WEBP" and max(thumb.size) == 128


def test_jpeg_has_no_transparency_and_small_pictures_are_not_enlarged():
    visual = images.process_image(encode(Image.new("RGB", (60, 40), "white"), "JPEG"))
    assert visual.has_alpha is False and visual.size == (60, 40)


def test_noisy_picture_is_compressed_to_fit():
    noise = Image.frombytes("RGB", (512, 512), os.urandom(512 * 512 * 3))
    visual = images.process_image(encode(noise, "PNG"))
    assert len(visual.image) <= 300_000


def test_refused_pictures(monkeypatch):
    with pytest.raises(images.ImageError, match="unreadable"):
        images.process_image(b"not a picture")
    with pytest.raises(images.ImageError, match="unreadable"):
        images.process_image(encode(Image.new("RGB", (4, 4)), "BMP"))
    monkeypatch.setattr(images, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(images.ImageError, match="too_big"):
        images.process_image(encode(Image.new("RGB", (40, 40)), "PNG"))
    monkeypatch.setattr(images, "MAX_UPLOAD_BYTES", 8 * 1024 * 1024)
    monkeypatch.setattr(images, "MAX_PIXELS", 100)
    with pytest.raises(images.ImageError, match="too_many_pixels"):
        images.process_image(encode(Image.new("RGB", (40, 40)), "PNG"))


def test_cannot_fit():
    noise = Image.frombytes("RGBA", (64, 64), os.urandom(64 * 64 * 4))
    with pytest.raises(images.ImageError, match="cannot_fit"):
        images._encode(noise, 10)
