"""Config flow for Tsundoku."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
import voluptuous as vol

from .const import DOMAIN


class TsundokuConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Tsundoku config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial setup step."""
        if user_input is not None:
            return self.async_create_entry(title="Tsundoku", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
        )
