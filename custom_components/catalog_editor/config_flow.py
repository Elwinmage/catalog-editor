"""Config flow of the catalog editor: the GitHub OAuth App and the catalogs."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .compat import vol
from .const import (
    CONF_CLIENT_ID,
    CONF_IMAGE_KEY,
    CONF_IMAGE_MODEL,
    CONF_IMAGE_PROVIDER,
    CONF_SECTIONS,
    DOMAIN,
    SECTION_KINDS,
)
from .image_providers import PROVIDERS

#: Option that removes the stored API key
CONF_CLEAR_KEY = "clear_image_key"


def _sections_field(default: list[str]) -> Any:
    """The catalogs to subscribe to: at least one."""
    return (
        vol.Required(CONF_SECTIONS, default=default),
        vol.All(
            SelectSelector(
                SelectSelectorConfig(
                    options=list(SECTION_KINDS),
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                    translation_key=CONF_SECTIONS,
                )
            ),
            vol.Length(min=1),
        ),
    )


class EditorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create the entry."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """The catalogs can be changed afterwards."""
        return EditorOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the client id of the OAuth App and the catalogs, then create."""
        if user_input is not None:
            return self.async_create_entry(
                title="Catalog editor",
                data={CONF_CLIENT_ID: user_input[CONF_CLIENT_ID].strip()},
                options={CONF_SECTIONS: user_input[CONF_SECTIONS]},
            )
        key, validator = _sections_field(list(SECTION_KINDS))
        schema = vol.Schema(
            {
                vol.Required(CONF_CLIENT_ID): vol.All(str, vol.Length(min=1)),
                key: validator,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)


class EditorOptionsFlow(OptionsFlow):
    """Choose the catalogs the editor subscribes to and the image model."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the sections and the image model; the entry reloads on a change.

        The API key is never shown again: leaving it empty keeps the stored one.
        """
        options = self.config_entry.options
        if user_input is not None:
            data: dict[str, Any] = {CONF_SECTIONS: user_input[CONF_SECTIONS]}
            for name in (CONF_IMAGE_PROVIDER, CONF_IMAGE_MODEL):
                if user_input.get(name):
                    data[name] = user_input[name].strip()
            key = (user_input.get(CONF_IMAGE_KEY) or "").strip()
            if not user_input.get(CONF_CLEAR_KEY):
                key = key or options.get(CONF_IMAGE_KEY, "")
            else:
                key = ""
            if key:
                data[CONF_IMAGE_KEY] = key
            return self.async_create_entry(data=data)
        current = options.get(CONF_SECTIONS, list(SECTION_KINDS))
        key, validator = _sections_field(
            [section for section in SECTION_KINDS if section in current]
        )
        provider = options.get(CONF_IMAGE_PROVIDER)
        schema = vol.Schema(
            {
                key: validator,
                vol.Optional(
                    CONF_IMAGE_PROVIDER,
                    description={"suggested_value": provider},
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=list(PROVIDERS), mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Optional(CONF_IMAGE_KEY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Optional(
                    CONF_IMAGE_MODEL,
                    description={"suggested_value": options.get(CONF_IMAGE_MODEL)},
                ): str,
                vol.Optional(CONF_CLEAR_KEY, default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "key_state": "set" if options.get(CONF_IMAGE_KEY) else "not set"
            },
        )
