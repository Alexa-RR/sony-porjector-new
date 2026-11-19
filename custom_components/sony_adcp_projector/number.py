"""Numeric ADCP adjustments (brightness, contrast, light output…)."""

from __future__ import annotations

from collections.abc import Iterable

from homeassistant.components.number import NumberEntity, NumberMode
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

    def factory(feature: Feature, info: CommandInfo) -> Iterable[NumberEntity]:
        if info.is_number:
            yield SonyFeatureNumber(coordinator, feature, info)

    async_setup_features(entry, async_add_entities, factory)


class SonyFeatureNumber(SonyFeatureEntity, NumberEntity):
    """Range and step come from the projector's ``--info`` reply."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        assert self.info.minimum is not None and self.info.maximum is not None
        self._attr_native_min_value = self.info.minimum
        self._attr_native_max_value = self.info.maximum
        self._attr_native_step = self.info.step or 1
        self._attr_mode = NumberMode.BOX if self.entity_category else NumberMode.SLIDER

    @property
    def native_value(self) -> float | None:
        try:
            return float(self.value)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        number: int | float = int(value) if float(value).is_integer() else value
        await self.coordinator.async_set_feature(self.feature, number)
