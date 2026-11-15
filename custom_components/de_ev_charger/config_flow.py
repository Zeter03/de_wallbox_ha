from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import device_registry as dr
from tinytuya import scanner

from .client import DeEvChargerClient
from .const import CONF_DEVICE_ID, CONF_IP, CONF_LOCAL_KEY, CONF_MAC, CONF_VERSION, DOMAIN, ConnectionFault

LOGGER = logging.getLogger(__name__)


def _scan_devices() -> dict[str, dict[str, Any]]:
    try:
        devices = scanner.devices(
            verbose=False,
            scantime=4,
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
        LOGGER.debug("UDP device scan failed.", exc_info=True)
        return {}


async def _async_validate_credentials(data: dict[str, Any]) -> str | None:
    """Validate connectivity and return an error key on failure, else None."""
    client = DeEvChargerClient(
        device_id=str(data[CONF_DEVICE_ID]).strip(),
        host=str(data[CONF_IP]).strip(),
        local_key=str(data[CONF_LOCAL_KEY]).strip(),
        version=str(data.get(CONF_VERSION, "3.5")).strip(),
    )
    try:
        await client.async_connect()
        dps = await client.async_get_raw_dps()
        if dps is not None:
            return None
        fault = await client.async_classify_fault()
        if fault == ConnectionFault.REFUSED:
            return "connection_refused"
        if fault == ConnectionFault.UNDECRYPTABLE:
            return "invalid_credentials"
        return "cannot_connect"
    except Exception:
        LOGGER.exception("Unexpected error validating charger configuration.")
        return "cannot_connect"
    finally:
        await client.async_close()


class DeEvChargerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self.discovered: dict[str, dict[str, Any]] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        return self.async_show_menu(
            step_id="user",
            menu_options=["auto", "manual"],
        )

    async def async_step_auto(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            dev_id = user_input[CONF_DEVICE_ID]
            info = self.discovered[dev_id]
            data: dict[str, Any] = {
                CONF_DEVICE_ID: dev_id,
                CONF_IP: info["ip"],
                CONF_LOCAL_KEY: user_input[CONF_LOCAL_KEY].strip(),
                CONF_VERSION: str(info.get("version", "3.5")),
            }
            if info.get("mac"):
                data[CONF_MAC] = dr.format_mac(str(info["mac"]))

            await self.async_set_unique_id(dev_id)
            self._abort_if_unique_id_configured()

            err = await _async_validate_credentials(data)
            if err is None:
                return self.async_create_entry(title="dé EV Charger", data=data)
            errors["base"] = err

        if not self.discovered:
            self.discovered = await self.hass.async_add_executor_job(_scan_devices)

        if not self.discovered:
            return self.async_show_form(
                step_id="manual",
                errors={"base": "no_devices"},
                data_schema=self._get_manual_schema(),
            )

        device_map = {
            did: f"{did} ({info['ip']} - v{info.get('version', '?')})"
            for did, info in self.discovered.items()
        }
        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): vol.In(device_map),
                vol.Required(CONF_LOCAL_KEY): str,
            }
        )
        return self.async_show_form(step_id="auto", data_schema=schema, errors=errors)

    async def async_step_manual(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            dev_id = user_input[CONF_DEVICE_ID].strip()
            await self.async_set_unique_id(dev_id)
            self._abort_if_unique_id_configured()

            err = await _async_validate_credentials(user_input)
            if err is None:
                return self.async_create_entry(title="dé EV Charger", data=user_input)
            errors["base"] = err

        return self.async_show_form(
            step_id="manual",
            data_schema=self._get_manual_schema(user_input),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Allow updating IP or Local Key without deleting history."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            candidate = {**entry.data, **user_input}
            err = await _async_validate_credentials(candidate)
            if err is None:
                return self.async_update_reload_and_abort(entry, data=candidate)
            errors["base"] = err

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._get_manual_schema(user_input or entry.data),
            errors=errors,
        )

    @staticmethod
    def _get_manual_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
        defaults = defaults or {}
        return vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID, default=defaults.get(CONF_DEVICE_ID, "")): str,
                vol.Required(CONF_IP, default=defaults.get(CONF_IP, "")): str,
                vol.Required(CONF_LOCAL_KEY, default=defaults.get(CONF_LOCAL_KEY, "")): str,
                vol.Optional(
                    CONF_VERSION, default=str(defaults.get(CONF_VERSION, "3.5"))
                ): vol.In(["3.3", "3.4", "3.5"]),
            }
        )