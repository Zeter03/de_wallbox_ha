from __future__ import annotations

import json
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)

from . import decode_charger_status, is_actively_charging
from .const import (
    DOMAIN,
    DP_ALARM,
    DP_CHARGE_HISTORY,
    DP_CHARGER_INFO,
    DP_DEBUG,
    DP_LIVE_STATUS_TEXT,
    DP_METRICS,
    DP_NUM,
    DP_WORK_STATE_DEBUG,
    STATUS_OPTIONS,
)
from .entity import DeEvChargerEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        # Status & text outputs
        EvChargerStatusSensor(coordinator, entry),
        EvChargerStateSensor(coordinator, entry, DP_WORK_STATE_DEBUG, "Work State", "mdi:ev-station"),
        EvChargerStateSensor(coordinator, entry, DP_ALARM, "Alarm Info", "mdi:alert"),
        EvChargerStateSensor(coordinator, entry, DP_DEBUG, "Debug Output", "mdi:bug"),
        EvChargerStateSensor(coordinator, entry, DP_LIVE_STATUS_TEXT, "Live Status Text", "mdi:information"),
        EvChargerStateSensor(coordinator, entry, DP_CHARGE_HISTORY, "Last Session History (Raw)", "mdi:history"),

        # DP 105 - Last Session Extracted Metrics
        EvChargerJsonSensor(coordinator, entry, DP_CHARGE_HISTORY, "Last Session Energy", "c", SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR, 0.1, None),
        EvChargerDurationSensor(coordinator, entry, DP_CHARGE_HISTORY, "Last Session Duration", json_key="d", scale=1.0),
        EvChargerHistoryTimeSensor(coordinator, entry, DP_CHARGE_HISTORY, "Last Session Start Time", time_key="s", icon="mdi:clock-start"),
        EvChargerHistoryTimeSensor(coordinator, entry, DP_CHARGE_HISTORY, "Last Session End Time", time_key="e", icon="mdi:clock-end"),

        # DP 102 - Real Time Metrics
        EvChargerTotalPowerSensor(coordinator, entry),
        EvChargerJsonSensor(coordinator, entry, DP_METRICS, "Temperature", "t", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, 0.1, SensorStateClass.MEASUREMENT),
        EvChargerJsonSensor(coordinator, entry, DP_METRICS, "Session Power", "p", SensorDeviceClass.POWER, UnitOfPower.KILO_WATT, 0.1, SensorStateClass.MEASUREMENT),
        EvChargerJsonSensor(coordinator, entry, DP_METRICS, "Session Energy", "e", SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR, 0.1, SensorStateClass.TOTAL_INCREASING),
        EvChargerDurationSensor(coordinator, entry, DP_METRICS, "Session Duration", json_key="d", scale=0.1),

        # DP 106 - Hardware / Lifetime Information
        EvChargerJsonSensor(coordinator, entry, DP_CHARGER_INFO, "Control Pilot Voltage", "cp", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, 1.0, SensorStateClass.MEASUREMENT),
        EvChargerJsonSensor(coordinator, entry, DP_CHARGER_INFO, "Lifetime Energy", "e", SensorDeviceClass.ENERGY, UnitOfEnergy.KILO_WATT_HOUR, 0.1, SensorStateClass.TOTAL_INCREASING),
        EvChargerJsonSensor(coordinator, entry, DP_CHARGER_INFO, "Total Charging Sessions", "t", None, "sessions", 0.1, SensorStateClass.TOTAL_INCREASING),

        # Diagnostics
        EvChargerDpNumSensor(coordinator, entry),
        EvChargerConnectionHealthSensor(coordinator, entry),
    ]

    for phase in ("L1", "L2", "L3"):
        entities.append(EvChargerPhaseSensor(coordinator, entry, phase, 0, f"{phase} Voltage", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT))
        entities.append(EvChargerPhaseSensor(coordinator, entry, phase, 1, f"{phase} Current", SensorDeviceClass.CURRENT, UnitOfElectricCurrent.AMPERE))
        entities.append(EvChargerPhaseSensor(coordinator, entry, phase, 2, f"{phase} Power", SensorDeviceClass.POWER, UnitOfPower.KILO_WATT))

    async_add_entities(entities)


def _extract_phase_values(dps: dict[str, Any], phase: str) -> tuple[float, float, float] | None:
    """Decode [V*10, A*10, kW*10], calculate exact kW, and zero stale readings when idle."""
    raw = dps.get(DP_METRICS)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        arr = data.get(phase)
        if not isinstance(arr, list) or len(arr) < 3:
            return None
        voltage = float(arr[0]) / 10.0
        raw_current = float(arr[1]) / 10.0
        # Omit unwired L2/L3 phases on single-phase installations
        if phase != "L1" and voltage == 0.0 and raw_current == 0.0:
            return None
        current = raw_current if is_actively_charging(dps) else 0.0
        power_kw = round((voltage * current) / 1000.0, 3)
        return round(voltage, 1), round(current, 1), power_kw
    except (ValueError, TypeError, json.JSONDecodeError, IndexError):
        return None


class EvChargerStatusSensor(DeEvChargerEntity, SensorEntity):
    """Translated, user-friendly charger status."""

    _attr_translation_key = "status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(STATUS_OPTIONS)

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = "Status"
        self._attr_unique_id = "de_ev_status"
        self._attr_icon = "mdi:ev-station"

    @property
    def native_value(self) -> str | None:
        return decode_charger_status(self.coordinator.data)


