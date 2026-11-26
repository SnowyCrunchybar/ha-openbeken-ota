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
    CONF_RETRY_DELAY_MINUTES,
    CONF_RETRY_FAILED_UPDATES,
    DEFAULT_INCLUDE_BATTERY_DEVICES,
    DEFAULT_RETRY_DELAY_MINUTES,
    DEFAULT_RETRY_FAILED_UPDATES,
    DOMAIN,
)


def _build_options_schema(current: dict[str, Any]) -> vol.Schema:
    """Build schema for setup and options flows."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_INCLUDE_BATTERY_DEVICES,
                default=current.get(
                    CONF_INCLUDE_BATTERY_DEVICES, DEFAULT_INCLUDE_BATTERY_DEVICES
                ),
            ): bool,
            vol.Optional(
                CONF_RETRY_FAILED_UPDATES,
                default=current.get(
                    CONF_RETRY_FAILED_UPDATES, DEFAULT_RETRY_FAILED_UPDATES
                ),
            ): bool,
            vol.Optional(
                CONF_RETRY_DELAY_MINUTES,
                default=current.get(
                    CONF_RETRY_DELAY_MINUTES, DEFAULT_RETRY_DELAY_MINUTES
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
        }
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
                    ),
                    CONF_RETRY_FAILED_UPDATES: user_input.get(
                        CONF_RETRY_FAILED_UPDATES, DEFAULT_RETRY_FAILED_UPDATES
                    ),
                    CONF_RETRY_DELAY_MINUTES: user_input.get(
                        CONF_RETRY_DELAY_MINUTES, DEFAULT_RETRY_DELAY_MINUTES
                    ),
                },
            )

        return self.async_show_form(
            step_id="user", data_schema=_build_options_schema({})
        )


class OpenBekenOTAOptionsFlowHandler(OptionsFlow):
    """Handle options for OpenBeken OTA Updater."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_build_options_schema(dict(self.config_entry.options)),
        )
