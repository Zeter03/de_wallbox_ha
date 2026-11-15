from __future__ import annotations

import asyncio
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory

from .const import DOMAIN, DP_HEARTBEAT, DP_WORK_STATE, WORK_STATE_READY_TO_CHARGE
from .entity import DeEvChargerEntity

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        EvChargerRebootButton(coordinator, entry),
        EvChargerReadyToChargeButton(coordinator, entry),
        EvChargerRefreshButton(coordinator, entry),
    ])


class EvChargerRebootButton(DeEvChargerEntity, ButtonEntity):
    """Button to restart the EV Charger."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = "Reboot Charger"
        self._attr_unique_id = "de_ev_button_reboot"
        self._attr_icon = "mdi:restart"

    async def async_press(self) -> None:
        await self.coordinator.client.async_reboot()
        await asyncio.sleep(3)
        try:
            await self.coordinator.async_request_refresh()
        except Exception as err:
            LOGGER.debug("Refresh after reboot failed while charger restarts: %s", err)


class EvChargerReadyToChargeButton(DeEvChargerEntity, ButtonEntity):
    """Puts the charger back into ready-to-charge (DP 101 = 200) to clear stale power."""

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = "Ready to Charge"
        self._attr_unique_id = "de_ev_button_ready_to_charge"
        self._attr_icon = "mdi:ev-plug-type2"

    async def async_press(self) -> None:
        await self.coordinator.client.async_send_command(DP_WORK_STATE, WORK_STATE_READY_TO_CHARGE)
        await self.coordinator.async_request_refresh()


class EvChargerRefreshButton(DeEvChargerEntity, ButtonEntity):
    """Manual on-demand refresh (DP 188) instead of spamming automatically."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_name = "Refresh Charger Data"
        self._attr_unique_id = "de_ev_button_refresh"
        self._attr_icon = "mdi:refresh"

    async def async_press(self) -> None:
        await self.coordinator.client.async_send_command(DP_HEARTBEAT, True, verify=False)
        await asyncio.sleep(0.5)
        await self.coordinator.async_request_refresh()