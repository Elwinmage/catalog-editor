"""Config flow of the catalog editor: one entry, nothing to ask."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class EditorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create the entry."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm, then create the entry."""
        if user_input is not None:
            return self.async_create_entry(title="ReefTech catalog editor", data={})
        return self.async_show_form(step_id="user")
