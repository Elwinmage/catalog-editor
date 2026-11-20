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

from custom_components.catalog_editor.catalog_pack import Layer
from custom_components.catalog_editor.const import DOMAIN

SCHEMAS = Path(__file__).parent / "fixtures" / "schema"
HOUSE_SCHEMAS = Path(__file__).parent / "fixtures" / "house_schema"
REEFTANK_SCHEMAS = Path(__file__).parent / "fixtures" / "reeftank_schema"
BASE = "https://github.com/Elwinmage/reeftech-catalog/releases/download"
HOUSE_BASE = "https://github.com/Elwinmage/house-catalog/releases/download"
REEFTANK_RELEASES = "https://github.com/Elwinmage/reeftank-catalog/releases"
KINDS = {
    "equipment": ("item", "category", "task"),
    "supplements": ("supplement",),
    "parameters": ("parameter",),
    "water_tests": ("water_test",),
    "trees": ("tree",),
    "objects": ("object",),
    "pond_fish": ("pond_fish",),
    "fish": ("fish",),
    "corals": ("coral",),
    "plants": ("plant",),
    "invertebrates": ("invertebrate",),
}
#: Sections published by house-catalog, with schemas of their own
HOUSE = ("trees", "objects", "pond_fish")
#: Sections published by reeftank-catalog: one release for all of them
REEFTANK = ("fish", "corals", "plants", "invertebrates")
REEFTANK_VERSION = "2026.11.0"


def base_of(section: str) -> str:
    """Where the releases of a section are downloaded from."""
    return HOUSE_BASE if section in HOUSE else BASE


def schema_zip(section: str, extra: dict[str, bytes] | None = None) -> bytes:
    """The schema.zip of a release, built from the schemas of the catalog."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        folder = (
            HOUSE_SCHEMAS
            if section in HOUSE
            else REEFTANK_SCHEMAS
            if section in REEFTANK
            else SCHEMAS
        )
        # reeftank-catalog has one schema archive for every species
        kinds = (
            ("fish", "coral", "plant", "invertebrate")
            if section in REEFTANK
            else KINDS[section]
        )
        for kind in ("common", *kinds):
            name = f"{kind}.schema.json"
            archive.writestr(name, (folder / name).read_bytes())
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


def reeftank_manifest(
    blob: bytes, entries: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The manifest of a reeftank-catalog release (one for every species)."""
    return {
        "format": 1,
        "version": REEFTANK_VERSION,
        "min_integration": "0.1.0",
        "notes": "## release",
        "entries": entries or {},
        "schema": {
            "sha256": hashlib.sha256(blob).hexdigest(),
            "size": len(blob),
            "file": "schema.zip",
        },
    }


def serve(aioclient_mock, sections=tuple(KINDS), reeftank_entries=None) -> None:
    """Serve the manifest and the schemas of the sections, each from its repository."""
    aioclient_mock.clear_requests()
    if any(section in REEFTANK for section in sections):
        blob = schema_zip("fish")
        aioclient_mock.get(
            f"{REEFTANK_RELEASES}/latest/download/manifest.json",
            text=json.dumps(reeftank_manifest(blob, reeftank_entries)),
        )
        aioclient_mock.get(
            f"{REEFTANK_RELEASES}/download/{REEFTANK_VERSION}/schema.zip", content=blob
        )
    for section in sections:
        if section in REEFTANK:
            continue
        blob = schema_zip(section)
        manifest = manifest_of(section, blob)
        base = base_of(section)
        aioclient_mock.get(
            f"{base}/{section}-latest/manifest.json", text=json.dumps(manifest)
        )
        aioclient_mock.get(f"{base}/{manifest['schema']['archive']}", content=blob)


def interval(default: int = 1) -> dict[str, Any]:
    return {
        "type": "interval",
        "unit": "months",
        "every": {"default": default, "min": 1, "max": 12},
    }


@dataclass
class FakePack:
    installed: object | None = None
    last_error: str | None = None


class FakeSource:
    """What the editor needs of the merged catalog of a section."""

    def __init__(self, name: str, section: str, root: Path, view: dict) -> None:
        self.section = section
        self.view = view
        self.root = root
        self.name = name
        self.user_revision = 0
        self.pack = FakePack(installed=object())
        self.real: Any = None  # the real source this one replaces, still to stop

    def async_stop(self) -> None:
        """Give back the packs held by the real source standing behind."""
        if self.real is not None:
            self.real.async_stop()

    @property
    def installed(self):
        return self.pack.installed

    async def async_view(self, refresh: bool = False) -> dict[str, Any]:
        return self.view

    async def async_reload(self) -> None:
        """Nothing to read again: the view is a given."""

    def layers(self) -> list[Layer]:
        return [Layer("pack", self.root, f"/{self.name}_catalog/pack", "1")]


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


WATER_TEST = {
    "brand": "Red Sea",
    "name": "Kit",
    "tests": [
        {
            "parameter": "kh",
            "unit": "dkh",
            "method": "titration",
            "table": {
                "amount_unit": "ml",
                "points": [{"amount": 0.5, "value": 12}, {"amount": 1, "value": 6}],
            },
        }
    ],
    "verified": True,
    "source": "manual",
}


@pytest.fixture(autouse=True)
def auto_enable(enable_custom_integrations, hass: HomeAssistant, tmp_path: Path):
    """Load the integration, with a config folder of its own per test."""
    hass.config.config_dir = str(tmp_path / "config")


@pytest.fixture
def pack(tmp_path: Path) -> Path:
    """Where the fake sources read their pack (and the tests drop released copies)."""
    return tmp_path / "pack"


@pytest.fixture
def providers(hass: HomeAssistant, pack: Path, monkeypatch) -> dict[str, FakeSource]:
    """A fake merged catalog for each section, put in the editor once it is set up."""
    fakes = {
        "equipment": FakeSource("fake", "equipment", pack, equipment_view(pack)),
        "supplements": FakeSource(
            "fake_sup", "supplements", pack, {"items": {"kh": {**SUPPLEMENT}}}
        ),
        "parameters": FakeSource(
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
        "water_tests": FakeSource(
            "fake_wt", "water_tests", pack, {"items": {"rs": {**WATER_TEST}}}
        ),
    }
    hass.data["_test_fakes"] = fakes
    return fakes


async def setup_editor(hass: HomeAssistant, aioclient_mock, release: bool = True):
    if release:
        serve(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, entry_id="editor", data={"client_id": "cid"})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    # Fakes stand in for the real sources, which are tested on their own
    sources = hass.data[DOMAIN].sources
    for section, fake in hass.data.get("_test_fakes", {}).items():
        fake.real = sources.get(section)
        sources[section] = fake
    return entry
