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
        return {
            "identifiers": {(DOMAIN, self.entry.data[CONF_DEVICE_ID])},
            "name": "dé EV Charger",
            "manufacturer": "Tuya / dé",
            "model": "11kW EV Wallbox",
            "sw_version": "v" + str(self.entry.data.get("version", "3.5"))
        }

    @property
    def should_poll(self):
        return False

    async def async_added_to_hass(self):
        """Subscribe to coordinator updates."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )