from __future__ import annotations

from enum import StrEnum

DOMAIN = "de_ev_charger"

CONF_DEVICE_ID = "device_id"
CONF_LOCAL_KEY = "local_key"
CONF_IP = "ip_address"
CONF_VERSION = "version"
CONF_MAC = "mac"

# Base interval in seconds (used as the anchor for adaptive polling)
UPDATE_INTERVAL = 60
MIN_INTERVAL_S = 15
MAX_INTERVAL_S = 300

# Adaptive polling multipliers relative to UPDATE_INTERVAL (60s base)
CHARGING_FACTOR = 0.5      # 30s while charging / waiting
PLUGGED_IN_FACTOR = 1.0    # 60s while plugged in / paused / charged
IDLE_FACTOR = 2.0          # 120s while idle / fault
ASLEEP_FACTOR = 3.0        # 180s while asleep

# Socket & command verification tuning
TUYA_CONTROL_PORT = 6668
SOCKET_TIMEOUT_S = 5
SOCKET_RETRY_LIMIT = 1
SOCKET_RETRY_DELAY_S = 1
IO_TIMEOUT_S = 20
COMMAND_VERIFY_RETRIES = 6
COMMAND_VERIFY_DELAY_S = 1.0

# Recovery & fault diagnosis tuning
REDISCOVERY_SCAN_SECONDS = 8
REDISCOVERY_COOLDOWN_SECONDS = 120
FAULT_DIAGNOSIS_COOLDOWN_SECONDS = 300
UNDECRYPTABLE_FAILURES_BEFORE_REAUTH = 3
UNDECRYPTABLE_GRACE_SECONDS = 600

# Data Points
DP_WORK_STATE = "101"
DP_METRICS = "102"
DP_ALARM = "104"
DP_CHARGE_HISTORY = "105"
DP_CHARGER_INFO = "106"
DP_ADJUST_CURRENT = "107"
DP_WORK_STATE_DEBUG = "109"
DP_SINGLE_PHASE = "110"
DP_DEBUG = "111"
DP_DO_CHARGE = "140"
DP_REBOOT = "142"
DP_CHARGE_CURRENT = "150"
DP_MAX_CURRENT_CFG = "152"
DP_LIVE_STATUS_TEXT = "153"
DP_PRODUCT_VARIANT = "157"
DP_HEARTBEAT = "188"
DP_NUM = "189"
DP_PLUG_CHARGE = "190"

# Known numeric DP 101 states
WORK_STATE_READY_TO_CHARGE = 200
WORK_STATE_CODE_CHARGING = 300

# Friendly status map from DP 109
STATUS_MAP: dict[str, str] = {
    "SLEEP": "sleep",
    "IDLE": "idle",
    "IDLEINS": "plugged_in",
    "WORKING": "charging",
    "WAIT": "waiting",
    "ERRORPAUSE": "fault",
    "PAUSE": "paused",
    "STOP": "charged",
}
STATUS_OPTIONS: tuple[str, ...] = tuple(dict.fromkeys(STATUS_MAP.values()))


class ConnectionFault(StrEnum):
    OK = "ok"
    UNREACHABLE = "unreachable"
    REFUSED = "refused"
    UNDECRYPTABLE = "undecryptable"