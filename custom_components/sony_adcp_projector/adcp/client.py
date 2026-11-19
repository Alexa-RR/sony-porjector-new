"""Async client for Sony's Advanced Display Control Protocol (ADCP).

Wire format (Sony Protocol Manual, common edition):

* TCP, default port 53595, ASCII, every frame terminated with CR LF.
* On connect the projector sends either ``NOKEY`` (authentication disabled) or
  a random challenge. The client answers ``sha256(challenge + password)`` as
  lowercase hex and the projector replies ``ok`` or ``err_auth``.
* Commands are ``<name> [--option] [value | ?]``. Choice values are quoted,
  numeric values are bare. Replies are ``ok``, a value, JSON, or ``err_*``.
* The projector drops idle connections after a configurable timeout (60 s by
  default), so the client transparently reconnects.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
from collections.abc import Iterable
from typing import Any, Final

from .errors import (
    AdcpAuthenticationError,
    AdcpAuthenticationRequiredError,
    AdcpCommandError,
    AdcpConnectionError,
    AdcpOutcomeUnknownError,
    AdcpTimeoutError,
)
from .models import (
    CommandInfo,
    PowerStatus,
    ProjectorIdentity,
    as_string_list,
    decode_response,
    encode_value,
    merge_object_list,
    normalize_mac,
    parse_power_status,
    validate_command,
    validate_suffix,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT: Final = 53595
DEFAULT_TIMEOUT: Final = 5.0
# Reconnect proactively before the projector's own idle timeout (60 s default).
DEFAULT_IDLE_RECONNECT: Final = 40.0
LINE_END: Final = b"\r\n"
MAX_FRAME: Final = 512
NOKEY: Final = "NOKEY"


def _auth_digest(challenge: str, password: str) -> str:
    return hashlib.sha256((challenge + password).encode()).hexdigest()


async def async_probe_requires_password(
    host: str, port: int = DEFAULT_PORT, connect_timeout: float = DEFAULT_TIMEOUT
) -> bool:
    """Connect, read the greeting only, and report whether a password is needed."""
    writer: asyncio.StreamWriter | None = None
    try:
        async with asyncio.timeout(connect_timeout):
            reader, writer = await asyncio.open_connection(host, port)
            greeting = await reader.readuntil(LINE_END)
    except TimeoutError as err:
        raise AdcpTimeoutError(f"Timed out connecting to {host}:{port}") from err
    except (OSError, asyncio.IncompleteReadError) as err:
        raise AdcpConnectionError(f"Cannot connect to {host}:{port}: {err}") from err
    finally:
        if writer is not None:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
    return greeting.decode("ascii", "replace").strip() != NOKEY


class AdcpClient:
    """A single serialized, self-healing ADCP connection."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        password: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        idle_reconnect: float = DEFAULT_IDLE_RECONNECT,
    ) -> None:
        self.host = host
        self.port = port
        self.password = password or None
        self.timeout = timeout
        self.idle_reconnect = idle_reconnect
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._last_io = 0.0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Connection handling
    # ------------------------------------------------------------------ #
    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def async_close(self) -> None:
        """Close the connection (safe to call repeatedly)."""
        writer, self._writer, self._reader = self._writer, None, None
        if writer is None:
            return
        writer.close()
        with contextlib.suppress(OSError, TimeoutError):
            await asyncio.wait_for(writer.wait_closed(), 1)

    async def async_update_host(self, host: str, port: int | None = None) -> None:
        """Point the client at a new address (e.g. after a DHCP change)."""
        async with self._lock:
            if host == self.host and (port is None or port == self.port):
                return
            await self.async_close()
            self.host = host
            if port is not None:
                self.port = port

    async def _async_connect(self) -> None:
        loop = asyncio.get_running_loop()
        if self.connected and loop.time() - self._last_io < self.idle_reconnect:
            return
        await self.async_close()
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout
            )
            challenge = await self._async_readline()
        except TimeoutError as err:
            await self.async_close()
            raise AdcpTimeoutError(f"Timed out connecting to {self.host}:{self.port}") from err
        except (OSError, asyncio.IncompleteReadError) as err:
            await self.async_close()
            raise AdcpConnectionError(f"Cannot connect to {self.host}:{self.port}: {err}") from err

        if challenge == NOKEY:
            _LOGGER.debug("Connected to %s (no authentication)", self.host)
            return
        if not self.password:
            await self.async_close()
            raise AdcpAuthenticationRequiredError("The projector requires a password")
        try:
            reply = await self._async_exchange(_auth_digest(challenge, self.password))
        except (TimeoutError, OSError, asyncio.IncompleteReadError) as err:
            await self.async_close()
            raise AdcpConnectionError("Connection lost during authentication") from err
        if reply.lower() != "ok":
            await self.async_close()
            raise AdcpAuthenticationError(f"Authentication rejected ({reply})")
        _LOGGER.debug("Connected and authenticated to %s", self.host)

    async def _async_readline(self) -> str:
        assert self._reader is not None
        raw = await asyncio.wait_for(self._reader.readuntil(LINE_END), self.timeout)
        self._last_io = asyncio.get_running_loop().time()
        return raw.decode("ascii", "replace").strip()

    async def _async_exchange(self, line: str) -> str:
        assert self._writer is not None
        self._writer.write(line.encode("ascii") + LINE_END)
        await self._writer.drain()
        return await self._async_readline()

    # ------------------------------------------------------------------ #
    # Raw command
    # ------------------------------------------------------------------ #
    async def async_send_raw(self, line: str, *, idempotent: bool = True) -> str:
        """Send one frame and return the stripped reply line.

        ``err_*`` replies raise :class:`AdcpCommandError`. Idempotent commands
        (queries and absolute sets) are retried once on a dropped connection;
        others (key presses, relative steps) never are.
        """
        encoded = line.encode("ascii", "strict")
        if not encoded or len(encoded) + 2 > MAX_FRAME:
            raise ValueError("ADCP frame must be 1-510 printable ASCII bytes")
        if any(byte < 0x20 or byte > 0x7E for byte in encoded):
            raise ValueError("ADCP frame must be a single printable ASCII line")

        async with self._lock:
            attempts = 2 if idempotent else 1
            for attempt in range(attempts):
                await self._async_connect()
                try:
                    reply = await self._async_exchange(line)
                except asyncio.CancelledError:
                    # A late reply could be mistaken for the next command's.
                    await self.async_close()
                    raise
                except (TimeoutError, OSError, asyncio.IncompleteReadError) as err:
                    await self.async_close()
                    if not idempotent:
                        raise AdcpOutcomeUnknownError(
                            f"Lost connection after sending {line!r}; not retried"
                        ) from err
                    if attempt + 1 < attempts:
                        _LOGGER.debug("Retrying %r after %r", line, err)
                        continue
                    if isinstance(err, TimeoutError):
                        raise AdcpTimeoutError(f"No reply to {line!r}") from err
                    raise AdcpConnectionError(f"Connection lost: {err}") from err
                _LOGGER.debug("%s >> %s << %s", self.host, line, reply)
                lowered = reply.lower()
                if lowered == "err_auth":
                    await self.async_close()
                    raise AdcpAuthenticationError("Authentication expired or rejected")
                if lowered.startswith("err_"):
                    raise AdcpCommandError(line, lowered)
                return reply
        raise AssertionError("unreachable")  # pragma: no cover

    # ------------------------------------------------------------------ #
    # Typed helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build(command: str, suffix: str | None, *parts: str) -> str:
        tokens = [validate_command(command)]
        if validate_suffix(suffix):
            tokens.append(suffix)  # type: ignore[arg-type]
        tokens.extend(parts)
        return " ".join(tokens)

    async def async_get(self, command: str, suffix: str | None = None) -> Any:
        """Query the current value of a command (``cmd [--sfx] ?``)."""
        return decode_response(await self.async_send_raw(self._build(command, suffix, "?")))

    async def async_set(
        self, command: str, value: str | int | float | bool, suffix: str | None = None
    ) -> None:
        """Set an absolute value (``cmd [--sfx] "choice"`` or ``cmd 10``)."""
        await self.async_send_raw(self._build(command, suffix, encode_value(value)))

    async def async_step(self, command: str, delta: int, suffix: str | None = None) -> None:
        """Relative numeric adjustment (``cmd --rel -1``); never retried."""
        await self.async_send_raw(
            self._build(command, suffix, "--rel", str(int(delta))), idempotent=False
        )

    async def async_reset(self, command: str, suffix: str | None = None) -> None:
        """Reset a menu value to its default (``cmd --reset``)."""
        await self.async_send_raw(self._build(command, suffix, "--reset"), idempotent=False)

    async def async_execute(
        self, command: str, choice: str | None = None, suffix: str | None = None
    ) -> None:
        """Run a ``menu_exec`` command, optionally with a choice."""
        parts = (encode_value(choice),) if choice is not None else ()
        await self.async_send_raw(self._build(command, suffix, *parts), idempotent=False)

    async def async_key(self, key: str) -> None:
        """Emulate a remote control key press."""
        await self.async_send_raw(f"key {encode_value(key)}", idempotent=False)

    async def async_get_info(self, command: str, suffix: str | None = None) -> CommandInfo:
        """Return command metadata.

        Sony documents both ``cmd --info`` (menu commands) and ``cmd ? --info``
        (system commands); try both. Raises :class:`AdcpCommandError` with
        ``unsupported`` set when neither form is known.
        """
        variants: Iterable[str] = (
            self._build(command, suffix, "--info"),
            self._build(command, None, "?", *((suffix,) if suffix else ()), "--info"),
        )
        last: AdcpCommandError | None = None
        for line in dict.fromkeys(variants):
            try:
                payload = decode_response(await self.async_send_raw(line))
            except AdcpCommandError as err:
                if not err.unsupported:
                    raise
                last = err
                continue
            try:
                return CommandInfo.from_payload(command, payload)
            except (TypeError, ValueError) as err:
                raise AdcpCommandError(line, "err_invalid_info") from err
        assert last is not None
        raise last

    async def async_get_range(self, command: str, suffix: str | None = None) -> Any:
        return decode_response(await self.async_send_raw(self._build(command, suffix, "--range")))

    # ------------------------------------------------------------------ #
    # System commands
    # ------------------------------------------------------------------ #
    async def async_power(self, on: bool) -> None:
        await self.async_send_raw(f"power {encode_value('on' if on else 'off')}")

    async def async_get_power_status(self) -> PowerStatus | None:
        return parse_power_status(await self.async_get("power_status"))

    async def async_get_errors(self) -> list[str]:
        return [e for e in as_string_list(await self.async_get("error")) if e != "no_err"]

    async def async_get_warnings(self) -> list[str]:
        return [w for w in as_string_list(await self.async_get("warning")) if w != "no_warn"]

    async def async_get_timers(self) -> dict[str, int]:
        merged = merge_object_list(await self.async_get("timer"))
        return {k: int(v) for k, v in merged.items() if isinstance(v, int | float)}

    async def async_get_firmware(self) -> dict[str, str]:
        merged = merge_object_list(await self.async_get("version"))
        return {k: str(v) for k, v in merged.items()}

    async def async_get_identity(self) -> ProjectorIdentity:
        """Read model, serial, MAC and firmware, skipping unsupported fields."""

        async def optional(coro: Any) -> Any:
            try:
                return await coro
            except AdcpCommandError:
                return None

        model = await optional(self.async_get("modelname"))
        serial = await optional(self.async_get("serialnum"))
        mac = await optional(self.async_get("mac_address"))
        firmware = await optional(self.async_get_firmware()) or {}
        return ProjectorIdentity(
            model=str(model) if model else None,
            serial=str(serial) if serial not in (None, "") else None,
            mac_address=normalize_mac(str(mac)) if mac else None,
            firmware=firmware,
        )
