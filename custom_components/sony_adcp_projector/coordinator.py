"""Coordinator: polling, SDAP push, capability probing and writes."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .adcp import (
    AdcpAuthenticationError,
    AdcpClient,
    AdcpCommandError,
    AdcpError,
    AdcpOutcomeUnknownError,
    CommandInfo,
    PowerStatus,
    ProjectorIdentity,
    SdapAdvertisement,
)
from .catalog import FEATURES, Feature, extra_feature
from .const import (
    CATALOG_VERSION,
    CONF_EXTRA_COMMANDS,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    SLOW_REFRESH,
    STANDBY_INTERVAL,
    STORAGE_VERSION,
    TRANSITION_INTERVAL,
)

if TYPE_CHECKING:
    from . import SonyProjectorConfigEntry

_LOGGER = logging.getLogger(__name__)

INPUT_KEY = "input"


@dataclass(slots=True)
class ProjectorData:
    """Snapshot of the projector state."""

    power: PowerStatus | None = None
    input: str | None = None
    signal: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timers: dict[str, int] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)

    @property
    def is_on(self) -> bool:
        return self.power is not None and self.power.is_on

    @property
    def fully_on(self) -> bool:
        return self.power is PowerStatus.ON


@dataclass(slots=True)
class Capabilities:
    """What the projector told us it supports (persisted per entry)."""

    supported: dict[str, CommandInfo] = field(default_factory=dict)
    unsupported: set[str] = field(default_factory=set)
    catalog_version: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "catalog_version": self.catalog_version,
            "supported": {key: info.as_dict() for key, info in self.supported.items()},
            "unsupported": sorted(self.unsupported),
        }

    @classmethod
    def from_dict(cls, data: Any) -> Capabilities:
        caps = cls()
        if not isinstance(data, dict):
            return caps
        for key, info in (data.get("supported") or {}).items():
            try:
                caps.supported[key] = CommandInfo.from_dict(info)
            except (KeyError, TypeError, ValueError):
                continue
        caps.unsupported = {str(k) for k in data.get("unsupported") or ()}
        caps.catalog_version = int(data.get("catalog_version") or 0)
        return caps


type CapabilityListener = Callable[[set[str]], None]


class SonyProjectorCoordinator(DataUpdateCoordinator[ProjectorData]):
    """Owns the ADCP client and everything the entities need."""

    config_entry: SonyProjectorConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SonyProjectorConfigEntry,
        client: AdcpClient,
        identity: ProjectorIdentity,
    ) -> None:
        self.scan_interval = timedelta(
            seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=STANDBY_INTERVAL,
            always_update=False,
        )
        self.client = client
        self.identity = identity
        self.unique_id: str = entry.unique_id or entry.entry_id
        self.capabilities = Capabilities()
        self.features: dict[str, Feature] = {f.key: f for f in FEATURES}
        for spec in entry.options.get(CONF_EXTRA_COMMANDS, []):
            if (feature := extra_feature(spec)) is not None:
                self.features.setdefault(feature.key, feature)
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._capability_listeners: list[CapabilityListener] = []
        self._last_slow: datetime | None = None
        self._last_sdap_power: int | None = None
        self._probe_pending = True

    # ------------------------------------------------------------------ #
    # Device registry
    # ------------------------------------------------------------------ #
    @property
    def device_info(self) -> DeviceInfo:
        host = self.config_entry.data[CONF_HOST]
        info = DeviceInfo(
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer=MANUFACTURER,
            model=self.identity.model,
            name=self.config_entry.title,
            serial_number=self.identity.serial,
            sw_version=self.identity.main_firmware,
            configuration_url=f"http://{host}",
        )
        if self.identity.mac_address:
            info["connections"] = {(dr.CONNECTION_NETWORK_MAC, self.identity.mac_address)}
        return info

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def _async_setup(self) -> None:
        stored = await self._store.async_load()
        self.capabilities = Capabilities.from_dict(stored)
        if self.capabilities.catalog_version != CATALOG_VERSION:
            # New candidates may have been added; keep what we know is supported.
            self.capabilities.unsupported.clear()

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self.client.async_close()

    # ------------------------------------------------------------------ #
    # Capabilities
    # ------------------------------------------------------------------ #
    def supported_features(self) -> Iterable[tuple[Feature, CommandInfo]]:
        for key, info in self.capabilities.supported.items():
            if (feature := self.features.get(key)) is not None:
                yield feature, info

    @property
    def input_info(self) -> CommandInfo | None:
        return self.capabilities.supported.get(INPUT_KEY)

    @callback
    def async_add_capability_listener(self, listener: CapabilityListener) -> Callable[[], None]:
        self._capability_listeners.append(listener)
        return lambda: self._capability_listeners.remove(listener)

    async def async_probe(self, *, force: bool = False) -> set[str]:
        """Ask the projector which commands it supports; return newly found keys."""
        caps = self.capabilities
        if force:
            caps.unsupported.clear()
        candidates: list[tuple[str, str, str | None]] = [(INPUT_KEY, INPUT_KEY, None)]
        candidates += [(f.key, f.command, f.suffix) for f in self.features.values()]
        new: set[str] = set()
        complete = True
        for key, command, suffix in candidates:
            if not force and (key in caps.unsupported or key in caps.supported):
                continue
            try:
                info = await self.client.async_get_info(command, suffix)
            except AdcpCommandError as err:
                if err.unsupported:
                    caps.unsupported.add(key)
                    caps.supported.pop(key, None)
                else:
                    complete = False  # inactive right now; try again later
                continue
            if caps.supported.get(key) != info:
                new.add(key)
            caps.supported[key] = info
            caps.unsupported.discard(key)
        if complete:
            caps.catalog_version = CATALOG_VERSION
            self._probe_pending = False
        await self._store.async_save(caps.as_dict())
        _LOGGER.debug(
            "Probe finished: %d supported, %d unsupported, new=%s",
            len(caps.supported),
            len(caps.unsupported),
            sorted(new),
        )
        if new:
            for listener in list(self._capability_listeners):
                listener(new)
        return new

    # ------------------------------------------------------------------ #
    # Polling
    # ------------------------------------------------------------------ #
    async def _async_update_data(self) -> ProjectorData:
        try:
            return await self._async_fetch()
        except AdcpAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except AdcpError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={"error": str(err)},
            ) from err

    async def _async_fetch(self) -> ProjectorData:
        client = self.client
        previous = self.data or ProjectorData()
        data = ProjectorData(timers=previous.timers)
        data.power = await client.async_get_power_status()
        data.errors = await self._optional(client.async_get_errors(), [])
        data.warnings = await self._optional(client.async_get_warnings(), [])

        now = dt_util.utcnow()
        if self._last_slow is None or now - self._last_slow >= SLOW_REFRESH:
            data.timers = await self._optional(client.async_get_timers(), previous.timers)
            self._last_slow = now

        if data.power is PowerStatus.ON:
            if self._probe_pending or not self.capabilities.supported:
                await self.async_probe()
            data.input = await self._optional(client.async_get(INPUT_KEY), None)
            signal = await self._optional(client.async_get("signal"), None)
            data.signal = str(signal) if signal is not None else None
            for feature, _info in self.supported_features():
                if not feature.poll or _info.is_exec:
                    continue
                data.values[feature.key] = await self._optional(
                    client.async_get(feature.command, feature.suffix), None
                )

        self._schedule_next(data.power)
        return data

    @staticmethod
    async def _optional[T](coro: Coroutine[Any, Any, T], default: Any) -> T | Any:
        try:
            return await coro
        except AdcpCommandError:
            return default

    def _schedule_next(self, power: PowerStatus | None) -> None:
        if power is not None and power.is_transitioning:
            self.update_interval = TRANSITION_INTERVAL
        elif power is PowerStatus.ON:
            self.update_interval = self.scan_interval
        else:
            self.update_interval = STANDBY_INTERVAL

    # ------------------------------------------------------------------ #
    # SDAP push
    # ------------------------------------------------------------------ #
    @callback
    def async_handle_advertisement(self, adv: SdapAdvertisement) -> None:
        """React to an SDAP advertisement from our projector."""
        entry = self.config_entry
        if adv.host != entry.data[CONF_HOST]:
            _LOGGER.info("Projector %s moved to %s", self.unique_id, adv.host)
            self.hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_HOST: adv.host}
            )
            self.hass.async_create_task(
                self.client.async_update_host(adv.host, entry.data.get(CONF_PORT))
            )
            self._last_sdap_power = None
        if adv.power_raw != self._last_sdap_power:
            first = self._last_sdap_power is None
            self._last_sdap_power = adv.power_raw
            if not first:
                self.hass.async_create_task(self.async_request_refresh())

    # ------------------------------------------------------------------ #
    # Writes (used by entities and services)
    # ------------------------------------------------------------------ #
    async def async_run(
        self,
        coro: Coroutine[Any, Any, Any],
        *,
        refresh: bool = True,
    ) -> Any:
        """Run a client call, translating errors for the UI."""
        try:
            result = await coro
        except AdcpCommandError as err:
            key = {
                "err_val": "invalid_value",
                "err_inactive": "command_inactive",
                "err_cmd": "command_unsupported",
                "err_option": "command_unsupported",
            }.get(err.code, "command_failed")
            exc = ServiceValidationError if key == "invalid_value" else HomeAssistantError
            raise exc(
                translation_domain=DOMAIN,
                translation_key=key,
                translation_placeholders={"command": err.command, "code": err.code},
            ) from err
        except AdcpAuthenticationError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except AdcpOutcomeUnknownError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="outcome_unknown"
            ) from err
        except AdcpError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={"error": str(err)},
            ) from err
        if refresh:
            await self.async_request_refresh()
        return result

    async def async_set_feature(self, feature: Feature, value: str | int | float) -> None:
        await self.async_run(
            self.client.async_set(feature.command, value, feature.suffix), refresh=False
        )
        if self.data is not None:
            self.data.values[feature.key] = value
            self.async_update_listeners()
        # Other settings often change with it (e.g. picture mode presets).
        await self.async_request_refresh()

    async def async_set_power(self, on: bool) -> None:
        await self.async_run(self.client.async_power(on), refresh=False)
        self.update_interval = TRANSITION_INTERVAL
        await self.async_request_refresh()