class EvChargerTotalPowerSensor(DeEvChargerEntity, SensorEntity):
    """Total charging power summed across all active phases (derived from V x A)."""

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = "Total Power"
        self._attr_unique_id = "de_ev_total_power"
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        dps = self.coordinator.data
        if not dps:
            return None
        total = 0.0
        found = False
        for phase in ("L1", "L2", "L3"):
            vals = _extract_phase_values(dps, phase)
            if vals is not None:
                total += vals[2]
                found = True
        return round(total, 3) if found else None


class EvChargerDpNumSensor(DeEvChargerEntity, SensorEntity):
    """Tracks DP 189 (daily DP report count toward the 3400/day firmware cap)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = "Daily DP Count"
        self._attr_unique_id = "de_ev_dp_num"
        self._attr_icon = "mdi:counter"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        val = (self.coordinator.data or {}).get(DP_NUM)
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None


class EvChargerConnectionHealthSensor(DeEvChargerEntity, SensorEntity):
    """Poll success percentage and connection diagnostics."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = "Connection Health"
        self._attr_unique_id = "de_ev_connection_health"
        self._attr_icon = "mdi:wifi-check"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> float | None:
        return self.coordinator.connection_health["success_rate_pct"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return dict(self.coordinator.connection_health)


class EvChargerStateSensor(DeEvChargerEntity, SensorEntity):
    def __init__(self, coordinator, entry, dp, name, icon) -> None:
        super().__init__(coordinator, entry)
        self.dp = dp
        self._attr_name = name
        self._attr_unique_id = f"de_ev_{name.lower().replace(' ', '_')}"
        self._attr_icon = icon

    @property
    def native_value(self):
        val = (self.coordinator.data or {}).get(self.dp)
        if val == "{}" or val == "":
            return "None"
        return val


class EvChargerHistoryTimeSensor(DeEvChargerEntity, SensorEntity):
    def __init__(self, coordinator, entry, dp, name, time_key, icon) -> None:
        super().__init__(coordinator, entry)
        self.dp = dp
        self.time_key = time_key
        self._attr_name = name
        self._attr_unique_id = f"de_ev_time_{dp}_{time_key}"
        self._attr_icon = icon

    @property
    def native_value(self):
        raw = (self.coordinator.data or {}).get(self.dp)
        if not raw:
            return None
        try:
            data = json.loads(raw)
            t_str = data.get("t", "")
            time_str = data.get(self.time_key, "")
            if not t_str or not time_str:
                return None
            date_split = t_str.split(" ")[0].split("-")
            if len(date_split) == 3:
                return f"{date_split[2]}.{date_split[1]}. - {time_str}"
            return time_str
        except (ValueError, TypeError, json.JSONDecodeError):
            return None


class EvChargerDurationSensor(DeEvChargerEntity, SensorEntity):
    def __init__(self, coordinator, entry, dp, name, json_key="d", scale=1.0) -> None:
        super().__init__(coordinator, entry)
        self.dp = dp
        self.json_key = json_key
        self.scale = scale
        self._attr_name = name
        self._attr_unique_id = f"de_ev_duration_{dp}_{json_key}"
        self._attr_icon = "mdi:timer-outline"

    @property
    def native_value(self):
        raw = (self.coordinator.data or {}).get(self.dp)
        if not raw:
            return None
        try:
            data = json.loads(raw)
            if self.json_key not in data:
                return None
            total_seconds = float(data[self.json_key]) * self.scale
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            return f"{hours:02d}:{minutes:02d}"
        except (ValueError, TypeError, json.JSONDecodeError):
            return None


class EvChargerJsonSensor(DeEvChargerEntity, SensorEntity):
    def __init__(self, coordinator, entry, dp, name, json_key, device_class, unit, scale, state_class) -> None:
        super().__init__(coordinator, entry)
        self.dp = dp
        self.json_key = json_key
        self.scale = scale
        self._attr_name = name
        self._attr_unique_id = f"de_ev_json_{dp}_{json_key}"
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        if state_class:
            self._attr_state_class = state_class

    @property
    def native_value(self):
        raw = (self.coordinator.data or {}).get(self.dp)
        if not raw:
            return None
        try:
            data = json.loads(raw)
            if self.json_key not in data:
                return None
            val = float(data[self.json_key])
            # Zero out session power when not actively charging
            if self.dp == DP_METRICS and self.json_key == "p" and not is_actively_charging(self.coordinator.data):
                return 0.0
            result = val * self.scale
            if self.json_key == "t" and self.dp == DP_CHARGER_INFO:
                return int(result)
            return round(result, 2)
        except (ValueError, TypeError, json.JSONDecodeError):
            return None


class EvChargerPhaseSensor(DeEvChargerEntity, SensorEntity):
    def __init__(self, coordinator, entry, phase, index, name, device_class, unit) -> None:
        super().__init__(coordinator, entry)
        self.phase = phase
        self.index = index
        self._attr_name = name
        self._attr_unique_id = f"de_ev_phase_{phase.lower()}_{index}"
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        dps = self.coordinator.data
        if not dps:
            return None
        vals = _extract_phase_values(dps, self.phase)
        if vals is None:
            return None
        return vals[self.index]