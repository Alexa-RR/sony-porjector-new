"""Remote entity: send any Sony remote-control key code."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    ATTR_NUM_REPEATS,
    DEFAULT_DELAY_SECS,
    RemoteEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SonyProjectorConfigEntry
from .coordinator import SonyProjectorCoordinator
from .entity import SonyProjectorEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonyProjectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([SonyProjectorRemote(entry.runtime_data.coordinator)])


class SonyProjectorRemote(SonyProjectorEntity, RemoteEntity):
    """Key codes such as ``menu``, ``up``, ``enter``, ``lens_focus_far``."""

    _attr_translation_key = "remote"

    def __init__(self, coordinator: SonyProjectorCoordinator) -> None:
        super().__init__(coordinator, "remote")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_power(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_power(False)

    async def async_send_command(self, command: Iterable[str], **kwargs: Any) -> None:
        repeats = int(kwargs.get(ATTR_NUM_REPEATS, 1))
        delay = float(kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS))
        keys = list(command)
        for repeat in range(repeats):
            for index, key in enumerate(keys):
                await self.coordinator.async_run(
                    self.coordinator.client.async_key(key.strip()), refresh=False
                )
                if delay and (repeat < repeats - 1 or index < len(keys) - 1):
                    await asyncio.sleep(delay)
        await self.coordinator.async_request_refresh()
