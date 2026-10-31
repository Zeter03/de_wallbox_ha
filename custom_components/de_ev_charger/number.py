from homeassistant.components.number import NumberEntity
from homeassistant.const import UnitOfElectricCurrent
from .const import DOMAIN
from .entity import DeEvChargerEntity
from . import send_tuya_command

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        EvChargerCurrentLimit(hass, entry, coordinator)
    ])

class EvChargerCurrentLimit(DeEvChargerEntity, NumberEntity):
    def __init__(self, hass, entry, coordinator):
        super().__init__(coordinator, entry)
        self.hass = hass
        self.dp = "150"
        self._attr_name = "Charge Current Limit"
        self._attr_unique_id = "de_ev_charge_current_limit"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_native_min_value = 6
        self._attr_native_max_value = 16
        self._attr_native_step = 1

    @property
    def native_value(self):
        # Safely convert incoming Tuya data (which might be a string) into a float
        val = self.coordinator.data.get(self.dp)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                return None
        return None

    async def async_set_native_value(self, value: float):
        # Convert float back to int for Tuya API
        await send_tuya_command(self.hass, self.entry, self.dp, int(value))
        
        # Instantly refresh data locally to prevent UI bouncing
        self.coordinator.data[self.dp] = int(value)
        self.async_write_ha_state()
        
        await self.coordinator.async_request_refresh()