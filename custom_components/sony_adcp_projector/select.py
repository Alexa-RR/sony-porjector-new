"""Multiple-choice ADCP settings (picture mode, aspect, Picture Position…)."""

from __future__ import annotations

from collections.abc import Iterable

from homeassistant.components.select import SelectEntity
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

    def factory(feature: Feature, info: CommandInfo) -> Iterable[SelectEntity]:
        if info.is_select and not info.is_on_off and info.choices:
            yield SonyFeatureSelect(coordinator, feature, info)

    async_setup_features(entry, async_add_entities, factory)


class SonyFeatureSelect(SonyFeatureEntity, SelectEntity):
    """Choices come straight from the projector's ``--info`` range."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._attr_options = list(self.info.choices)

    @property
    def current_option(self) -> str | None:
        value = self.value
        if value is None:
            return None
        value = str(value)
        return value if value in self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_feature(self.feature, option)
