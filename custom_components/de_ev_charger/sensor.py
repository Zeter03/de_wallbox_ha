import json
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfElectricPotential, UnitOfElectricCurrent, UnitOfPower, UnitOfTemperature, UnitOfEnergy, UnitOfTime
from .const import DOMAIN
from .entity import DeEvChargerEntity

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = [
        EvChargerStateSensor(coordinator, entry, "109", "Work State", "mdi:ev-station"),
        EvChargerStateSensor(coordinator, entry, "104", "Alarm Info", "mdi:alert"),
        EvChargerStateSensor(coordinator, entry, "111", "Debug Output", "mdi:bug"),
        EvChargerStateSensor(coordinator, entry, "153", "Live Status Text", "mdi:information"),
        EvChargerStateSensor(coordinator, entry, "105", "Last Session History", "mdi:history"),
        
        # DP 102 - Real Time Metrics
        EvChargerJsonSensor(coordinator, entry, "102", "Temperature", "t", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, 0.1, SensorStateClass.MEASUREMENT),
        EvChargerJsonSensor(coordinator, entry, "102", "Session Power", "p", SensorDeviceClass.POWER, UnitOfPower.KILO_WATT, 0.1, SensorStateClass.MEASUREMENT),
        
        # TOTAL_INCREASING allows these to be used in the Home Assistant Energy Dashboard
        EvChargerJsonSensor(coordinator, entry, "102", "Session Energy", "e", SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR, 0.1, SensorStateClass.TOTAL_INCREASING),
        EvChargerJsonSensor(coordinator, entry, "102", "Session Duration", "d", SensorDeviceClass.DURATION, UnitOfTime.SECONDS, 0.1, None),
        
        # DP 106 - Hardware / Lifetime Information
        EvChargerJsonSensor(coordinator, entry, "106", "Control Pilot Voltage", "cp", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, 1.0, SensorStateClass.MEASUREMENT),
        EvChargerJsonSensor(coordinator, entry, "106", "Lifetime Energy", "e", SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR, 1.0, SensorStateClass.TOTAL_INCREASING),
        EvChargerJsonSensor(coordinator, entry, "106", "Lifetime Time", "t", SensorDeviceClass.DURATION, UnitOfTime.HOURS, 1.0, None),
    ]
    
    # Generate Phase L1, L2, L3 Sensors
    for phase in ["L1", "L2", "L3"]:
        entities.append(EvChargerPhaseSensor(coordinator, entry, phase, 0, f"{phase} Voltage", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, 0.1))
        entities.append(EvChargerPhaseSensor(coordinator, entry, phase, 1, f"{phase} Current", SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE, 0.1))
        
        # Notice Power is now KILO_WATT and scale is 0.1
        entities.append(EvChargerPhaseSensor(coordinator, entry, phase, 2, f"{phase} Power", SensorDeviceClass.POWER, UnitOfPower.KILO_WATT, 0.1))
        
    async_add_entities(entities)

class EvChargerStateSensor(DeEvChargerEntity, SensorEntity):
    """String based sensors for states, text info, and errors."""
    def __init__(self, coordinator, entry, dp, name, icon):
        super().__init__(coordinator, entry)
        self.dp = dp
        self._attr_name = f"{name}"
        self._attr_unique_id = f"de_ev_{name.lower().replace(' ', '_')}"
        self._attr_icon = icon

    @property
    def native_value(self):
        val = self.coordinator.data.get(self.dp)
        if val == "{}" or val == "":
            return "None"
        return val

class EvChargerJsonSensor(DeEvChargerEntity, SensorEntity):
    """Extracts a specific key from a JSON string Data Point."""
    def __init__(self, coordinator, entry, dp, name, json_key, device_class, unit, scale, state_class):
        super().__init__(coordinator, entry)
        self.dp = dp
        self.json_key = json_key
        self.scale = scale
        self._attr_name = f"{name}"
        self._attr_unique_id = f"de_ev_json_{dp}_{json_key}"
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        if state_class:
            self._attr_state_class = state_class

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
    """Extracts Phase Array Data like 'L1': [2250, 143, 32]."""
    def __init__(self, coordinator, entry, phase, index, name, device_class, unit, scale):
        super().__init__(coordinator, entry)
        self.phase = phase
        self.index = index
        self.scale = scale
        self._attr_name = f"{name}"
        self._attr_unique_id = f"de_ev_phase_{phase.lower()}_{index}"
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
            except (ValueError, TypeError, json.JSONDecodeError, IndexError):
                return None
        return None