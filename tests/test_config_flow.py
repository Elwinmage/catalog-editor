"""Config flow: a single confirmation."""

from __future__ import annotations

from conftest import serve
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.reeftech_catalog_editor.const import DOMAIN


async def test_flow(hass, aioclient_mock):
    serve(aioclient_mock)
    form = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert form["type"] is FlowResultType.FORM and form["step_id"] == "user"
    done = await hass.config_entries.flow.async_configure(form["flow_id"], {})
    assert done["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done(wait_background_tasks=True)
    again = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert again["type"] is FlowResultType.ABORT
