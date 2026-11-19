"""Integration-wide actions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import probatio as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service

from .adcp import decode_response
from .const import (
    ATTR_COMMAND,
    ATTR_CONFIG_ENTRY_ID,
    DOMAIN,
    SERVICE_PROBE_CAPABILITIES,
    SERVICE_SEND_COMMAND,
)

if TYPE_CHECKING:
    from . import SonyProjectorConfigEntry

_ENTRY_SCHEMA = {vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string}

SEND_COMMAND_SCHEMA = vol.Schema(
    {
        **_ENTRY_SCHEMA,
        vol.Required(ATTR_COMMAND): vol.All(cv.string, vol.Length(min=1, max=500)),
    }
)
PROBE_SCHEMA = vol.Schema(_ENTRY_SCHEMA)


def _get_entry(hass: HomeAssistant, call: ServiceCall) -> SonyProjectorConfigEntry:
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    entry: SonyProjectorConfigEntry | None = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_found",
            translation_placeholders={"entry_id": entry_id},
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_loaded",
            translation_placeholders={"title": entry.title},
        )
    return entry


def _is_read_only(command: str) -> bool:
    tokens = command.split()
    return "?" in tokens or "--info" in tokens or "--range" in tokens


async def _async_send_command(call: ServiceCall) -> ServiceResponse:
    entry = _get_entry(call.hass, call)
    command: str = call.data[ATTR_COMMAND].strip()
    if not command.isascii() or not command.isprintable():
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid_command")
    coordinator = entry.runtime_data.coordinator
    read_only = _is_read_only(command)
    reply: str = await coordinator.async_run(
        entry.runtime_data.client.async_send_raw(command, idempotent=read_only),
        refresh=not read_only,
    )
    decoded: Any = decode_response(reply)
    return {"command": command, "response": reply, "value": decoded}


async def _async_probe(call: ServiceCall) -> ServiceResponse:
    entry = _get_entry(call.hass, call)
    coordinator = entry.runtime_data.coordinator
    if coordinator.data is None or not coordinator.data.fully_on:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="probe_requires_power"
        )
    new = await coordinator.async_run(coordinator.async_probe(force=True), refresh=True)
    caps = coordinator.capabilities
    return {
        "new": sorted(new),
        "supported": {
            key: {
                "type": info.type,
                **({"choices": list(info.choices)} if info.choices else {}),
                **(
                    {"min": info.minimum, "max": info.maximum, "step": info.step}
                    if info.minimum is not None
                    else {}
                ),
            }
            for key, info in sorted(caps.supported.items())
        },
        "unsupported": sorted(caps.unsupported),
    }


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's actions."""
    # Raw commands can change any setting, so only administrators may call it.
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_SEND_COMMAND,
        _async_send_command,
        schema=SEND_COMMAND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PROBE_CAPABILITIES,
        _async_probe,
        schema=PROBE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
