"""The Sony Projector (ADCP) integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import discovery_flow
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .adcp import (
    AdcpAuthenticationError,
    AdcpClient,
    AdcpError,
    SdapAdvertisement,
    SdapListener,
)
from .const import DATA_SDAP, DOMAIN, PLATFORMS, STORAGE_VERSION
from .coordinator import SonyProjectorCoordinator
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass(slots=True)
class SonyProjectorRuntimeData:
    """Objects owned by a loaded config entry."""

    client: AdcpClient
    coordinator: SonyProjectorCoordinator


type SonyProjectorConfigEntry = ConfigEntry[SonyProjectorRuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register actions and start listening for SDAP advertisements."""
    async_setup_services(hass)
    await async_get_sdap_listener(hass)
    return True


async def async_get_sdap_listener(hass: HomeAssistant) -> SdapListener | None:
    """Return the shared SDAP listener, starting it on first use."""
    if (listener := hass.data.get(DATA_SDAP)) is not None:
        return listener
    listener = SdapListener()
    try:
        await listener.async_start()
    except OSError as err:
        _LOGGER.warning(
            "Cannot listen for Sony SDAP advertisements on UDP %s (%s); "
            "discovery and instant power updates are disabled",
            listener.port,
            err,
        )
        return None
    hass.data[DATA_SDAP] = listener
    announced: set[str] = set()

    @callback
    def _discovered(adv: SdapAdvertisement) -> None:
        if not adv.serial or adv.serial in announced:
            return
        for entry in hass.config_entries.async_entries(DOMAIN, include_ignore=True):
            if entry.unique_id == adv.serial:
                return
        announced.add(adv.serial)
        discovery_flow.async_create_flow(
            hass,
            DOMAIN,
            context={"source": SOURCE_INTEGRATION_DISCOVERY},
            data={"host": adv.host, "serial": adv.serial, "model": adv.model},
        )

    listener.subscribe(_discovered)

    @callback
    def _stop(_: Event) -> None:
        listener.stop()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop)
    return listener


async def async_setup_entry(hass: HomeAssistant, entry: SonyProjectorConfigEntry) -> bool:
    """Set up a projector from a config entry."""
    client = AdcpClient(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data.get(CONF_PASSWORD),
    )
    try:
        identity = await client.async_get_identity()
    except AdcpAuthenticationError as err:
        await client.async_close()
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="auth_failed"
        ) from err
    except AdcpError as err:
        await client.async_close()
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"host": entry.data[CONF_HOST], "error": str(err)},
        ) from err

    coordinator = SonyProjectorCoordinator(hass, entry, client, identity)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = SonyProjectorRuntimeData(client=client, coordinator=coordinator)

    if (listener := hass.data.get(DATA_SDAP)) is not None:

        @callback
        def _advertisement(adv: SdapAdvertisement) -> None:
            if adv.serial == coordinator.unique_id or (
                adv.serial is None and adv.host == entry.data[CONF_HOST]
            ):
                coordinator.async_handle_advertisement(adv)

        entry.async_on_unload(listener.subscribe(_advertisement))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SonyProjectorConfigEntry) -> bool:
    """Unload a config entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.coordinator.async_shutdown()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: SonyProjectorConfigEntry) -> None:
    """Delete stored capabilities when the entry is removed."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
