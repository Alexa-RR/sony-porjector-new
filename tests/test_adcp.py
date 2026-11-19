"""Protocol-level tests for the bundled ADCP library (no Home Assistant)."""

from __future__ import annotations

import pytest

from custom_components.sony_adcp_projector.adcp import (
    AdcpAuthenticationError,
    AdcpAuthenticationRequiredError,
    AdcpClient,
    AdcpCommandError,
    AdcpConnectionError,
    AdcpOutcomeUnknownError,
    PowerStatus,
    async_probe_requires_password,
    decode_response,
    encode_value,
    parse_sdap,
)

from .fake_projector import FakeProjector

pytestmark = pytest.mark.usefixtures("socket_enabled")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('"hdmi1"', "hdmi1"),
        ("50", 50),
        ("-3", -3),
        ("1.5", 1.5),
        ('["a","b"]', ["a", "b"]),
        ('{"type":"menu_sel"}', {"type": "menu_sel"}),
        ("ok", "ok"),
        ("[broken", "[broken"),
    ],
)
def test_decode_response(raw: str, expected: object) -> None:
    assert decode_response(raw) == expected


def test_encode_value() -> None:
    assert encode_value("cinema_film1") == '"cinema_film1"'
    assert encode_value(10) == "10"
    assert encode_value(10.0) == "10"
    assert encode_value(True) == '"on"'
    with pytest.raises(ValueError):
        encode_value('bad"quote')
    with pytest.raises(ValueError):
        encode_value(float("nan"))


async def test_no_auth_roundtrip(projector: FakeProjector) -> None:
    client = AdcpClient("127.0.0.1", projector.port)
    assert not await async_probe_requires_password("127.0.0.1", projector.port)
    assert await client.async_get_power_status() is PowerStatus.ON
    assert await client.async_get("brightness") == 50
    await client.async_set("brightness", 60)
    await client.async_set("picture_mode", "game")
    assert projector.received[-2:] == ["brightness 60", 'picture_mode "game"']
    assert await client.async_get("blanking", "--top") == 0
    identity = await client.async_get_identity()
    assert identity.model == "VPL-GTZ380"
    assert identity.serial == "0012345"
    assert identity.mac_address == "08:00:46:aa:bb:cc"
    assert identity.main_firmware == "1.020"
    assert await client.async_get_timers() == {"operation": 1234, "light_src": 1000}
    assert await client.async_get_errors() == []
    # Everything above used one connection.
    assert projector.connections == 2  # probe + client
    await client.async_close()


async def test_password_auth() -> None:
    fake = FakeProjector(password="Projector")
    await fake.start()
    try:
        assert await async_probe_requires_password("127.0.0.1", fake.port)
        with pytest.raises(AdcpAuthenticationRequiredError):
            await AdcpClient("127.0.0.1", fake.port).async_get("brightness")
        with pytest.raises(AdcpAuthenticationError):
            await AdcpClient("127.0.0.1", fake.port, "wrong").async_get("brightness")
        good = AdcpClient("127.0.0.1", fake.port, "Projector")
        assert await good.async_get("brightness") == 50
        await good.async_close()
    finally:
        await fake.stop()


async def test_command_errors(projector: FakeProjector) -> None:
    client = AdcpClient("127.0.0.1", projector.port)
    with pytest.raises(AdcpCommandError) as err:
        await client.async_get("nonexistent")
    assert err.value.unsupported
    with pytest.raises(AdcpCommandError) as err:
        await client.async_set("brightness", 500)
    assert err.value.code == "err_val"
    projector.power = "standby"
    with pytest.raises(AdcpCommandError) as err:
        await client.async_get("brightness")
    assert err.value.inactive
    await client.async_close()


async def test_info_and_fallback_syntax() -> None:
    fake = FakeProjector(info_needs_query_form=frozenset({"picture_mode"}))
    await fake.start()
    client = AdcpClient("127.0.0.1", fake.port)
    try:
        info = await client.async_get_info("picture_mode")
        assert info.is_select and "game" in info.choices
        assert fake.received[-2:] == ["picture_mode --info", "picture_mode ? --info"]
        number = await client.async_get_info("brightness")
        assert number.is_number and (number.minimum, number.maximum) == (0, 100)
        assert (await client.async_get_info("real_cre")).is_on_off
        assert (await client.async_get_info("pic_pos_save")).is_exec
        with pytest.raises(AdcpCommandError) as err:
            await client.async_get_info("does_not_exist")
        assert err.value.unsupported
    finally:
        await client.async_close()
        await fake.stop()


