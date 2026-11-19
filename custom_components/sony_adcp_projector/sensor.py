"""Sensors: power status, input signal, hour counters and status commands."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SonyProjectorConfigEntry
from .adcp import CommandInfo, PowerStatus
from .catalog import Feature
from .coordinator import ProjectorData, SonyProjectorCoordinator
from .entity import SonyFeatureEntity, SonyProjectorEntity, async_setup_features

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class SonySensorDescription(SensorEntityDescription):
    """Describes a fixed projector sensor."""

    value_fn: Callable[[ProjectorData], Any]
    available_fn: Callable[[ProjectorData], bool] = lambda data: True


SENSORS: tuple[SonySensorDescription, ...] = (
    SonySensorDescription(
        key="power_status",
        translation_key="power_status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.value for status in PowerStatus],
        value_fn=lambda data: data.power.value if data.power else None,
    ),
    SonySensorDescription(
        key="signal",
        translation_key="signal",
        value_fn=lambda data: data.signal,
        available_fn=lambda data: data.fully_on,
    ),
    SonySensorDescription(
        key="operation_hours",
        translation_key="operation_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.timers.get("operation"),
        available_fn=lambda data: "operation" in data.timers,
    ),
    SonySensorDescription(
        key="light_source_hours",
        translation_key="light_source_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.timers.get("light_src"),
        available_fn=lambda data: "light_src" in data.timers,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonyProjectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(SonyProjectorSensor(coordinator, description) for description in SENSORS)

    def factory(feature: Feature, info: CommandInfo) -> Iterable[SensorEntity]:
        if info.is_status:
            yield SonyStatusSensor(coordinator, feature, info)

    async_setup_features(entry, async_add_entities, factory)


class SonyProjectorSensor(SonyProjectorEntity, SensorEntity):
    """A fixed sensor."""

    entity_description: SonySensorDescription

    def __init__(
        self, coordinator: SonyProjectorCoordinator, description: SonySensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        return super().available and self.entity_description.available_fn(self.coordinator.data)

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)


class SonyStatusSensor(SonyFeatureEntity, SensorEntity):
    """A read-only ``sys_stat`` command."""

    @property
    def native_value(self) -> Any:
        value = self.value
        if isinstance(value, list | dict):
            return str(value)[:255]
        return value
