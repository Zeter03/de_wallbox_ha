import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_DEVICE_ID, CONF_LOCAL_KEY, CONF_IP, CONF_VERSION

class DeEvChargerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for dé EV Charger."""
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="dé EV Charger", data=user_input)

        data_schema = vol.Schema({
            vol.Required(CONF_DEVICE_ID): str,
            vol.Required(CONF_IP): str,
            vol.Required(CONF_LOCAL_KEY): str,
            vol.Optional(CONF_VERSION, default="3.5"): str,
        })

        return self.async_show_form(step_id="user", data_schema=data_schema)