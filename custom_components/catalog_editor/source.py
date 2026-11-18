"""What the editor reads of a section: the shared pack and the user layer.

The editor does not depend on an integration reading the catalog. It takes the
shared pack of every section (see reeftech-catalog, doc/consumers.md), which it
downloads and keeps up to date like any other holder, and merges it with the
user layer it writes itself. A section whose pack is not downloaded yet (offline
at the first start, say) is not editable until it is.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback

from .catalog_pack import Layer, Manifest, build_view
from .catalog_runtime import SharedPack, async_acquire_pack, async_release_pack
from .const import DOMAIN, USER_URL


class SectionSource:
    """The merged catalog of a section as the editor sees it."""

    def __init__(
        self, hass: HomeAssistant, section: str, pack: SharedPack, user_root: Path
    ) -> None:
        """Follow the shared pack of the section and read the user layer folder."""
        self.hass = hass
        self.section = section
        self.pack = pack
        self.user_root = user_root
        self.user_url = f"{USER_URL}/{section}"
        #: Counts the changes of the user layer; stamps its visuals so that a
        #: replaced picture is fetched again
        self.user_revision = 0
        self._view: dict[str, Any] | None = None
        self._seen: Manifest | None = pack.installed
        self._unsub: CALLBACK_TYPE | None = pack.async_add_listener(
            self._on_pack_changed
        )

    @property
    def installed(self) -> Manifest | None:
        """Manifest of the downloaded pack, None while there is none."""
        return self.pack.installed

    def layers(self) -> list[Layer]:
        """The folders the view is read from, least specific first."""
        layers = []
        installed = self.pack.installed
        if installed is not None:
            layers.append(
                Layer("pack", self.pack.root, self.pack.url, installed.version)
            )
        layers.append(
            Layer("user", self.user_root, self.user_url, f"u{self.user_revision}")
        )
        return layers

    async def async_view(self, refresh: bool = False) -> dict[str, Any]:
        """Merged catalog (pack < user layer), re-read on demand."""
        view = self._view
        if view is None or refresh:
            view = await self.hass.async_add_executor_job(
                build_view, self.layers(), self.section
            )
            self._view = view
        return view

    async def async_reload(self) -> None:
        """The pack or the user layer changed: read them again."""
        await self.async_view(refresh=True)

    @callback
    def _on_pack_changed(self) -> None:
        """A release was installed (by anyone holding the pack): reload the view."""
        installed = self.pack.installed
        if installed is self._seen:
            return
        self._seen = installed
        self.hass.async_create_background_task(
            self.async_reload(), f"{DOMAIN} {self.section} reload"
        )

    @callback
    def async_stop(self) -> None:
        """Stop following the pack and give it back."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        async_release_pack(self.hass, self.section, DOMAIN)


async def async_start_sources(
    hass: HomeAssistant, roots: dict[str, Path]
) -> dict[str, SectionSource]:
    """Take the shared pack of each section of `roots` (its user layer folder)."""
    sources = {}
    for section in roots:
        pack = await async_acquire_pack(hass, section, DOMAIN, auto=True)
        sources[section] = SectionSource(hass, section, pack, roots[section])
    return sources
