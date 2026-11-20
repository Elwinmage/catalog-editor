"""Config flow: the OAuth App and the catalogs; options: the catalogs."""

from __future__ import annotations

import pytest
from conftest import serve, setup_editor
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from custom_components.catalog_editor.const import DOMAIN


async def test_flow(hass, aioclient_mock):
    serve(aioclient_mock)
    form = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert form["type"] is FlowResultType.FORM and form["step_id"] == "user"
    done = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {"client_id": " cid ", "sections": ["equipment", "water_tests"]},
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert done["data"] == {"client_id": "cid"}
    assert done["options"] == {"sections": ["equipment", "water_tests"]}
    await hass.async_block_till_done(wait_background_tasks=True)
    again = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert again["type"] is FlowResultType.ABORT


async def test_flow_needs_a_catalog(hass):
    form = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            form["flow_id"], {"client_id": "cid", "sections": []}
        )


async def test_options_change_the_subscriptions(hass, aioclient_mock):
    entry = await setup_editor(hass, aioclient_mock)
    assert list(hass.data[DOMAIN].sources) == [
        "equipment",
        "supplements",
        "parameters",
        "water_tests",
        "trees",
        "objects",
        "pond_fish",
        "fish",
        "corals",
        "plants",
        "invertebrates",
    ]
    form = await hass.config_entries.options.async_init(entry.entry_id)
    assert form["type"] is FlowResultType.FORM and form["step_id"] == "init"
    done = await hass.config_entries.options.async_configure(
        form["flow_id"], {"sections": ["parameters", "equipment"]}
    )
    assert done["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done(wait_background_tasks=True)
    # Reloaded with the chosen catalogs, in the order of the catalog
    assert list(hass.data[DOMAIN].sources) == ["equipment", "parameters"]
