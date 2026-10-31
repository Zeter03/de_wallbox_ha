import voluptuous as vol
import logging
from homeassistant import config_entries
from .const import DOMAIN, CONF_DEVICE_ID, CONF_LOCAL_KEY, CONF_IP, CONF_VERSION

_LOGGER = logging.getLogger(__name__)

def _scan_devices():
    import tinytuya
    # Scans the local network for UDP broadcasts from Tuya devices (3-second timeout)
    return tinytuya.deviceScan(False, 3)

class DeEvChargerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self.discovered = {}

    async def async_step_user(self, user_input=None):
        """First step: Ask user to auto-discover or enter manually."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["auto", "manual"]
        )

    async def async_step_auto(self, user_input=None):
        """Handle auto-discovery."""
        if user_input is not None:
            # Parse the selection
            selection = user_input[CONF_DEVICE_ID]
            dev_id = selection.split(" ")[0]
            ip = self.discovered[dev_id]["ip"]
            version = self.discovered[dev_id]["version"]
            
            return self.async_create_entry(
                title="dé EV Charger",
                data={
                    CONF_DEVICE_ID: dev_id,
                    CONF_IP: ip,
                    CONF_LOCAL_KEY: user_input[CONF_LOCAL_KEY],
                    CONF_VERSION: version
                }
            )

        # Run the UDP scan in the background
        raw_scan = await self.hass.async_add_executor_job(_scan_devices)
        
        # Format the scan results
        for ip, info in raw_scan.items():
            dev_id = info.get("gwId") or info.get("id")
            if dev_id:
                self.discovered[dev_id] = {
                    "ip": info.get("ip", ip),
                    "version": info.get("version", "3.5")
                }

        # Fallback to manual if nothing is found
        if not self.discovered:
            _LOGGER.warning("No Tuya devices found. Falling back to manual entry.")
            return await self.async_step_manual()

        # Create dropdown list for the UI
        device_list = [f"{did} ({info['ip']})" for did, info in self.discovered.items()]

        schema = vol.Schema({
            vol.Required(CONF_DEVICE_ID): vol.In(device_list),
            vol.Required(CONF_LOCAL_KEY): str,
        })
        
        return self.async_show_form(step_id="auto", data_schema=schema)

    async def async_step_manual(self, user_input=None):
        """Handle manual IP/ID entry."""
        if user_input is not None:
            return self.async_create_entry(title="dé EV Charger", data=user_input)

        schema = vol.Schema({
            vol.Required(CONF_DEVICE_ID): str,
            vol.Required(CONF_IP): str,
            vol.Required(CONF_LOCAL_KEY): str,
            vol.Optional(CONF_VERSION, default="3.5"): str,
        })
        return self.async_show_form(step_id="manual", data_schema=schema)