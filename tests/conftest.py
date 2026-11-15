"""Fixtures: releases served by a mocked GitHub, and a fake catalog provider."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.reeftech_catalog_editor import const
from custom_components.reeftech_catalog_editor.catalog_pack import Layer
from custom_components.reeftech_catalog_editor.catalog_runtime import DATA_KEY
from custom_components.reeftech_catalog_editor.const import DOMAIN

SCHEMAS = Path(__file__).parent / "fixtures" / "schema"
BASE = "https://github.com/Elwinmage/reeftech-catalog/releases/download"
KINDS = {
    "equipment": ("task", "category", "item"),
    "supplements": ("supplement",),
    "parameters": ("parameter",),
}


def schema_zip(section: str, extra: dict[str, bytes] | None = None) -> bytes:
    """The schema.zip of a release, built from the schemas of the catalog."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for kind in ("common", *KINDS[section]):
            name = f"{kind}.schema.json"
            archive.writestr(name, (SCHEMAS / name).read_bytes())
        for name, blob in (extra or {}).items():
            archive.writestr(name, blob)
    return buffer.getvalue()


def manifest_of(
    section: str, blob: bytes, version: str = "2026.11.0"
) -> dict[str, Any]:
    return {
        "format": 1,
        "section": section,
        "version": version,
        "entries": {},
        "schema": {
            "archive": f"{section}-{version}/schema.zip",
            "sha256": hashlib.sha256(blob).hexdigest(),
            "size": len(blob),
            "since": version,
        },
    }


def serve(aioclient_mock, sections=("equipment", "supplements", "parameters")) -> None:
    """Serve the manifest and the schemas of the sections."""
    aioclient_mock.clear_requests()
    for section in sections:
        blob = schema_zip(section)
        manifest = manifest_of(section, blob)
        aioclient_mock.get(
            f"{BASE}/{section}-latest/manifest.json", text=json.dumps(manifest)
        )
        aioclient_mock.get(f"{BASE}/{manifest['schema']['archive']}", content=blob)


def interval(default: int = 1) -> dict[str, Any]:
    return {
        "type": "interval",
        "unit": "months",
        "every": {"default": default, "min": 1, "max": 12},
    }


@dataclass
class Spec:
    domain: str
    section: str


class FakeUpdater:
    """What the editor needs from a consumer of the catalog."""

    def __init__(self, domain: str, section: str, root: Path, view: dict) -> None:
        self.spec = Spec(domain, section)
        self.view = view
        self.root = root

    async def async_view(self, refresh: bool = False) -> dict[str, Any]:
        return self.view

    def _layers(self) -> list[Layer]:
        return [Layer("pack", self.root, f"/{self.spec.domain}_catalog/pack", "1")]


def equipment_view(pack: Path) -> dict[str, Any]:
    """A small merged view; the Eheim item has a visual in `pack`."""
    folder = pack / "items/eheim-200"
    folder.mkdir(parents=True)
    (folder / "image.png").write_bytes(b"PNGDATA")
    (folder / "thumb.webp").write_bytes(b"THUMBDATA")
    url = "/fake_catalog/pack/items/eheim-200"
    return {
        "tasks": {
            "clean": {"name": {"en": "Clean"}, "schedule": interval(3)},
        },
        "categories": {
            "heater": {
                "name": {"en": "Heater"},
                "scopes": ["aquarium"],
                "source": "pack",
                "image": None,
                "thumb": None,
            }
        },
        "items": {
            "eheim-200": {
                "category": "heater",
                "brand": "Eheim",
                "model": "200",
                "scopes": ["aquarium"],  # inherited from the category by the view
                "source": "pack",
                "image": f"{url}/image.png?v=1",
                "thumb": f"{url}/thumb.webp?v=1",
            }
        },
    }


SUPPLEMENT = {
    "brand": "B",
    "name": "KH",
    "fullname": "B - KH",
    "uid": "u1",
    "kind": "kh",
    "verified": False,
}


@pytest.fixture(autouse=True)
def auto_enable(enable_custom_integrations, hass: HomeAssistant, tmp_path: Path):
    """Load the integration, with a config folder of its own per test."""
    hass.config.config_dir = str(tmp_path / "config")


@pytest.fixture
def pack(tmp_path: Path) -> Path:
    return tmp_path / "pack"


@pytest.fixture
def providers(hass: HomeAssistant, pack: Path, monkeypatch) -> dict[str, FakeUpdater]:
    """A fake integration reading each section (registered like the real ones)."""
    monkeypatch.setitem(const.PROVIDERS, "equipment", ("fake",))
    monkeypatch.setitem(const.PROVIDERS, "supplements", ("fake_sup",))
    monkeypatch.setitem(const.PROVIDERS, "parameters", ("fake_par",))
    fakes = {
        "equipment": FakeUpdater("fake", "equipment", pack, equipment_view(pack)),
        "supplements": FakeUpdater(
            "fake_sup", "supplements", pack, {"items": {"kh": {**SUPPLEMENT}}}
        ),
        "parameters": FakeUpdater(
            "fake_par",
            "parameters",
            pack,
            {
                "items": {
                    "kh": {
                        "name": {"en": "KH"},
                        "symbol": "KH",
                        "category": "alkalinity",
                        "unit": "dkh",
                        "effect_parameter": "kh",
                    }
                }
            },
        ),
    }
    registry = hass.data.setdefault(DATA_KEY, {})
    for fake in fakes.values():
        registry[fake.spec.domain] = fake
    return fakes


async def setup_editor(hass: HomeAssistant, aioclient_mock, release: bool = True):
    if release:
        serve(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, entry_id="editor")
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return entry
