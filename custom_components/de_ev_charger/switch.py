from homeassistant.components.switch import SwitchEntity
from .const import DOMAIN
from . import send_tuya_command

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        EvChargerSwitch(hass, entry, coordinator, "140", "Start Charge", "mdi:ev-station"),
        EvChargerSwitch(hass, entry, coordinator, "190", "Plug and Charge", "mdi:power-plug"),
        EvChargerSwitch(hass, entry, coordinator, "110", "Single Phase Mode", "mdi:sine-wave")
    ])

class EvChargerSwitch(SwitchEntity):
    def __init__(self, hass, entry, coordinator, dp, name, icon):
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.dp = dp
        self._attr_name = f"dé EV {name}"
        self._attr_unique_id = f"de_ev_switch_{dp}"
        self._attr_icon = icon

    @property
    def is_on(self):
        return bool(self.coordinator.data.get(self.dp, False))

    async def async_turn_on(self, **kwargs):
        await send_tuya_command(self.hass, self.entry, self.dp, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await send_tuya_command(self.hass, self.entry, self.dp, False)
        await self.coordinator.async_request_refresh()

    @property
    def should_poll(self): return False
    async def async_added_to_hass(self):
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))