"""Serve the card and load it in the interface."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

CARD_FILE = Path(__file__).parent / "frontend" / "reeftech-catalog-editor-card.js"
CARD_URL = f"/{DOMAIN}/reeftech-catalog-editor-card.js"


async def async_register_card(hass: HomeAssistant) -> None:
    """Make the card available as `type: custom:reeftech-catalog-editor-card`."""
    if getattr(hass, "http", None) is None:
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_FILE), False)]
    )
    if "frontend" not in hass.config.components:
        return
    from homeassistant.components.frontend import add_extra_js_url

    version = (await hass.async_add_executor_job(CARD_FILE.stat)).st_mtime_ns
    add_extra_js_url(hass, f"{CARD_URL}?v={version}")
