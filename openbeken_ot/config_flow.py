"""Config flow for OpenBeken OTA integration."""
from homeassistant import config_entries
from .const import DOMAIN

class OpenBekenOTAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenBeken OTA."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="OpenBeken OTA", data={})

        return self.async_show_form(step_id="user")