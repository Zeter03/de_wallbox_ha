from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Callable
from typing import Any

import tinytuya

from .const import (
    COMMAND_VERIFY_DELAY_S,
    COMMAND_VERIFY_RETRIES,
    DP_REBOOT,
    IO_TIMEOUT_S,
    SOCKET_RETRY_DELAY_S,
    SOCKET_RETRY_LIMIT,
    SOCKET_TIMEOUT_S,
    TUYA_CONTROL_PORT,
    ConnectionFault,
)

LOGGER = logging.getLogger(__name__)


def _configure_device(device: tinytuya.Device) -> None:
    device.set_socketTimeout(SOCKET_TIMEOUT_S)
    device.set_socketRetryLimit(SOCKET_RETRY_LIMIT)
    device.set_socketRetryDelay(SOCKET_RETRY_DELAY_S)


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "1", "on"):
            return True
        if low in ("false", "0", "off"):
            return False
    return None


def _values_match(received: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        rec_bool = _coerce_bool(received)
        return rec_bool is not None and rec_bool == expected
    try:
        return int(received) == int(expected)
    except (TypeError, ValueError):
        return str(received).strip() == str(expected).strip()


class DeEvChargerClient:
    """Thread-safe local client serialized around the charger's single TCP slot."""

    def __init__(self, device_id: str, host: str, local_key: str, version: str | float) -> None:
        self._device_id = device_id
        self._host = host
        self._local_key = local_key
        self._version = float(version)
        self._device: tinytuya.Device | None = None
        self._io_lock = asyncio.Lock()
        self._needs_reconnect = False

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def host(self) -> str:
        return self._host

    @property
    def version(self) -> float:
        return self._version

    async def async_connect(self) -> None:
        async with self._io_lock:
            self._build_device()

    def _build_device(self) -> tinytuya.Device:
        if self._device is not None:
            try:
                self._device.close()
            except OSError:
                pass
        device = tinytuya.Device(
            dev_id=self._device_id,
            address=self._host,
            local_key=self._local_key,
            version=self._version,
        )
        _configure_device(device)
        self._device = device
        self._needs_reconnect = False
        return device

    def _get_device(self) -> tinytuya.Device:
        if self._device is None and self._needs_reconnect:
            return self._build_device()
        if self._device is None:
            raise RuntimeError("Client not initialized. Call async_connect first.")
        return self._device

    async def _async_in_thread(self, func: Callable[..., Any], *args: Any) -> Any:
        """Run a blocking tinytuya call off the event loop with a hard timeout."""
        try:
            async with asyncio.timeout(IO_TIMEOUT_S):
                return await asyncio.to_thread(func, *args)
        except TimeoutError:
            LOGGER.warning(
                "Charger I/O timed out after %ss; resetting connection.", IO_TIMEOUT_S
            )
            device, self._device = self._device, None
            self._needs_reconnect = True
            if device is not None:
                try:
                    await asyncio.to_thread(device.close)
                except OSError as err:
                    LOGGER.debug("Closing stuck socket failed: %s", err)
            raise

    async def async_update_host(self, host: str) -> None:
        self._host = host
        await self.async_connect()

    async def async_close(self) -> None:
        """Close the socket cleanly so it doesn't linger on port 6668."""
        async with self._io_lock:
            if self._device is not None:
                device, self._device = self._device, None
                try:
                    async with asyncio.timeout(IO_TIMEOUT_S):
                        await asyncio.to_thread(device.close)
                except (TimeoutError, OSError):
                    LOGGER.debug("Timed out closing charger socket; abandoning.")
            self._needs_reconnect = False

    async def _async_probe_port(self) -> ConnectionFault:
        def _connect() -> ConnectionFault:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(SOCKET_TIMEOUT_S)
            try:
                sock.connect((self._host, TUYA_CONTROL_PORT))
                return ConnectionFault.OK
            except ConnectionRefusedError:
                return ConnectionFault.REFUSED
            except OSError:
                return ConnectionFault.UNREACHABLE
            finally:
                sock.close()

        try:
            async with asyncio.timeout(IO_TIMEOUT_S):
                return await asyncio.to_thread(_connect)
        except TimeoutError:
            return ConnectionFault.UNREACHABLE

    async def async_probe_host(self, host: str) -> bool:
        def _probe() -> bool:
            device = tinytuya.Device(
                dev_id=self._device_id,
                address=host,
                local_key=self._local_key,
                version=self._version,
            )
            _configure_device(device)
            try:
                payload = device.status()
            except Exception:
                return False
            finally:
                try:
                    device.close()
                except OSError:
                    pass
            return (
                isinstance(payload, dict)
                and "Error" not in payload
                and isinstance(payload.get("dps"), dict)
                and bool(payload["dps"])
            )

        try:
            async with asyncio.timeout(IO_TIMEOUT_S):
                return await asyncio.to_thread(_probe)
        except TimeoutError:
            return False

    async def async_classify_fault(self) -> ConnectionFault:
        verdict = await self._async_probe_port()
        if verdict != ConnectionFault.OK:
            return verdict
        return (
            ConnectionFault.OK
            if await self.async_probe_host(self._host)
            else ConnectionFault.UNDECRYPTABLE
        )

    async def _async_get_dps_payload(self) -> dict[str, Any] | None:
        device = self._get_device()
        try:
            payload = await self._async_in_thread(device.status)
        except TimeoutError:
            return None
        except Exception as err:
            LOGGER.debug("tinytuya status() error: %s", err)
            return None

        if not isinstance(payload, dict):
            LOGGER.debug("Invalid status payload type: %s", type(payload).__name__)
            return None
        if "Error" in payload:
            LOGGER.debug("Charger returned error payload: %s", payload["Error"])
            return None

        dps = payload.get("dps")
        if not isinstance(dps, dict):
            return None
        return dps

    async def async_get_raw_dps(self) -> dict[str, Any] | None:
        async with self._io_lock:
            return await self._async_get_dps_payload()

    async def async_send_command(self, dp_id: str, value: Any, verify: bool = True) -> bool:
        async with self._io_lock:
            device = self._get_device()
            try:
                response = await self._async_in_thread(device.set_value, dp_id, value)
            except TimeoutError:
                if not verify:
                    return False
                response = None
            except Exception as err:
                LOGGER.warning("Command to DP %s raised error: %s", dp_id, err)
                return False

            if isinstance(response, dict) and "Error" in response:
                LOGGER.warning("Command to DP %s failed: %s", dp_id, response["Error"])
                return False

            if not verify:
                return True

            verdict = await self._async_verify_command(dp_id, value)
            if verdict is not False:
                return True

        LOGGER.warning("Command accepted but not reflected in status for DP %s.", dp_id)
        return False

    async def _async_verify_command(self, dp_id: str, expected: Any) -> bool | None:
        saw_dp = False
        reads_without_dp = 0
        for _ in range(COMMAND_VERIFY_RETRIES):
            await asyncio.sleep(COMMAND_VERIFY_DELAY_S)
            dps = await self._async_get_dps_payload()
            if dps is None:
                continue
            if dp_id not in dps:
                reads_without_dp += 1
                # Write-only DPs (like DP 140) are omitted from status(); stop early
                if reads_without_dp >= 2:
                    break
                continue
            saw_dp = True
            if _values_match(dps.get(dp_id), expected):
                return True

        if not saw_dp:
            return None
        return False

    async def async_reboot(self) -> bool:
        for payload in (True, 1, "1"):
            if await self.async_send_command(DP_REBOOT, payload, verify=False):
                return True
        return False