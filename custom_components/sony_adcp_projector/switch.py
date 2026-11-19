"""On/off ADCP settings (picture muting, Reality Creation, locks…)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SonyProjectorConfigEntry
from .adcp import CommandInfo
from .catalog import Feature
from .entity import SonyFeatureEntity, async_setup_features

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonyProjectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator

    def factory(feature: Feature, info: CommandInfo) -> Iterable[SwitchEntity]:
        if info.is_on_off:
            yield SonyFeatureSwitch(coordinator, feature, info)

    async_setup_features(entry, async_add_entities, factory)


class SonyFeatureSwitch(SonyFeatureEntity, SwitchEntity):
    """A two-state ADCP menu setting."""

    @property
    def is_on(self) -> bool | None:
        value = self.value
        return None if value is None else str(value).lower() == "on"

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_feature(self.feature, "on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_feature(self.feature, "off")
