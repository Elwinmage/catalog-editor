"""ReefTech catalog editor: add and edit entries of the ReefTech catalogs.

The entries are written in the user layer shared by the integrations reading
the catalog (see reeftech-catalog, doc/consumers.md), so they are usable at
once; the contribution to the catalog itself (a pull request) comes on top.
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import EditorData, async_register_api
from .const import CONF_CLIENT_ID, DOMAIN, SECTION_KINDS
from .contributions import Contributions
from .frontend import async_register_card, async_register_user_paths
from .schemas import SchemaStore
from .source import async_start_sources
from .storage import UserCatalog


def _make_folders(folders: list[Path]) -> None:
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)


async def _async_refresh_schemas(data: EditorData) -> None:
    for section in SECTION_KINDS:
        await data.schemas.async_refresh(section)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Take the catalogs, load the schemas on disk, register the API.

    The catalogs and the schemas are refreshed in the background.
    """
    contributions = Contributions(hass)
    await contributions.async_load()
    catalog = UserCatalog(hass.config.path)
    roots = {section: catalog.root(section) for section in SECTION_KINDS}
    await hass.async_add_executor_job(_make_folders, list(roots.values()))
    data = EditorData(
        SchemaStore(hass),
        catalog,
        contributions,
        entry.data[CONF_CLIENT_ID],
        sources=await async_start_sources(hass, roots),
    )
    await data.schemas.async_load()
    hass.data[DOMAIN] = data
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
