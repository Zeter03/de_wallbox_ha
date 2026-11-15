from __future__ import annotations

import json

from homeassistant.components.number import NumberEntity
from homeassistant.const import UnitOfElectricCurrent

from .const import DOMAIN, DP_ADJUST_CURRENT, DP_CHARGE_CURRENT, DP_MAX_CURRENT_CFG
from .entity import DeEvChargerEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EvChargerCurrentLimit(coordinator, entry)])


class EvChargerCurrentLimit(DeEvChargerEntity, NumberEntity):
    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self.dp = DP_CHARGE_CURRENT
        self._attr_name = "Charge Current Limit"
        self._attr_unique_id = "de_ev_charge_current_limit"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_native_step = 1.0

    @property
    def native_min_value(self) -> float:
        raw_opts = (self.coordinator.data or {}).get(DP_ADJUST_CURRENT)
        if raw_opts:
            try:
                opts = json.loads(raw_opts) if isinstance(raw_opts, str) else raw_opts
                if isinstance(opts, list) and opts:
                    return float(min(int(x) for x in opts))
            except (ValueError, TypeError, json.JSONDecodeError):
                pass
        return 6.0

    @property
    def native_max_value(self) -> float:
        raw_max = (self.coordinator.data or {}).get(DP_MAX_CURRENT_CFG)
        if raw_max is not None:
            try:
                return float(max(6, min(32, int(raw_max))))
            except (ValueError, TypeError):
                pass
        return 16.0

    @property
    def native_value(self) -> float | None:
        val = (self.coordinator.data or {}).get(self.dp)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                return None
        return None

    async def async_set_native_value(self, value: float) -> None:
        amperage = round(value)
        current = self.native_value
        # Skip redundant write to avoid wallbox beeps & DP quota usage
        if current is not None and int(current) == amperage:
            return

        if await self.coordinator.client.async_send_command(self.dp, amperage):
            self.coordinator.data[self.dp] = amperage
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()