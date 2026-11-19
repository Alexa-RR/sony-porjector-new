"""Sony SDAP (Simple Display Advertisement Protocol) listener.

Projectors with *Advertisement* enabled broadcast a 50 byte UDP datagram to
port 53862 every few seconds (interval configurable on the projector):

====== ===== ===================================================
offset bytes  field
====== ===== ===================================================
0      2      ID, ASCII ``DA``
2      1      version (``0x01``)
3      1      category (``0x0A`` = projector)
4      4      community (default ``SONY``)
8      12     product name, NUL padded
20     4      serial number, big endian integer
24     2      power status (model specific bit field)
26     24     installation location, NUL padded
====== ===== ===================================================
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from .models import normalize_serial

_LOGGER = logging.getLogger(__name__)

SDAP_PORT: Final = 53862
SDAP_LENGTH: Final = 50


@dataclass(frozen=True, slots=True)
class SdapAdvertisement:
    """A parsed advertisement."""

    host: str
    community: str | None
    model: str | None
    serial: str | None
    power_raw: int
    location: str | None

    @property
    def unique_id(self) -> str:
        return self.serial or self.host


def _text(data: bytes) -> str | None:
    value = data.split(b"\0", 1)[0].decode("ascii", "ignore").strip()
    return value or None


def parse_sdap(data: bytes, host: str) -> SdapAdvertisement | None:
    """Parse a datagram, returning ``None`` for anything that is not SDAP."""
    if len(data) < SDAP_LENGTH or data[:2] != b"DA" or data[3] != 0x0A:
        return None
    serial_number = int.from_bytes(data[20:24], "big")
    return SdapAdvertisement(
        host=host,
        community=_text(data[4:8]),
        model=_text(data[8:20]),
        serial=normalize_serial(serial_number) if serial_number else None,
        power_raw=int.from_bytes(data[24:26], "big"),
        location=_text(data[26:50]),
    )


type AdvertisementCallback = Callable[[SdapAdvertisement], None]


class _Protocol(asyncio.DatagramProtocol):
    def __init__(self, listener: SdapListener) -> None:
        self._listener = listener

    def datagram_received(self, data: bytes, addr: tuple[str | int, ...]) -> None:
        if (adv := parse_sdap(data, str(addr[0]))) is not None:
            self._listener.dispatch(adv)

    def error_received(self, exc: Exception) -> None:  # pragma: no cover
        _LOGGER.debug("SDAP socket error: %s", exc)


class SdapListener:
    """Shared UDP listener; dispatches advertisements to subscribers."""

    def __init__(self, port: int = SDAP_PORT) -> None:
        self.port = port
        self.seen: dict[str, SdapAdvertisement] = {}
        self._callbacks: set[AdvertisementCallback] = set()
        self._transport: asyncio.DatagramTransport | None = None

    @property
    def running(self) -> bool:
        return self._transport is not None

    async def async_start(self) -> None:
        """Bind the socket. Uses SO_REUSEPORT so other tools can listen too."""
        if self._transport is not None:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                with contextlib.suppress(OSError):  # platform specific
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setblocking(False)
            sock.bind(("", self.port))
        except OSError:
            sock.close()
            raise
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(lambda: _Protocol(self), sock=sock)

    def stop(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    def subscribe(self, callback: AdvertisementCallback) -> Callable[[], None]:
        self._callbacks.add(callback)
        return lambda: self._callbacks.discard(callback)

    def dispatch(self, adv: SdapAdvertisement) -> None:
        if adv.serial:
            # Forget stale addresses of the same projector.
            for host, known in list(self.seen.items()):
                if host != adv.host and known.serial == adv.serial:
                    del self.seen[host]
        self.seen[adv.host] = adv
        for callback in list(self._callbacks):
            try:
                callback(adv)
            except Exception:  # pragma: no cover - defensive
                _LOGGER.exception("Error in SDAP callback")
