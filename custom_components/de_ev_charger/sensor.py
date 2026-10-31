import json
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    UnitOfElectricPotential, UnitOfElectricCurrent, UnitOfPower, UnitOfTemperature
)
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        EvChargerStateSensor(coordinator, "109", "Work State"),
        EvChargerJsonSensor(coordinator, "102", "Temperature", "t", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, 0.1),
        EvChargerJsonSensor(coordinator, "106", "Control Pilot Voltage", "cp", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, 1.0)
    ]
    
    # 3-Phase Metrics
    for phase in ["L1", "L2", "L3"]:
        entities.append(EvChargerPhaseSensor(coordinator, phase, 0, f"{phase} Voltage", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, 0.1))
        entities.append(EvChargerPhaseSensor(coordinator, phase, 1, f"{phase} Current", SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE, 0.1))
        entities.append(EvChargerPhaseSensor(coordinator, phase, 2, f"{phase} Power", SensorDeviceClass.POWER, UnitOfPower.WATT, 1.0))
        
    async_add_entities(entities)

class EvChargerStateSensor(SensorEntity):
    """Basic String Sensor for Wallbox State."""
    def __init__(self, coordinator, dp, name):
        self.coordinator = coordinator
        self.dp = dp
        self._attr_name = f"dé EV {name}"
        self._attr_unique_id = f"de_ev_{name.lower().replace(' ', '_')}"

    @property
    def native_value(self):
        return self.coordinator.data.get(self.dp)

    @property
    def should_poll(self): return False
    
    async def async_added_to_hass(self):
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

class EvChargerJsonSensor(SensorEntity):
    """Parses root JSON fields from Tuya stringified JSON DPs."""
    def __init__(self, coordinator, dp, name, json_key, device_class, unit, scale):
        self.coordinator = coordinator
        self.dp = dp
        self.json_key = json_key
        self.scale = scale
        self._attr_name = f"dé EV {name}"
        self._attr_unique_id = f"de_ev_{name.lower().replace(' ', '_')}"
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        raw = self.coordinator.data.get(self.dp)
        if raw:
            try:
                data = json.loads(raw)
                val = float(data.get(self.json_key, 0))
                return round(val * self.scale, 2)
            except (ValueError, TypeError, json.JSONDecodeError):
                return None
        return None

    @property
    def should_poll(self): return False
    async def async_added_to_hass(self):
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

class EvChargerPhaseSensor(SensorEntity):
    """Parses Phase Arrays like 'L1': [2240, 0, 0] from DP 102"""
    def __init__(self, coordinator, phase, index, name, device_class, unit, scale):
        self.coordinator = coordinator
        self.phase = phase
        self.index = index
        self.scale = scale
        self._attr_name = f"dé EV {name}"
        self._attr_unique_id = f"de_ev_{name.lower().replace(' ', '_')}"
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        raw = self.coordinator.data.get("102")
        if raw:
            try:
                data = json.loads(raw)
                phase_data = data.get(self.phase, [0, 0, 0])
                val = float(phase_data[self.index])
                return round(val * self.scale, 2)
            except (ValueError, TypeError, json.JSONDecodeError):
                return None
        return None

    @property
    def should_poll(self): return False
    async def async_added_to_hass(self):
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))