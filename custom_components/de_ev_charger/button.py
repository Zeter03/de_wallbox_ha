from homeassistant.components.button import ButtonEntity
from .const import DOMAIN
from .entity import DeEvChargerEntity
from . import send_tuya_command

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    async_add_entities([
        EvChargerRebootButton(hass, entry, coordinator)
    ])

class EvChargerRebootButton(DeEvChargerEntity, ButtonEntity):
    """Button to restart the EV Charger."""
    
    def __init__(self, hass, entry, coordinator):
        super().__init__(coordinator, entry)
        self.hass = hass
        self.dp = "142"
        self._attr_name = "Reboot Charger"
        self._attr_unique_id = "de_ev_button_reboot"
        self._attr_icon = "mdi:restart"

    async def async_press(self) -> None:
        """Handle the button press to reboot the charger."""
        await send_tuya_command(self.hass, self.entry, self.dp, True)