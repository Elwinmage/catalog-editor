"""Catalog editor: add and edit entries of the catalogs.

The entries are written in the user layer shared by the integrations reading
the catalog (see reeftech-catalog, doc/consumers.md), so they are usable at
once; the contribution to the catalog itself (a pull request) comes on top.
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import EditorData, async_register_api
from .const import (
    CONF_CLIENT_ID,
    CONF_IMAGE_KEY,
    CONF_IMAGE_MODEL,
    CONF_IMAGE_PROVIDER,
    CONF_SECTIONS,
    DOMAIN,
    SECTION_KINDS,
)
from .contributions import Contributions
from .frontend import async_register_card, async_register_user_paths
from .schemas import SchemaStore
from .source import async_start_sources
from .storage import UserCatalog


def _make_folders(folders: list[Path]) -> None:
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)


def subscribed_sections(entry: ConfigEntry) -> list[str]:
    """The sections the editor is subscribed to (all by default), in catalog order."""
    chosen = entry.options.get(CONF_SECTIONS, list(SECTION_KINDS))
    return [section for section in SECTION_KINDS if section in chosen]


async def _async_refresh_schemas(data: EditorData) -> None:
    for section in data.sources:
        await data.schemas.async_refresh(section)


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """The subscriptions changed: start again with the new ones."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Take the catalogs, load the schemas on disk, register the API.

    The catalogs and the schemas are refreshed in the background.
    """
    contributions = Contributions(hass)
    await contributions.async_load()
    catalog = UserCatalog(hass.config.path)
    # The folders and the static paths exist for every section (they are registered
    # once, whatever the subscriptions of a later reload)
    roots = {section: catalog.root(section) for section in SECTION_KINDS}
    await hass.async_add_executor_job(_make_folders, list(roots.values()))
    subscribed = {section: roots[section] for section in subscribed_sections(entry)}
    data = EditorData(
        SchemaStore(hass),
        catalog,
        contributions,
        entry.data[CONF_CLIENT_ID],
        sources=await async_start_sources(hass, subscribed),
        image={
            name: entry.options[name]
            for name in (CONF_IMAGE_PROVIDER, CONF_IMAGE_KEY, CONF_IMAGE_MODEL)
            if entry.options.get(name)
        },
    )
    await data.schemas.async_load()
    hass.data[DOMAIN] = data
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    async_register_api(hass)
    if not hass.data.get(f"{DOMAIN}_card"):
        hass.data[f"{DOMAIN}_card"] = True
        await async_register_card(hass)
        await async_register_user_paths(hass, roots)
    # Offline or GitHub down: what is on disk stays usable
    hass.async_create_background_task(
        _async_refresh_schemas(data), f"{DOMAIN} schemas refresh"
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Give the packs back and forget the run-time state.

    The commands answer `not_loaded` meanwhile.
    """
    data = hass.data.pop(DOMAIN, None)
    if data is not None:
        for source in data.sources.values():
            source.async_stop()
    return True
