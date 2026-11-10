import logging
import json
import time
import tinytuya
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import DOMAIN, CONF_DEVICE_ID, CONF_LOCAL_KEY, CONF_IP, CONF_VERSION, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "switch", "number", "button"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up dé EV Charger from a config entry."""
    dev_id = entry.data[CONF_DEVICE_ID]
    ip = entry.data[CONF_IP]
    key = entry.data[CONF_LOCAL_KEY]
    version = float(entry.data.get(CONF_VERSION, 3.5))

    # We track the work state locally to know when to send heartbeats
    last_work_state = "UNKNOWN"

    def fetch_data():
        nonlocal last_work_state
        try:
            device = tinytuya.OutletDevice(dev_id, ip, key)
            device.set_version(version)
            
            # If the charger is actively charging, send the heartbeat
            # to force the main MCU to push live metrics to the Wi-Fi chip's cache.
            if last_work_state == "WORKING":
                _LOGGER.debug("Charger is WORKING, sending Heartbeat (DP 188)")
                try:
                    device.set_value("188", True)
                    # Give the MCU half a second to reply to the Wi-Fi module with fresh data
                    time.sleep(0.5) 
                except Exception as err:
                    _LOGGER.warning(f"Failed to send Heartbeat: {err}")

            # Now fetch the data (which will contain the refreshed metrics if charging)
            payload = device.status()
            if payload and 'dps' in payload:
                # Update our state tracker for the next cycle
                last_work_state = payload['dps'].get("109", last_work_state)
                return payload['dps']
                
            raise Exception(f"No dps in payload: {payload}")
        except Exception as e:
            raise UpdateFailed(f"Error fetching data: {e}")

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="de_ev_charger",
        update_method=lambda: hass.async_add_executor_job(fetch_data),
        update_interval=timedelta(seconds=UPDATE_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

def send_tuya_command(hass, entry, dp, value):
    """Helper to send a command to the device."""
    dev_id = entry.data[CONF_DEVICE_ID]
    ip = entry.data[CONF_IP]
    key = entry.data[CONF_LOCAL_KEY]
    version = float(entry.data.get(CONF_VERSION, 3.5))

    def _send():
        device = tinytuya.OutletDevice(dev_id, ip, key)
        device.set_version(version)
        device.set_value(dp, value)
        
    return hass.async_add_executor_job(_send)