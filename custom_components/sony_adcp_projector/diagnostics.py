"""Diagnostics support."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from . import SonyProjectorConfigEntry
from .const import CONF_SERIAL

TO_REDACT = {CONF_HOST, CONF_PASSWORD, CONF_SERIAL, "serial", "mac_address", "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SonyProjectorConfigEntry
) -> dict[str, Any]:
    """Return diagnostics, including the full capability probe result.

    The capability list is the most useful thing to attach to a bug report or
    a "please support my model" request.
    """
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data
    return {
        "entry": async_redact_data(
            {
                "data": dict(entry.data),
                "options": dict(entry.options),
                "unique_id": entry.unique_id,
            },
            TO_REDACT,
        ),
        "identity": async_redact_data(asdict(coordinator.identity), TO_REDACT),
        "capabilities": coordinator.capabilities.as_dict(),
        "state": None
        if data is None
        else {
            "power": data.power.value if data.power else None,
            "input": data.input,
            "signal": data.signal,
            "errors": data.errors,
            "warnings": data.warnings,
            "timers": data.timers,
            "values": data.values,
        },
        "last_update_success": coordinator.last_update_success,
    }
