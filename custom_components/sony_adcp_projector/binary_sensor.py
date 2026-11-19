"""Binary sensors for projector errors and warnings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SonyProjectorConfigEntry
from .coordinator import ProjectorData, SonyProjectorCoordinator
from .entity import SonyProjectorEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class SonyBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a projector problem sensor."""

    codes_fn: Callable[[ProjectorData], list[str]]


BINARY_SENSORS: tuple[SonyBinarySensorDescription, ...] = (
    SonyBinarySensorDescription(
        key="error",
        translation_key="error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        codes_fn=lambda data: data.errors,
    ),
    SonyBinarySensorDescription(
        key="warning",
        translation_key="warning",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        codes_fn=lambda data: data.warnings,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonyProjectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        SonyProblemSensor(coordinator, description) for description in BINARY_SENSORS
    )


class SonyProblemSensor(SonyProjectorEntity, BinarySensorEntity):
    """On while the projector reports error/warning codes; codes in attributes."""

    entity_description: SonyBinarySensorDescription

    def __init__(
        self, coordinator: SonyProjectorCoordinator, description: SonyBinarySensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return bool(self.entity_description.codes_fn(self.coordinator.data))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"codes": self.entity_description.codes_fn(self.coordinator.data)}
