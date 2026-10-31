import voluptuous as vol
import logging
from homeassistant import config_entries
from .const import DOMAIN, CONF_DEVICE_ID, CONF_LOCAL_KEY, CONF_IP, CONF_VERSION

_LOGGER = logging.getLogger(__name__)

def _scan_devices():
    import tinytuya
    # Scans the local network for 5 seconds. maxretry=5, poll=True
    return tinytuya.deviceScan(False, 5, False)

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
            dev_id = user_input[CONF_DEVICE_ID]
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
            return self.async_show_form(
                step_id="manual", 
                errors={"base": "no_devices"},
                data_schema=self._get_manual_schema()
            )

        # Create a dictionary for the dropdown menu: { "device_id": "Device_ID (192.168.x.x)" }
        device_map = {did: f"{did} ({info['ip']})" for did, info in self.discovered.items()}

        schema = vol.Schema({
            vol.Required(CONF_DEVICE_ID): vol.In(device_map),
            vol.Required(CONF_LOCAL_KEY): str,
        })
        
        return self.async_show_form(step_id="auto", data_schema=schema)

    async def async_step_manual(self, user_input=None):
        """Handle manual IP/ID entry."""
        if user_input is not None:
            return self.async_create_entry(title="dé EV Charger", data=user_input)

        return self.async_show_form(step_id="manual", data_schema=self._get_manual_schema())

    def _get_manual_schema(self):
        return vol.Schema({
            vol.Required(CONF_DEVICE_ID): str,
            vol.Required(CONF_IP): str,
            vol.Required(CONF_LOCAL_KEY): str,
            vol.Optional(CONF_VERSION, default="3.5"): str,
        })