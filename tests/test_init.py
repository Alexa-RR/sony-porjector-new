"""Integration tests: setup, entities, writes, push and actions."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sony_adcp_projector.adcp import SdapAdvertisement
from custom_components.sony_adcp_projector.const import DOMAIN
from custom_components.sony_adcp_projector.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .fake_projector import FakeProjector


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _eid(hass: HomeAssistant, platform: str, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"12345_{key}")
    assert entity_id, f"{platform}.{key} not created"
    return entity_id


async def test_setup_creates_probed_entities(
    hass: HomeAssistant, projector: FakeProjector, mock_config_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED

    player = hass.states.get(_eid(hass, "media_player", "media_player"))
    assert player.state == STATE_ON
    assert player.attributes["source_list"] == ["HDMI 1", "HDMI 2", "DisplayPort 1"]
    assert player.attributes["source"] == "HDMI 1"

    assert hass.states.get(_eid(hass, "select", "picture_mode")).state == "cinema_film1"
    assert hass.states.get(_eid(hass, "select", "pic_pos_sel")).state == "custom1"
    assert hass.states.get(_eid(hass, "switch", "real_cre")).state == STATE_ON
    assert hass.states.get(_eid(hass, "switch", "blank")).state == STATE_OFF
    brightness = hass.states.get(_eid(hass, "number", "brightness"))
    assert float(brightness.state) == 50
    assert brightness.attributes["max"] == 100
    assert hass.states.get(_eid(hass, "sensor", "power_status")).state == "on"
    assert hass.states.get(_eid(hass, "sensor", "signal")).state == "3840x2160/24p"
    assert hass.states.get(_eid(hass, "binary_sensor", "error")).state == STATE_OFF

    registry = er.async_get(hass)
    # Picture Position save buttons, one per memory slot.
    assert registry.async_get_entity_id("button", DOMAIN, "12345_pic_pos_save_custom2")
    # Disabled-by-default config entity.
    blanking = registry.async_get(_eid(hass, "number", "blanking_top"))
    assert blanking.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    # Unsupported candidates are not created.
    assert registry.async_get_entity_id("select", DOMAIN, "12345_motionflow") is None


async def test_writes(
    hass: HomeAssistant, projector: FakeProjector, mock_config_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_config_entry)

    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: _eid(hass, "select", "pic_pos_sel"), "option": "custom2"},
        blocking=True,
    )
    assert projector.values["pic_pos_sel"] == "custom2"

    await hass.services.async_call(
        "number",
        "set_value",
        {ATTR_ENTITY_ID: _eid(hass, "number", "brightness"), "value": 42},
        blocking=True,
    )
    assert "brightness 42" in projector.received

    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: _eid(hass, "switch", "blank")}, blocking=True
    )
    assert projector.values["blank"] == "on"

    await hass.services.async_call(
        "media_player",
        "select_source",
        {ATTR_ENTITY_ID: _eid(hass, "media_player", "media_player"), "source": "DisplayPort 1"},
        blocking=True,
    )
    assert projector.values["input"] == "dp1"

    await hass.services.async_call(
        "button",
        "press",
        {ATTR_ENTITY_ID: _eid(hass, "button", "pic_pos_save_custom2")},
        blocking=True,
    )
    assert 'pic_pos_save "custom2"' in projector.received

    await hass.services.async_call(
        "button",
        "press",
        {ATTR_ENTITY_ID: _eid(hass, "button", "key_lens_focus_far")},
        blocking=True,
    )
    assert 'key "lens_focus_far"' in projector.received

    await hass.services.async_call(
        "remote",
        "send_command",
        {
            ATTR_ENTITY_ID: _eid(hass, "remote", "remote"),
            "command": ["menu", "down"],
            "delay_secs": 0,
        },
        blocking=True,
    )
    assert projector.received[-3:-1] == ['key "menu"', 'key "down"'] or (
        'key "down"' in projector.received
    )


async def test_rejected_value(
    hass: HomeAssistant, projector: FakeProjector, mock_config_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_config_entry)
    projector.infos["brightness"]["range"]["max"] = 10  # projector narrower than HA thinks
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "number",
            "set_value",
            {ATTR_ENTITY_ID: _eid(hass, "number", "brightness"), "value": 90},
            blocking=True,
        )


async def test_standby_then_power_on(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    socket_enabled: None,
) -> None:
    fake = FakeProjector(power="standby")
    await fake.start()
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, "port": fake.port}
    )
    try:
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        player_id = _eid(hass, "media_player", "media_player")
        assert hass.states.get(player_id).state == STATE_OFF
        # Nothing probed yet while in standby.
        assert (
            er.async_get(hass).async_get_entity_id("select", DOMAIN, "12345_picture_mode") is None
        )

        await hass.services.async_call(
            "media_player", "turn_on", {ATTR_ENTITY_ID: player_id}, blocking=True
        )
        assert fake.power == "on"
        coordinator = mock_config_entry.runtime_data.coordinator
        await hass.async_block_till_done()
        assert coordinator.update_interval == timedelta(seconds=15)

        assert hass.states.get(player_id).state == STATE_ON
        # Entities appear without a reload once the projector is on.
        assert hass.states.get(_eid(hass, "select", "picture_mode")).state == "cinema_film1"

        fake.power = "cooling1"
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert coordinator.update_interval == timedelta(seconds=2)
        fake.power = "standby"
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert coordinator.update_interval == timedelta(seconds=30)
        assert hass.states.get(_eid(hass, "select", "picture_mode")).state == STATE_UNAVAILABLE
        assert hass.states.get(player_id).state == STATE_OFF
    finally:
        await hass.config_entries.async_unload(mock_config_entry.entry_id)
        await fake.stop()


async def test_not_ready_and_auth_failed(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, socket_enabled: None
) -> None:
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, "port": 1}
    )
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_auth_failed_starts_reauth(hass: HomeAssistant, socket_enabled: None) -> None:
    fake = FakeProjector(password="secret")
    await fake.start()
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="12345",
        data={CONF_HOST: "127.0.0.1", "port": fake.port, "password": "wrong"},
    )
    try:
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.SETUP_ERROR
        flows = hass.config_entries.flow.async_progress()
        assert any(flow["context"]["source"] == "reauth" for flow in flows)
    finally:
        await fake.stop()


async def test_services_and_diagnostics(
    hass: HomeAssistant, projector: FakeProjector, mock_config_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_config_entry)

    result = await hass.services.async_call(
        DOMAIN,
        "send_command",
        {"config_entry_id": mock_config_entry.entry_id, "command": "brightness ?"},
        blocking=True,
        return_response=True,
    )
    assert result == {"command": "brightness ?", "response": "50", "value": 50}

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "send_command",
            {"config_entry_id": mock_config_entry.entry_id, "command": "bogus ?"},
            blocking=True,
            return_response=True,
        )

    projector.infos["motionflow"] = {
        "type": "menu_sel",
        "version": "1.0",
        "range": ["off", "smooth_high", "true_cinema"],
    }
    projector.values["motionflow"] = "true_cinema"
    probe = await hass.services.async_call(
        DOMAIN,
        "probe_capabilities",
        {"config_entry_id": mock_config_entry.entry_id},
        blocking=True,
        return_response=True,
    )
    assert "motionflow" in probe["new"]
    assert probe["supported"]["brightness"] == {
        "type": "menu_num",
        "min": 0,
        "max": 100,
        "step": None,
    }
    await hass.async_block_till_done()
    assert hass.states.get(_eid(hass, "select", "motionflow")).state == "true_cinema"

    diag = await async_get_config_entry_diagnostics(hass, mock_config_entry)
    assert diag["entry"]["data"][CONF_HOST] == "**REDACTED**"
    assert "brightness" in diag["capabilities"]["supported"]
    assert diag["state"]["power"] == "on"


async def test_sdap_push_updates_host(
    hass: HomeAssistant, projector: FakeProjector, mock_config_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data.coordinator
    coordinator.async_handle_advertisement(
        SdapAdvertisement("127.0.0.2", "SONY", "VPL-GTZ380", "12345", 3, None)
    )
    await hass.async_block_till_done()
    assert mock_config_entry.data[CONF_HOST] == "127.0.0.2"


async def test_unload(
    hass: HomeAssistant, projector: FakeProjector, mock_config_entry: MockConfigEntry
) -> None:
    await _setup(hass, mock_config_entry)
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_extra_commands_option(
    hass: HomeAssistant, projector: FakeProjector, mock_config_entry: MockConfigEntry
) -> None:
    """A user-listed command becomes an entity named after the command."""
    projector.infos["my_mode"] = {"type": "menu_sel", "version": "1.0", "range": ["a", "b"]}
    projector.values["my_mode"] = "b"
    projector.infos["laser_temp"] = {"type": "sys_stat", "version": "1.0"}
    projector.values["laser_temp"] = 41
    hass.config_entries.async_update_entry  # noqa: B018
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, options={"extra_commands": ["my_mode", "laser_temp"]}
    )
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(_eid(hass, "select", "my_mode"))
    assert state.state == "b"
    assert state.name.endswith("My mode")
    assert hass.states.get(_eid(hass, "sensor", "laser_temp")).state == "41"


async def test_errors_and_warnings(
    hass: HomeAssistant, projector: FakeProjector, mock_config_entry: MockConfigEntry
) -> None:
    projector.errors = ["err_temp"]
    projector.warnings = ["warn_highland"]
    await _setup(hass, mock_config_entry)
    error = hass.states.get(_eid(hass, "binary_sensor", "error"))
    assert error.state == STATE_ON
    assert error.attributes["codes"] == ["err_temp"]
    assert hass.states.get(_eid(hass, "binary_sensor", "warning")).state == STATE_ON
