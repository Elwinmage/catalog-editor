"""JSON Schemas of the catalog, as published by its releases.

Each release of a section carries `schema.zip` (data only). The editor keeps the
latest one of every section in `<config>/reeftech_catalog_editor/schema/<section>/`
and checks drafts against it, so that what it accepts is what the catalog CI
accepts.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from jsonschema import Draft202012Validator

from .catalog_pack import PackClient, PackEntry, PackError, extract_entry
from .catalog_rules import load_validators
from .const import DOMAIN, SECTION_KINDS

_LOGGER = logging.getLogger(__name__)

SHA_FILE = ".sha256"


def _install(blob: bytes, entry: PackEntry, folder: Path) -> None:
    """Replace the schemas of a section by the ones of an archive (all or nothing)."""
    staging = folder.with_name(folder.name + ".new")
    shutil.rmtree(staging, ignore_errors=True)
    extract_entry(blob, entry, staging)
    (staging / SHA_FILE).write_text(entry.sha256, encoding="utf-8")
    old = folder.with_name(folder.name + ".old")
    shutil.rmtree(old, ignore_errors=True)
    if folder.exists():
        folder.rename(old)
    staging.rename(folder)
    shutil.rmtree(old, ignore_errors=True)


def _load(
    folder: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, Draft202012Validator], str | None]:
    """Schemas, validators and archive checksum of an installed folder."""
    schemas = {
        path.name.split(".")[0]: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(folder.glob("*.schema.json"))
    }
    try:
        sha = (folder / SHA_FILE).read_text(encoding="utf-8")
    except OSError:
        sha = None
    return schemas, load_validators(folder), sha


class SchemaStore:
    """The schemas of each section: what is on disk, refreshed from the releases."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Bind to the schema folder of the integration."""
        self.hass = hass
        self.root = Path(hass.config.path(DOMAIN, "schema"))
        self.schemas: dict[str, dict[str, dict[str, Any]]] = {}
        self.validators: dict[str, dict[str, Draft202012Validator]] = {}
        self.checksums: dict[str, str | None] = {}
        self.errors: dict[str, str] = {}

    def folder(self, section: str) -> Path:
        """Where the schemas of a section are kept."""
        return self.root / section

    def ready(self, section: str) -> bool:
        """The schemas of a section are available (on disk or just downloaded)."""
        return section in self.validators

    def schemas_of(self, kind: str) -> dict[str, dict[str, Any]]:
        """The schemas a kind of entry needs (its own and the shared definitions)."""
        section = next(s for s, kinds in SECTION_KINDS.items() if kind in kinds)
        return self.schemas[section]

    def validators_of(self, kind: str) -> dict[str, Draft202012Validator]:
        """The validators of the section a kind of entry belongs to."""
        section = next(s for s, kinds in SECTION_KINDS.items() if kind in kinds)
        return self.validators[section]

    async def async_load(self) -> None:
        """Read what a previous run installed."""
        for section in SECTION_KINDS:
            folder = self.folder(section)
            if await self.hass.async_add_executor_job(folder.is_dir):
                await self._async_read(section)

    async def _async_read(self, section: str) -> None:
        try:
            schemas, validators, sha = await self.hass.async_add_executor_job(
                _load, self.folder(section)
            )
        except (OSError, ValueError, KeyError) as err:
            _LOGGER.warning(
                "Schemas of %s unreadable, downloaded again: %s", section, err
            )
            self.schemas.pop(section, None)
            self.validators.pop(section, None)
            self.checksums.pop(section, None)
            return
        self.schemas[section] = schemas
        self.validators[section] = validators
        self.checksums[section] = sha

    async def async_refresh(self, section: str) -> bool:
        """Download the schemas of the current release when they changed.

        Returns True when the section has usable schemas afterwards. A failure
        (offline, release without schemas) keeps what is installed.
        """
        client = PackClient(async_get_clientsession(self.hass), section)
        try:
            manifest = await client.latest()
            entry = manifest.schema
            if entry is None:
                raise PackError(f"release {manifest.version} has no schemas")
            if self.ready(section) and self.checksums.get(section) == entry.sha256:
                self.errors.pop(section, None)
                return True
            blob = await client.entry(entry)
            await self.hass.async_add_executor_job(
                _install, blob, entry, self.folder(section)
            )
        except (PackError, OSError) as err:
            self.errors[section] = str(err)
            _LOGGER.debug("Schemas of %s not refreshed: %s", section, err)
            return self.ready(section)
        self.errors.pop(section, None)
        await self._async_read(section)
        return self.ready(section)
