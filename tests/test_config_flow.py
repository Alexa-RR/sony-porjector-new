"""Config, options, reauth and reconfigure flow tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sony_adcp_projector import async_get_sdap_listener
from custom_components.sony_adcp_projector.adcp import SdapAdvertisement
from custom_components.sony_adcp_projector.const import (
    CONF_EXTRA_COMMANDS,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)

from .fake_projector import FakeProjector

pytestmark = pytest.mark.usefixtures("socket_enabled")


@pytest.fixture(autouse=True)
def no_wait() -> None:
    with (
        patch("custom_components.sony_adcp_projector.config_flow.DISCOVERY_WAIT", 0),
        patch("custom_components.sony_adcp_projector.async_setup_entry", return_value=True),
    ):
        yield


async def test_manual_no_auth(hass: HomeAssistant, projector: FakeProjector) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: projector.port}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "VPL-GTZ380"
    assert result["result"].unique_id == "12345"
    assert CONF_PASSWORD not in result["data"]


async def test_manual_with_password(hass: HomeAssistant) -> None:
    fake = FakeProjector(password="Projector")
    await fake.start()
    try:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: fake.port}
        )
        assert result["step_id"] == "password"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "nope"}
        )
        assert result["errors"] == {"base": "invalid_auth"}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "Projector"}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_PASSWORD] == "Projector"
    finally:
        await fake.stop()


async def test_cannot_connect_then_recover(hass: HomeAssistant, projector: FakeProjector) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: 1}
    )
    assert result["errors"] == {"base": "cannot_connect"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: projector.port}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_already_configured_updates_host(
    hass: HomeAssistant, projector: FakeProjector
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="12345", data={CONF_HOST: "10.0.0.9", CONF_PORT: 1}
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: projector.port}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "127.0.0.1"


async def test_pick_discovered(hass: HomeAssistant, projector: FakeProjector) -> None:
    listener = await async_get_sdap_listener(hass)
    assert listener is not None
    listener.seen["127.0.0.1"] = SdapAdvertisement(
        "127.0.0.1", "SONY", "VPL-GTZ380", "12345", 0, None
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["step_id"] == "pick"
    with patch("custom_components.sony_adcp_projector.config_flow.DEFAULT_PORT", projector.port):
        flow = hass.config_entries.flow._progress[result["flow_id"]]
        flow._port = projector.port
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device": "127.0.0.1"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_integration_discovery(hass: HomeAssistant, projector: FakeProjector) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={"host": "127.0.0.1", "serial": "12345", "model": "VPL-GTZ380"},
    )
    assert result["step_id"] == "discovery_confirm"
    flow = hass.config_entries.flow._progress[result["flow_id"]]
    flow._port = projector.port
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_reauth(hass: HomeAssistant) -> None:
    fake = FakeProjector(password="new")
    await fake.start()
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="12345",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: fake.port, CONF_PASSWORD: "old"},
    )
    entry.add_to_hass(hass)
    try:
        result = await entry.start_reauth_flow(hass)
        assert result["step_id"] == "reauth_confirm"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "bad"}
        )
        assert result["errors"] == {"base": "invalid_auth"}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "new"}
        )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "reauth_successful"
        assert entry.data[CONF_PASSWORD] == "new"
    finally:
        await fake.stop()


async def test_reconfigure(hass: HomeAssistant, projector: FakeProjector) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="12345", data={CONF_HOST: "10.0.0.9", CONF_PORT: 1}
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: projector.port}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_PORT] == projector.port


async def test_reconfigure_wrong_device(hass: HomeAssistant, projector: FakeProjector) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="99999", data={CONF_HOST: "10.0.0.9", CONF_PORT: 1}
    )
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: projector.port}
    )
    assert result["reason"] == "wrong_device"


async def test_options(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="12345", data={CONF_HOST: "10.0.0.9", CONF_PORT: 1}
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 20, CONF_EXTRA_COMMANDS: ["Bad Name"]}
    )
    assert result["errors"] == {CONF_EXTRA_COMMANDS: "invalid_command"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL: 20, CONF_EXTRA_COMMANDS: ["my_setting", "other --hdmi1"]},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_SCAN_INTERVAL: 20,
        CONF_EXTRA_COMMANDS: ["my_setting", "other --hdmi1"],
    }


async def test_pick_manual_option(hass: HomeAssistant, projector: FakeProjector) -> None:
    listener = await async_get_sdap_listener(hass)
    listener.seen["192.0.2.50"] = SdapAdvertisement(
        "192.0.2.50", "SONY", "VPL-GTZ380", "777", 0, None
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["step_id"] == "pick"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"device": "manual"})
    assert result["step_id"] == "manual"


async def test_no_serial_aborts(hass: HomeAssistant) -> None:
    fake = FakeProjector(serial=None)
    await fake.start()
    try:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: fake.port}
        )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "no_serial"
    finally:
        await fake.stop()


async def test_password_step_connection_lost(hass: HomeAssistant) -> None:
    fake = FakeProjector(password="Projector")
    await fake.start()
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: fake.port}
    )
    assert result["step_id"] == "password"
    await fake.stop()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "Projector"}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_password_appears_between_steps(hass: HomeAssistant) -> None:
    """Greeting said NOKEY, but auth got enabled before identity was read."""
    fake = FakeProjector()
    await fake.start()
    try:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        with patch(
            "custom_components.sony_adcp_projector.config_flow.async_probe_requires_password",
            return_value=False,
        ):
            fake.password = "Projector"
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: fake.port}
            )
        assert result["step_id"] == "password"
    finally:
        await fake.stop()


async def test_reauth_cannot_connect(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="12345",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: 1, CONF_PASSWORD: "old"},
    )
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PASSWORD: "x"})
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reconfigure_errors(hass: HomeAssistant) -> None:
    fake = FakeProjector(password="Projector")
    await fake.start()
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="12345",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: fake.port, CONF_PASSWORD: "Projector"},
    )
    entry.add_to_hass(hass)
    try:
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: fake.port}
        )
        assert result["errors"] == {CONF_PASSWORD: "password_required"}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "127.0.0.1", CONF_PORT: fake.port, CONF_PASSWORD: "bad"},
        )
        assert result["errors"] == {"base": "invalid_auth"}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: 1}
        )
        assert result["errors"] == {"base": "cannot_connect"}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "127.0.0.1", CONF_PORT: fake.port, CONF_PASSWORD: "Projector"},
        )
        assert result["reason"] == "reconfigure_successful"
        assert entry.data[CONF_PASSWORD] == "Projector"
    finally:
        await fake.stop()
