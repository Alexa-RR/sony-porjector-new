"""Fixtures for Sony Projector (ADCP) tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sony_adcp_projector.const import CONF_MODEL, CONF_SERIAL, DOMAIN

from .fake_projector import FakeProjector

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations."""


@pytest.fixture(autouse=True)
def no_sdap(request: pytest.FixtureRequest) -> Generator[None]:
    """Do not bind the real UDP port during tests (opt out with ``real_sdap``)."""
    if "real_sdap" in request.keywords:
        yield
        return
    with patch(
        "custom_components.sony_adcp_projector.adcp.discovery.SdapListener.async_start",
        autospec=True,
    ):
        yield


@pytest.fixture
async def projector(socket_enabled: None) -> AsyncGenerator[FakeProjector]:
    fake = FakeProjector()
    await fake.start()
    yield fake
    await fake.stop()


@pytest.fixture
def mock_config_entry(projector: FakeProjector) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="VPL-GTZ380",
        unique_id="12345",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: projector.port,
            CONF_SERIAL: "0012345",
            CONF_MODEL: "VPL-GTZ380",
        },
    )
