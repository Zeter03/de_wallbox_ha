import json
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfElectricPotential, UnitOfElectricCurrent, UnitOfPower, UnitOfTemperature, UnitOfEnergy
from .const import DOMAIN
from .entity import DeEvChargerEntity

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = [
        EvChargerStateSensor(coordinator, entry, "109", "Work State", "mdi:ev-station"),
        EvChargerStateSensor(coordinator, entry, "104", "Alarm Info", "mdi:alert"),
        EvChargerStateSensor(coordinator, entry, "111", "Debug Output", "mdi:bug"),
        EvChargerStateSensor(coordinator, entry, "153", "Live Status Text", "mdi:information"),
        EvChargerStateSensor(coordinator, entry, "105", "Last Session History (Raw)", "mdi:history"),
        
        # DP 105 - Last Session Extracted Metrics
        EvChargerJsonSensor(coordinator, entry, "105", "Last Session Energy", "c", SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR, 0.1, None),
        EvChargerDurationSensor(coordinator, entry, "105", "Last Session Duration", json_key="d", scale=1.0),

        # DP 102 - Real Time Metrics
        EvChargerJsonSensor(coordinator, entry, "102", "Temperature", "t", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, 0.1, SensorStateClass.MEASUREMENT),
        EvChargerJsonSensor(coordinator, entry, "102", "Session Power", "p", SensorDeviceClass.POWER, UnitOfPower.KILO_WATT, 0.1, SensorStateClass.MEASUREMENT),
        EvChargerJsonSensor(coordinator, entry, "102", "Session Energy", "e", SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR, 0.1, SensorStateClass.TOTAL_INCREASING),
        EvChargerDurationSensor(coordinator, entry, "102", "Session Duration", json_key="d", scale=0.1),
        
        # DP 106 - Hardware / Lifetime Information
        EvChargerJsonSensor(coordinator, entry, "106", "Control Pilot Voltage", "cp", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, 1.0, SensorStateClass.MEASUREMENT),
        EvChargerJsonSensor(coordinator, entry, "106", "Lifetime Energy", "e", SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR, 0.1, SensorStateClass.TOTAL_INCREASING),
        EvChargerJsonSensor(coordinator, entry, "106", "Total Charging Sessions", "t", None, "sessions", 0.1, SensorStateClass.TOTAL_INCREASING),
    ]
    
    # Generate Phase L1, L2, L3 Sensors
    for phase in ["L1", "L2", "L3"]:
        entities.append(EvChargerPhaseSensor(coordinator, entry, phase, 0, f"{phase} Voltage", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, 0.1))
        entities.append(EvChargerPhaseSensor(coordinator, entry, phase, 1, f"{phase} Current", SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE, 0.1))
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

class EvChargerDurationSensor(DeEvChargerEntity, SensorEntity):
    """Extracts duration and formats it as an HH:MM string."""
    def __init__(self, coordinator, entry, dp, name, json_key="d", scale=1.0):
        super().__init__(coordinator, entry)
        self.dp = dp
        self.json_key = json_key
        self.scale = scale
        self._attr_name = f"{name}"
        self._attr_unique_id = f"de_ev_duration_{dp}_{json_key}"
        self._attr_icon = "mdi:timer-outline"

    @property
    def native_value(self):
        raw = self.coordinator.data.get(self.dp)
        if raw:
            try:
                data = json.loads(raw)
                if self.json_key not in data:
                    return None
                
                # Apply the specific scale (0.1 for live, 1.0 for history) to get total seconds
                total_seconds = float(data[self.json_key]) * self.scale
                
                # Calculate hours and minutes
                hours = int(total_seconds // 3600)
                minutes = int((total_seconds % 3600) // 60)
                
                # Format exactly as HH:MM
                return f"{hours:02d}:{minutes:02d}"
            except (ValueError, TypeError, json.JSONDecodeError):
                return None
        return None

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
                
                if self.json_key not in data:
                    return None
                    
                val = float(data[self.json_key])
                result = val * self.scale
                
                if self.json_key == "t" and self.dp == "106":
                    return int(result)
                return round(result, 2)
                
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