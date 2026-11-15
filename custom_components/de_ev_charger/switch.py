from __future__ import annotations

from time import monotonic

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory

from .const import (
    DOMAIN,
    DP_DO_CHARGE,
    DP_PLUG_CHARGE,
    DP_SINGLE_PHASE,
    DP_WORK_STATE,
    DP_WORK_STATE_DEBUG,
    WORK_STATE_CODE_CHARGING,
)
from .entity import DeEvChargerEntity

_PENDING_TIMEOUT_S = 90.0
_NOT_STARTING_STATES = frozenset({"SLEEP", "IDLE", "STOP", "ERRORPAUSE"})


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        EvChargerStartSwitch(coordinator, entry),
        EvChargerConfigSwitch(coordinator, entry, DP_PLUG_CHARGE, "Plug and Charge", "mdi:power-plug"),
        EvChargerConfigSwitch(coordinator, entry, DP_SINGLE_PHASE, "Single Phase Mode", "mdi:sine-wave"),
    ])


class EvChargerStartSwitch(DeEvChargerEntity, SwitchEntity):
    """Start/Stop Charging switch backed by DP 140 & DP 109/101 state."""

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self.dp = DP_DO_CHARGE
        self._attr_name = "Start Charge"
        self._attr_unique_id = f"de_ev_switch_{self.dp}"
        self._attr_icon = "mdi:ev-station"
        self._pending: bool | None = None
        self._pending_since = 0.0

    @property
    def _reported_on(self) -> bool:
        dps = self.coordinator.data or {}
        work_state_debug = str(dps.get(DP_WORK_STATE_DEBUG, "")).strip().upper()
        try:
            work_state = int(dps[DP_WORK_STATE]) if DP_WORK_STATE in dps else None
        except (TypeError, ValueError):
            work_state = None

        # Active in WORKING/WAIT, or if screen is asleep while DP 101 == 300. PAUSE is OFF.
        return work_state_debug in ("WORKING", "WAIT") or (
            work_state_debug == "SLEEP" and work_state == WORK_STATE_CODE_CHARGING
        )

    @property
    def is_on(self) -> bool:
        reported = self._reported_on
        pending = self._pending
        if pending is None:
            return reported

        dps = self.coordinator.data or {}
        raw_debug = str(dps.get(DP_WORK_STATE_DEBUG, "")).strip().upper()
        stalled = pending and raw_debug in _NOT_STARTING_STATES
        if reported == pending or stalled or (monotonic() - self._pending_since > _PENDING_TIMEOUT_S):
            self._pending = None
            return reported
        return pending

    async def async_turn_on(self, **kwargs) -> None:
        if self._reported_on:
            return
        if await self.coordinator.client.async_send_command(self.dp, True):
            self._pending = True
            self._pending_since = monotonic()
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        if not self._reported_on:
            return
        if await self.coordinator.client.async_send_command(self.dp, False):
            self._pending = False
            self._pending_since = monotonic()
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()


class EvChargerConfigSwitch(DeEvChargerEntity, SwitchEntity):
    """Configuration toggles (Plug & Charge, Single Phase Mode)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry, dp: str, name: str, icon: str) -> None:
        super().__init__(coordinator, entry)
        self.dp = dp
        self._attr_name = name
        self._attr_unique_id = f"de_ev_switch_{dp}"
        self._attr_icon = icon

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data or {}).get(self.dp, False))

    async def async_turn_on(self, **kwargs) -> None:
        if self.is_on:
            return
        if await self.coordinator.client.async_send_command(self.dp, True):
            self.coordinator.data[self.dp] = True
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        if not self.is_on:
            return
        if await self.coordinator.client.async_send_command(self.dp, False):
            self.coordinator.data[self.dp] = False
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()