"""Constants for the Sony Projector (ADCP) integration."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Final

from homeassistant.const import Platform
from homeassistant.util.hass_dict import HassKey

if TYPE_CHECKING:
    from .adcp import SdapListener

DOMAIN: Final = "sony_adcp_projector"
MANUFACTURER: Final = "Sony"
DEFAULT_NAME: Final = "Sony Projector"

CONF_SERIAL: Final = "serial"
CONF_MODEL: Final = "model"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_EXTRA_COMMANDS: Final = "extra_commands"

DEFAULT_SCAN_INTERVAL: Final = 15
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 300

# Polling cadence outside of the "on" state.
STANDBY_INTERVAL: Final = timedelta(seconds=30)
TRANSITION_INTERVAL: Final = timedelta(seconds=2)
# Rarely changing data (hour counters, firmware).
SLOW_REFRESH: Final = timedelta(minutes=10)
DISCOVERY_WAIT: Final = 4.0

STORAGE_VERSION: Final = 1
# Bump whenever catalog.py gains candidates so they are probed again.
CATALOG_VERSION: Final = 1

DATA_SDAP: HassKey[SdapListener] = HassKey(f"{DOMAIN}_sdap")

PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.REMOTE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

SERVICE_SEND_COMMAND: Final = "send_command"
SERVICE_PROBE_CAPABILITIES: Final = "probe_capabilities"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_COMMAND: Final = "command"
