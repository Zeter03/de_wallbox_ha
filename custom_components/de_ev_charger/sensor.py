import json
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfElectricPotential, UnitOfElectricCurrent, UnitOfPower, UnitOfTemperature, UnitOfEnergy, UnitOfTime
from .const import DOMAIN
from .entity import DeEvChargerEntity

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = [
        EvChargerStateSensor(coordinator, entry, "109", "Work State"),
        EvChargerStateSensor(coordinator, entry, "104", "Alarm Info"),
        EvChargerStateSensor(coordinator, entry, "111", "Debug Output"),
        
        EvChargerJsonSensor(coordinator, entry, "102", "Temperature", "t", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, 0.1),
        EvChargerJsonSensor(coordinator, entry, "106", "Control Pilot Voltage", "cp", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, 1.0),
        
        # New Session Metrics
        EvChargerJsonSensor(coordinator, entry, "102", "Session Power", "p", SensorDeviceClass.POWER, UnitOfPower.WATT, 1.0),
        EvChargerJsonSensor(coordinator, entry, "102", "Session Energy", "e", SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR, 1.0),
        EvChargerJsonSensor(coordinator, entry, "102", "Session Duration", "d", SensorDeviceClass.DURATION, UnitOfTime.SECONDS, 1.0),
    ]
    
    for phase in ["L1", "L2", "L3"]:
        entities.append(EvChargerPhaseSensor(coordinator, entry, phase, 0, f"{phase} Voltage", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, 0.1))
        entities.append(EvChargerPhaseSensor(coordinator, entry, phase, 1, f"{phase} Current", SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE, 0.1))
        entities.append(EvChargerPhaseSensor(coordinator, entry, phase, 2, f"{phase} Power", SensorDeviceClass.POWER, UnitOfPower.WATT, 1.0))
        
    async_add_entities(entities)

class EvChargerStateSensor(DeEvChargerEntity, SensorEntity):
    def __init__(self, coordinator, entry, dp, name):
        super().__init__(coordinator, entry)
        self.dp = dp
        self._attr_name = f"{name}"
        self._attr_unique_id = f"de_ev_{name.lower().replace(' ', '_')}"

    @property
    def native_value(self):
        val = self.coordinator.data.get(self.dp)
        # Handle empty JSON strings correctly
        if val == "{}" or val == "":
            return "None"
        return val

class EvChargerJsonSensor(DeEvChargerEntity, SensorEntity):
    def __init__(self, coordinator, entry, dp, name, json_key, device_class, unit, scale):
        super().__init__(coordinator, entry)
        self.dp = dp
        self.json_key = json_key
        self.scale = scale
        self._attr_name = f"{name}"
        self._attr_unique_id = f"de_ev_{name.lower().replace(' ', '_')}"
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        
        # Duration shouldn't have a measurement state class if it resets
        if device_class != SensorDeviceClass.DURATION:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        else:
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

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

class EvChargerPhaseSensor(DeEvChargerEntity, SensorEntity):
    def __init__(self, coordinator, entry, phase, index, name, device_class, unit, scale):
        super().__init__(coordinator, entry)
        self.phase = phase
        self.index = index
        self.scale = scale
        self._attr_name = f"{name}"
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