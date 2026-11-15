"""Config flow of the catalog editor: the GitHub OAuth App to sign in with."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .compat import vol
from .const import CONF_CLIENT_ID, DOMAIN


class EditorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create the entry."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the client id of the OAuth App, then create the entry."""
        if user_input is not None:
            return self.async_create_entry(
                title="ReefTech catalog editor",
                data={CONF_CLIENT_ID: user_input[CONF_CLIENT_ID].strip()},
            )
        schema = vol.Schema(
            {vol.Required(CONF_CLIENT_ID): vol.All(str, vol.Length(min=1))}
        )
        return self.async_show_form(step_id="user", data_schema=schema)
