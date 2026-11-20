"""Reader of the releases of reeftank-catalog.

The other catalogs publish one release per section (`<section>-latest`, a manifest
that names its section). reeftank-catalog publishes one release for all its
species: `manifest.json` lists `<folder>/<id>` entries, each with its archive in
the same release, and the reeftank integration reads it like that. This client
cuts that manifest into the sections of the editor (fish, corals, plants,
invertebrates) and hands the rest of the editor the manifest of a section as the
catalog client knows it, so that a section is downloaded, shared and merged like
any other. Nothing changes for the integration: the release stays as it is.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import aiohttp

from .catalog_pack import (
    MANIFEST_FILE,
    MANIFEST_FORMAT,
    MAX_ENTRY_BYTES,
    MAX_MANIFEST_BYTES,
    Manifest,
    PackClient,
    PackEntry,
    PackError,
    download,
    parse_manifest,
    verify,
)
from .reeftank_catalog_sections import SECTIONS

_LOGGER = logging.getLogger(__name__)

#: Ids the catalog client accepts
_ID_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
#: Consumer named in the `min_integration` of the manifest
CONSUMER = "reeftank"


def section_manifest(raw: Any, section: str) -> dict[str, Any]:
    """The manifest of one section, in the format of the catalog client.

    From the manifest of a reeftank-catalog release. Archives are named
    `<section>-<version>/<file>`, which `ReeftankPackClient.entry` maps back to the
    release. An entry the client could not take (an id it does not know, an archive
    too big) is left out rather than refusing the whole section.
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("entries"), dict):
        raise PackError("manifest without entries")
    version = raw.get("version")
    kind, (folder, _) = next(iter(SECTIONS[section].items()))
    entries: dict[str, Any] = {}
    for key, item in raw["entries"].items():
        entry_folder, _, entry_id = str(key).partition("/")
        if entry_folder != folder:
            continue
        if (
            not isinstance(item, dict)
            or not _ID_RE.match(entry_id)
            or not isinstance(item.get("size"), int)
            or not 0 < item["size"] <= MAX_ENTRY_BYTES
        ):
            _LOGGER.warning("Entry %s of reeftank-catalog ignored", key)
            continue
        entries[f"{kind}.{entry_id}"] = {
            "kind": kind,
            "sha256": item.get("sha256"),
            "size": item["size"],
            "archive": f"{section}-{version}/{item.get('file')}",
            "since": item.get("version"),
        }
    manifest: dict[str, Any] = {
        "format": MANIFEST_FORMAT,
        "section": section,
        "version": version,
        "notes": raw.get("notes", ""),
        "entries": entries,
    }
    minimum = raw.get("min_integration")
    if isinstance(minimum, str):
        manifest["min_integration"] = {CONSUMER: minimum}
    schema = raw.get("schema")
    if isinstance(schema, dict):
        manifest["schema"] = {
            "sha256": schema.get("sha256"),
            "size": schema.get("size"),
            "archive": f"{section}-{version}/{schema.get('file')}",
            "since": version,
        }
    return manifest


class ReeftankPackClient(PackClient):
    """Reads one section out of the single release of reeftank-catalog."""

    @property
    def manifest_url(self) -> str:
        """The manifest of the latest release."""
        return f"{self.base_url}/latest/download/{MANIFEST_FILE}"

    def release_url(self, version: str) -> str:
        """Page of a release (its tag is its version)."""
        return f"{self.base_url}/tag/{version}"

    async def latest(self) -> Manifest:
        """Manifest of the current release, cut to this section."""
        blob = await download(self._session, self.manifest_url, MAX_MANIFEST_BYTES)
        try:
            raw = json.loads(blob.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as err:
            raise PackError(f"unreadable manifest: {err}") from err
        return parse_manifest(section_manifest(raw, self.section), self.section)

    async def entry(self, entry: PackEntry) -> bytes:
        """Checked archive of an entry (or of the schemas)."""
        folder, _, name = entry.archive.partition("/")
        version = folder.removeprefix(f"{self.section}-")
        blob = await download(
            self._session, f"{self.base_url}/download/{version}/{name}", entry.size
        )
        verify(blob, entry)
        return blob


def pack_client(
    session: aiohttp.ClientSession, section: str, repo: str | None = None
) -> PackClient:
    """The client of a section: the one of reeftank-catalog, or the usual one."""
    cls = ReeftankPackClient if section in SECTIONS else PackClient
    return cls(session, section, repo)
