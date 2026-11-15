"""ReefTech catalog editor: add and edit entries of the ReefTech catalogs.

The entries are written in the user layer shared by the integrations reading
the catalog (see reeftech-catalog, doc/consumers.md), so they are usable at
once; the contribution to the catalog itself (a pull request) comes on top.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import EditorData, async_register_api
from .const import CONF_CLIENT_ID, DOMAIN, SECTION_KINDS
from .contributions import Contributions
from .frontend import async_register_card
from .schemas import SchemaStore
from .storage import UserCatalog


async def _async_refresh_schemas(data: EditorData) -> None:
    for section in SECTION_KINDS:
        await data.schemas.async_refresh(section)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load the schemas on disk, register the API, refresh the schemas in the background."""
    contributions = Contributions(hass)
    await contributions.async_load()
    data = EditorData(
        SchemaStore(hass),
        UserCatalog(hass.config.path),
        contributions,
        entry.data[CONF_CLIENT_ID],
    )
    await data.schemas.async_load()
    hass.data[DOMAIN] = data
    async_register_api(hass)
    if not hass.data.get(f"{DOMAIN}_card"):
        hass.data[f"{DOMAIN}_card"] = True
        await async_register_card(hass)
    # Offline or GitHub down: what is on disk stays usable
    hass.async_create_background_task(
        _async_refresh_schemas(data), f"{DOMAIN} schemas refresh"
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Forget the run-time state; the commands answer `not_loaded` meanwhile."""
    hass.data.pop(DOMAIN, None)
    return True
