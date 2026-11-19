"""Config flow and Options flow for OpenBeken OTA Updater."""
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .const import (
    CONF_INCLUDE_BATTERY_DEVICES,
    DEFAULT_INCLUDE_BATTERY_DEVICES,
    DOMAIN,
)


class OpenBekenOTAConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenBeken OTA Updater."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return OpenBekenOTAOptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title="OpenBeken OTA",
                data={},
                options={
                    CONF_INCLUDE_BATTERY_DEVICES: user_input.get(
                        CONF_INCLUDE_BATTERY_DEVICES, DEFAULT_INCLUDE_BATTERY_DEVICES
                    )
                },
            )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_INCLUDE_BATTERY_DEVICES,
                    default=DEFAULT_INCLUDE_BATTERY_DEVICES,
                ): bool,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)


class OpenBekenOTAOptionsFlowHandler(OptionsFlow):
    """Handle options for OpenBeken OTA Updater."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_include = self.config_entry.options.get(
            CONF_INCLUDE_BATTERY_DEVICES, DEFAULT_INCLUDE_BATTERY_DEVICES
        )
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_INCLUDE_BATTERY_DEVICES,
                    default=current_include,
                ): bool,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
