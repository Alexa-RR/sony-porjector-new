"""Media player: power and input selection."""

from __future__ import annotations

import re

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SonyProjectorConfigEntry
from .adcp import PowerStatus
from .coordinator import SonyProjectorCoordinator
from .entity import SonyProjectorEntity

PARALLEL_UPDATES = 1

_SOURCE_NAMES = {
    "hdmi": "HDMI",
    "dp": "DisplayPort",
    "displayport": "DisplayPort",
    "hdbaset": "HDBaseT",
    "dvi": "DVI",
    "rgb": "RGB",
    "video": "Video",
    "svideo": "S-Video",
    "usb_a": "USB-A",
    "usb_b": "USB-B",
    "sdi": "SDI",
    "option": "Option",
}
_SOURCE_RE = re.compile(r"^([a-z_]+?)(\d*)$")
# Dual-link inputs such as the VPL-GTZ380's "dp1_2" (DisplayPort 1+2).
_DUAL_RE = re.compile(r"^([a-z]+)(\d+)_(\d+)$")


def source_name(raw: str) -> str:
    """``hdmi1`` -> ``HDMI 1``, ``dp2`` -> ``DisplayPort 2``, ``dp1_2`` -> ``DisplayPort 1+2``."""
    if match := _DUAL_RE.match(raw):
        prefix, first, second = match.groups()
        if prefix in _SOURCE_NAMES:
            return f"{_SOURCE_NAMES[prefix]} {first}+{second}"
    if match := _SOURCE_RE.match(raw):
        prefix, number = match.groups()
        if prefix in _SOURCE_NAMES:
            return f"{_SOURCE_NAMES[prefix]} {number}".strip()
    return raw.replace("_", " ").title()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonyProjectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([SonyProjectorMediaPlayer(entry.runtime_data.coordinator)])


class SonyProjectorMediaPlayer(SonyProjectorEntity, MediaPlayerEntity):
    """The projector itself."""

    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.TV

    def __init__(self, coordinator: SonyProjectorCoordinator) -> None:
        super().__init__(coordinator, "media_player")
        self._sources: dict[str, str] = {}
        self._update_sources()

    @callback
    def _update_sources(self) -> None:
        info = self.coordinator.input_info
        choices = info.choices if info else ()
        self._sources = {source_name(raw): raw for raw in choices}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def _new_capabilities(keys: set[str]) -> None:
            if "input" in keys:
                self._update_sources()
                self.async_write_ha_state()

        self.async_on_remove(self.coordinator.async_add_capability_listener(_new_capabilities))

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        features = MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF
        if self._sources:
            features |= MediaPlayerEntityFeature.SELECT_SOURCE
        return features

    @property
    def state(self) -> MediaPlayerState:
        return MediaPlayerState.ON if self.coordinator.data.is_on else MediaPlayerState.OFF

    @property
    def source_list(self) -> list[str] | None:
        return list(self._sources) or None

    @property
    def source(self) -> str | None:
        raw = self.coordinator.data.input
        if raw is None or not self.coordinator.data.fully_on:
            return None
        raw = str(raw)
        for name, value in self._sources.items():
            if value == raw:
                return name
        return source_name(raw)

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        power = self.coordinator.data.power
        return {"power_status": power.value if isinstance(power, PowerStatus) else None}

    async def async_turn_on(self) -> None:
        await self.coordinator.async_set_power(True)

    async def async_turn_off(self) -> None:
        await self.coordinator.async_set_power(False)

    async def async_select_source(self, source: str) -> None:
        raw = self._sources.get(source, source)
        await self.coordinator.async_run(self.coordinator.client.async_set("input", raw))
