import json
from homeassistant.helpers.entity import Entity
from .const import DOMAIN, CONF_DEVICE_ID

class DeEvChargerEntity(Entity):
    """Base entity to group everything under one Device."""
    
    def __init__(self, coordinator, entry):
        self.coordinator = coordinator
        self.entry = entry

    @property
    def device_info(self):
        """Return device information to link this entity to the physical device."""
        fw_version = "Unknown"
        
        # Extract true firmware version from DP 106
        raw_info = self.coordinator.data.get("106")
        if raw_info:
            try:
                data = json.loads(raw_info)
                fw_version = data.get("fv", fw_version)
            except (ValueError, TypeError, json.JSONDecodeError):
                pass

        return {
            "identifiers": {(DOMAIN, self.entry.data[CONF_DEVICE_ID])},
            "name": "dé EV Charger",
            "manufacturer": "dé",
            "model": "EV Charger (Tuya)",
            "sw_version": fw_version,
        }

    @property
    def should_poll(self):
        return False

    async def async_added_to_hass(self):
        """Subscribe to coordinator updates."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )