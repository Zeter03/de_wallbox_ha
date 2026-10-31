from homeassistant.components.number import NumberEntity
from homeassistant.const import UnitOfElectricCurrent
from .const import DOMAIN
from . import send_tuya_command

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        EvChargerCurrentLimit(hass, entry, coordinator)
    ])

class EvChargerCurrentLimit(NumberEntity):
    def __init__(self, hass, entry, coordinator):
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.dp = "150"
        self._attr_name = "dé EV Charge Current Limit"
        self._attr_unique_id = "de_ev_charge_current_limit"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_native_min_value = 6
        self._attr_native_max_value = 16 # Adjust to 32 if you ever get a 22kW setup
        self._attr_native_step = 1

    @property
    def native_value(self):
        return self.coordinator.data.get(self.dp)

    async def async_set_native_value(self, value: float):
        await send_tuya_command(self.hass, self.entry, self.dp, int(value))
        await self.coordinator.async_request_refresh()

    @property
    def should_poll(self): return False
    async def async_added_to_hass(self):
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))