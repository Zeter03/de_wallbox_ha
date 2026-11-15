from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from tinytuya import scanner

from .client import DeEvChargerClient, _coerce_bool
from .const import (
    ASLEEP_FACTOR,
    CHARGING_FACTOR,
    CONF_DEVICE_ID,
    CONF_IP,
    CONF_LOCAL_KEY,
    CONF_MAC,
    CONF_VERSION,
    DOMAIN,
    DP_DO_CHARGE,
    DP_WORK_STATE,
    DP_WORK_STATE_DEBUG,
    FAULT_DIAGNOSIS_COOLDOWN_SECONDS,
    IDLE_FACTOR,
    MAX_INTERVAL_S,
    MIN_INTERVAL_S,
    PLUGGED_IN_FACTOR,
    REDISCOVERY_COOLDOWN_SECONDS,
    REDISCOVERY_SCAN_SECONDS,
    STATUS_MAP,
    UNDECRYPTABLE_FAILURES_BEFORE_REAUTH,
    UNDECRYPTABLE_GRACE_SECONDS,
    UPDATE_INTERVAL,
    WORK_STATE_CODE_CHARGING,
    ConnectionFault,
)

LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "switch", "number", "button"]

SERVICE_RELEASE_CONNECTION = "release_connection"
SERVICE_RELEASE_SCHEMA = vol.Schema(
    {
        vol.Required("duration_minutes"): vol.All(vol.Coerce(int), vol.Range(min=0, max=120)),
    }
)


def decode_charger_status(dps: dict[str, Any] | None) -> str | None:
    if not dps:
        return None
    raw_debug = str(dps.get(DP_WORK_STATE_DEBUG, "")).strip().upper()
    try:
        work_state = int(dps[DP_WORK_STATE]) if DP_WORK_STATE in dps else None
    except (TypeError, ValueError):
        work_state = None

    if raw_debug == "SLEEP" and work_state == WORK_STATE_CODE_CHARGING:
        return "charging"
    return STATUS_MAP.get(raw_debug)


def is_actively_charging(dps: dict[str, Any] | None) -> bool:
    if not dps:
        return False
    raw_debug = str(dps.get(DP_WORK_STATE_DEBUG, "")).strip().upper()
    try:
        work_state = int(dps[DP_WORK_STATE]) if DP_WORK_STATE in dps else None
    except (TypeError, ValueError):
        work_state = None
    do_charge = _coerce_bool(dps.get(DP_DO_CHARGE))
    return (
        raw_debug == "WORKING"
        or do_charge is True
        or (raw_debug == "SLEEP" and work_state == WORK_STATE_CODE_CHARGING)
    )


def _scan_for_device(scantime: int) -> dict[str, dict[str, Any]]:
    try:
        devices = scanner.devices(
            verbose=False,
            scantime=scantime,
            color=False,
            poll=False,
            byID=True,
        )
        return {
            dev_id: info
            for dev_id, info in devices.items()
            if isinstance(info, dict) and info.get("ip")
        }
    except Exception:
        LOGGER.debug("UDP rediscovery scan failed.", exc_info=True)
        return {}


class DeEvCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator with adaptive polling, DHCP IP relocation, and slot release."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: DeEvChargerClient,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.client = client
        self.entry = entry

        self._polls_ok = 0
        self._polls_failed = 0
        self._consecutive_failures = 0
        self._last_success_at: Any = None
        self._last_failure_at: Any = None
        self._relocations = 0

        self._last_rediscovery_at = 0.0
        self._last_fault: ConnectionFault | None = None
        self._last_fault_at = 0.0
        self._undecryptable_since: float | None = None
        self._reconnect_tried = False
        self._relocating: Any = None
        self._release_until: float | None = None

    @property
    def connection_released(self) -> bool:
        if self._release_until is None:
            return False
        return self.hass.loop.time() < self._release_until

    @property
    def connection_health(self) -> dict[str, Any]:
        total = self._polls_ok + self._polls_failed
        return {
            "polls_ok": self._polls_ok,
            "polls_failed": self._polls_failed,
            "success_rate_pct": round(self._polls_ok * 100 / total, 1) if total else None,
            "consecutive_failures": self._consecutive_failures,
            "last_success_at": (
                self._last_success_at.isoformat(timespec="seconds")
                if self._last_success_at
                else None
            ),
            "last_failure_at": (
                self._last_failure_at.isoformat(timespec="seconds")
                if self._last_failure_at
                else None
            ),
            "last_fault": str(self._last_fault) if self._last_fault else None,
            "host": self.client.host,
            "relocations": self._relocations,
            "poll_interval_s": (
                int(self.update_interval.total_seconds()) if self.update_interval else None
            ),
            "connection_released": self.connection_released,
        }

    async def async_release_connection(self, duration_s: int) -> None:
        self._release_until = self.hass.loop.time() + max(0, duration_s)
        await self.client.async_close()
        LOGGER.info("Released local connection to %s for %ss", self.entry.title, duration_s)
        self.async_update_listeners()

    def async_resume_connection(self) -> None:
        self._release_until = self.hass.loop.time()

    async def _async_update_data(self) -> dict[str, Any]:
        if self._release_until is not None:
            if self.connection_released:
                return self.data or {}
            self._release_until = None
            await self.client.async_connect()
            LOGGER.info("Resuming polling of %s; connection release expired", self.entry.title)

        dps = await self.client.async_get_raw_dps()
        if dps is not None:
            self._note_success(dps)
            return dps

        # Try relocating DHCP IP if unreachable
        if await self._async_try_rediscover_host():
            dps = await self.client.async_get_raw_dps()
            if dps is not None:
                self._note_success(dps)
                return dps

        self._polls_failed += 1
        self._consecutive_failures += 1
        self._last_failure_at = dt_util.now()

        message = await self._async_failure_message()
        if self._last_fault == ConnectionFault.UNDECRYPTABLE:
            now = self.hass.loop.time()
            if self._undecryptable_since is None:
                self._undecryptable_since = now
            if (
                self._consecutive_failures >= UNDECRYPTABLE_FAILURES_BEFORE_REAUTH
                and now - self._undecryptable_since >= UNDECRYPTABLE_GRACE_SECONDS
            ):
                if not self._reconnect_tried:
                    self._reconnect_tried = True
                    LOGGER.warning(
                        "Charger at %s unreadable for %ss; rebuilding connection once.",
                        self.client.host,
                        round(now - self._undecryptable_since),
                    )
                    await self.client.async_connect()
                    dps = await self.client.async_get_raw_dps()
                    if dps is not None:
                        self._note_success(dps)
                        return dps
                raise ConfigEntryAuthFailed(message)
        else:
            self._undecryptable_since = None
            self._reconnect_tried = False

        raise UpdateFailed(message)

    def _note_success(self, dps: dict[str, Any]) -> None:
        self._polls_ok += 1
        self._consecutive_failures = 0
        self._undecryptable_since = None
        self._reconnect_tried = False
        self._last_success_at = dt_util.now()
        self._last_fault = None
        self._last_fault_at = 0.0
        self._retune_interval(dps)

    def _retune_interval(self, dps: dict[str, Any]) -> None:
        status = decode_charger_status(dps)
        if status in ("charging", "waiting"):
            factor = CHARGING_FACTOR
        elif status in ("plugged_in", "paused", "charged"):
            factor = PLUGGED_IN_FACTOR
        elif status == "sleep":
            factor = ASLEEP_FACTOR
        else:
            factor = IDLE_FACTOR

        secs = max(MIN_INTERVAL_S, min(MAX_INTERVAL_S, round(UPDATE_INTERVAL * factor)))
        wanted = timedelta(seconds=secs)
        if wanted != self.update_interval:
            LOGGER.debug("Adaptive poll interval -> %ss (status=%s)", secs, status)
            self.update_interval = wanted

    async def _async_failure_message(self) -> str:
        host = self.client.host
        now = self.hass.loop.time()
        if self._last_fault is None or (now - self._last_fault_at) >= FAULT_DIAGNOSIS_COOLDOWN_SECONDS:
            try:
                self._last_fault = await self.client.async_classify_fault()
                self._last_fault_at = now
            except Exception:
                pass

        if self._last_fault == ConnectionFault.REFUSED:
            return (
                f"Charger at {host} refused connection (Smart Life app or another "
                "integration may be holding its single local slot)."
            )
        if self._last_fault == ConnectionFault.UNDECRYPTABLE:
            return f"Charger at {host} answered, but replies could not be decrypted (check local_key)."
        return f"Charger unreachable at {host}."

    async def _async_try_rediscover_host(self) -> bool:
        now = self.hass.loop.time()
        if now - self._last_rediscovery_at < REDISCOVERY_COOLDOWN_SECONDS:
            return False
        self._last_rediscovery_at = now

        if self.data is not None:
            if self._relocating is None or self._relocating.done():
                self._relocating = self.entry.async_create_background_task(
                    self.hass, self._async_bg_relocate(), name=f"{DOMAIN}_relocate"
                )
            return False
        return await self._async_relocate()

    async def _async_bg_relocate(self) -> None:
        if await self._async_relocate():
            await self.async_request_refresh()

    async def _async_relocate(self) -> bool:
        dev_id = self.client.device_id
        candidates = await self.hass.async_add_executor_job(
            _scan_for_device, REDISCOVERY_SCAN_SECONDS
        )
        info = candidates.get(dev_id)
        if info and info.get("ip"):
            new_host = str(info["ip"]).strip()
            if new_host and new_host != self.client.host:
                LOGGER.info("Relocated charger %s -> %s", dev_id, new_host)
                await self.client.async_update_host(new_host)
                self._relocations += 1
                self.hass.config_entries.async_update_entry(
                    self.entry, data={**self.entry.data, CONF_IP: new_host}
                )
                return True
        return False


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    async def _handle_release(call: ServiceCall) -> None:
        minutes = int(call.data["duration_minutes"])
        for entry in hass.config_entries.async_entries(DOMAIN):
            coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if isinstance(coordinator, DeEvCoordinator):
                if minutes <= 0:
                    coordinator.async_resume_connection()
                    await coordinator.async_request_refresh()
                else:
                    await coordinator.async_release_connection(minutes * 60)

    if not hass.services.has_service(DOMAIN, SERVICE_RELEASE_CONNECTION):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RELEASE_CONNECTION,
            _handle_release,
            schema=SERVICE_RELEASE_SCHEMA,
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = DeEvChargerClient(
        device_id=entry.data[CONF_DEVICE_ID],
        host=entry.data[CONF_IP],
        local_key=entry.data[CONF_LOCAL_KEY],
        version=entry.data.get(CONF_VERSION, "3.5"),
    )
    try:
        await client.async_connect()
    except Exception as err:
        raise ConfigEntryNotReady(f"Unable to connect to {entry.title}: {err}") from err

    coordinator = DeEvCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: DeEvCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.async_close()
    return unload_ok