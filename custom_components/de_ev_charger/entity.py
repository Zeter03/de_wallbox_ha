from __future__ import annotations

import json
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo, format_mac
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, CONF_MAC, DOMAIN, DP_CHARGER_INFO, DP_PRODUCT_VARIANT


class DeEvChargerEntity(CoordinatorEntity):
    """Base entity grouping all wallbox entities under one Device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        self.entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        fw_version = "Unknown"
        hw_version = None
        dps = self.coordinator.data or {}

        raw_info = dps.get(DP_CHARGER_INFO)
        if raw_info:
            try:
                fw_version = json.loads(raw_info).get("fv", fw_version)
            except (ValueError, TypeError, json.JSONDecodeError):
                pass

        if DP_PRODUCT_VARIANT in dps:
            hw_version = str(dps[DP_PRODUCT_VARIANT])

        info = DeviceInfo(
            identifiers={(DOMAIN, self.entry.data[CONF_DEVICE_ID])},
            name="dé EV Charger",
            manufacturer="dé",
            model="EV Charger (Tuya)",
            sw_version=fw_version,
            hw_version=hw_version,
            configuration_url=f"http://{self.coordinator.client.host}",
        )

        raw_mac = self.entry.data.get(CONF_MAC)
        if raw_mac:
            info["connections"] = {(CONNECTION_NETWORK_MAC, format_mac(str(raw_mac)))}

        return info