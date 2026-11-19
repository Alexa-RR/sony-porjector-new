"""Buttons: lens motor steps and one-shot ADCP operations."""

from __future__ import annotations

import re
from collections.abc import Iterable

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SonyProjectorConfigEntry
from .adcp import CommandInfo
from .catalog import LENS_KEYS, Feature
from .coordinator import SonyProjectorCoordinator
from .entity import SonyFeatureEntity, SonyProjectorEntity, async_setup_features

PARALLEL_UPDATES = 1

_CUSTOM_RE = re.compile(r"^custom(\d+)$")


def choice_label(choice: str) -> str:
    """``custom3`` -> ``3``; other choices are prettified."""
    if match := _CUSTOM_RE.match(choice):
        return match.group(1)
    return choice.replace("_", " ")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonyProjectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(SonyKeyButton(coordinator, key) for key in LENS_KEYS)

    def factory(feature: Feature, info: CommandInfo) -> Iterable[ButtonEntity]:
        if not info.is_exec:
            return
        if info.choices:
            for choice in info.choices:
                yield SonyExecButton(coordinator, feature, info, choice)
        else:
            yield SonyExecButton(coordinator, feature, info)

    async_setup_features(entry, async_add_entities, factory)


class SonyKeyButton(SonyProjectorEntity, ButtonEntity):
    """Send one remote-control key (lens focus/zoom/shift step)."""

    def __init__(self, coordinator: SonyProjectorCoordinator, key: str) -> None:
        super().__init__(coordinator, f"key_{key}")
        self._key = key
        self._attr_translation_key = key

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.fully_on

    async def async_press(self) -> None:
        await self.coordinator.async_run(self.coordinator.client.async_key(self._key))


class SonyExecButton(SonyFeatureEntity, ButtonEntity):
    """Run a ``menu_exec`` command, e.g. save Picture Position 2."""

    def __init__(
        self,
        coordinator: SonyProjectorCoordinator,
        feature: Feature,
        info: CommandInfo,
        choice: str | None = None,
    ) -> None:
        super().__init__(
            coordinator, feature, info, key=f"{feature.key}_{choice}" if choice else None
        )
        self._choice = choice
        if choice is not None:
            self._attr_translation_placeholders = {"choice": choice_label(choice)}
            if not feature.tkey:
                self._attr_name = f"{self._attr_name} {choice_label(choice)}"

    async def async_press(self) -> None:
        await self.coordinator.async_run(
            self.coordinator.client.async_execute(
                self.feature.command, self._choice, self.feature.suffix
            )
        )
