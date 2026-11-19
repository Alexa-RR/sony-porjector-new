"""Base entities for the Sony Projector (ADCP) integration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SonyProjectorConfigEntry
from .adcp import CommandInfo
from .catalog import Feature
from .coordinator import SonyProjectorCoordinator


class SonyProjectorEntity(CoordinatorEntity[SonyProjectorCoordinator]):
    """Common device info and naming."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SonyProjectorCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.unique_id}_{key}"
        self._attr_device_info = coordinator.device_info


class SonyFeatureEntity(SonyProjectorEntity):
    """An entity backed by one probed ADCP command."""

    def __init__(
        self,
        coordinator: SonyProjectorCoordinator,
        feature: Feature,
        info: CommandInfo,
        key: str | None = None,
    ) -> None:
        super().__init__(coordinator, key or feature.key)
        self.feature = feature
        self.info = info
        if feature.tkey:
            self._attr_translation_key = feature.tkey
        else:
            # User-added command: name it after the command itself.
            label = feature.command.replace("_", " ")
            if feature.suffix:
                label = f"{label} {feature.suffix.removeprefix('--')}"
            self._attr_name = label[:1].upper() + label[1:]
        self._attr_entity_category = feature.entity_category
        self._attr_entity_registry_enabled_default = feature.enabled_default

    @property
    def value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.values.get(self.feature.key)

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return (
            super().available
            and data is not None
            and data.fully_on
            and (self.info.is_exec or self.value is not None)
        )


type FeatureFactory = Callable[[Feature, CommandInfo], Iterable[Entity]]


@callback
def async_setup_features(
    entry: SonyProjectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: FeatureFactory,
) -> None:
    """Add entities for supported features now and whenever new ones are probed."""
    coordinator = entry.runtime_data.coordinator
    added: set[str] = set()

    @callback
    def _add(_: set[str] | None = None) -> None:
        entities: list[Entity] = []
        for feature, info in coordinator.supported_features():
            if feature.key in added:
                continue
            if new := list(factory(feature, info)):
                added.add(feature.key)
                entities.extend(new)
        if entities:
            async_add_entities(entities)

    _add()
    entry.async_on_unload(coordinator.async_add_capability_listener(_add))