async def test_reconnect_after_drop(projector: FakeProjector) -> None:
    client = AdcpClient("127.0.0.1", projector.port)
    assert await client.async_get("brightness") == 50
    projector.drop_next = True
    # Idempotent query: retried transparently on a fresh connection.
    assert await client.async_get("brightness") == 50
    projector.drop_next = True
    # Key presses are never replayed.
    with pytest.raises(AdcpOutcomeUnknownError):
        await client.async_key("menu")
    await client.async_close()


async def test_unreachable() -> None:
    client = AdcpClient("127.0.0.1", 1, timeout=1)
    with pytest.raises(AdcpConnectionError):
        await client.async_get("power_status")


def test_invalid_command_names() -> None:
    client = AdcpClient("127.0.0.1")
    with pytest.raises(ValueError):
        client._build("bad name", None)
    with pytest.raises(ValueError):
        client._build("ok", "top")


def test_parse_sdap() -> None:
    packet = (
        b"DA\x01\x0a"
        + b"SONY"
        + b"VPL-GTZ380".ljust(12, b"\0")
        + (12345).to_bytes(4, "big")
        + (3).to_bytes(2, "big")
        + b"Cinema".ljust(24, b"\0")
    )
    adv = parse_sdap(packet, "192.0.2.10")
    assert adv is not None
    assert (adv.model, adv.serial, adv.power_raw, adv.location) == (
        "VPL-GTZ380",
        "12345",
        3,
        "Cinema",
    )
    assert parse_sdap(b"XX" + packet[2:], "x") is None
    assert parse_sdap(packet[:20], "x") is None


@pytest.mark.real_sdap
async def test_sdap_listener_receives_broadcast() -> None:
    import asyncio
    import socket

    from custom_components.sony_adcp_projector.adcp import SdapListener

    listener = SdapListener(port=0)
    received: list = []
    unsubscribe = listener.subscribe(received.append)
    # Bind to an ephemeral port so the test never needs UDP 53862.
    await listener.async_start()
    port = listener._transport.get_extra_info("sockname")[1]
    packet = (
        b"DA\x01\x0a"
        + b"SONY"
        + b"VPL-GTZ380".ljust(12, b"\0")
        + (12345).to_bytes(4, "big")
        + (1).to_bytes(2, "big")
        + bytes(24)
    )
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sender.sendto(packet, ("127.0.0.1", port))
        sender.sendto(b"garbage", ("127.0.0.1", port))
        for _ in range(50):
            if received:
                break
            await asyncio.sleep(0.01)
    finally:
        sender.close()
        unsubscribe()
        listener.stop()
    assert len(received) == 1
    assert received[0].serial == "12345"
    assert listener.seen["127.0.0.1"].model == "VPL-GTZ380"
    assert not listener.running


def test_source_names() -> None:
    from custom_components.sony_adcp_projector.media_player import source_name

    assert source_name("hdmi1") == "HDMI 1"
    assert source_name("dp2") == "DisplayPort 2"
    # Real VPL-GTZ380 input list: hdmi1, hdmi2, dp1, dp2, dp1_2
    assert source_name("dp1_2") == "DisplayPort 1+2"
    assert source_name("weird_input") == "Weird Input"


async def test_info_query_form_only() -> None:
    """The VPL-GTZ380 rejects ``cmd --info`` and only accepts ``cmd ? --info``."""
    fake = FakeProjector(info_needs_query_form=frozenset({"motionflow", "brightness"}))
    fake.infos["motionflow"] = {
        "type": "menu_sel",
        "version": "1.0",
        "range": ["off", "smooth_high", "impulse1", "true_cinema"],
    }
    await fake.start()
    client = AdcpClient("127.0.0.1", fake.port)
    try:
        info = await client.async_get_info("motionflow")
        assert info.choices == ("off", "smooth_high", "impulse1", "true_cinema")
        assert (await client.async_get_info("brightness")).is_number
    finally:
        await client.async_close()
        await fake.stop()
