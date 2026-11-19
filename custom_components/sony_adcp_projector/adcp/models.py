"""Data models and value codecs for Sony ADCP."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# Command types reported by ``<command> --info``.
TYPE_SYS_SEL = "sys_sel"
TYPE_SYS_STAT = "sys_stat"
TYPE_SYS_VAR = "sys_var"
TYPE_MENU_SEL = "menu_sel"
TYPE_MENU_NUM = "menu_num"
TYPE_MENU_VAL = "menu_val"
TYPE_MENU_EXEC = "menu_exec"
TYPE_KEY = "key"

SELECT_TYPES = frozenset({TYPE_SYS_SEL, TYPE_MENU_SEL})
NUMBER_TYPES = frozenset({TYPE_MENU_NUM, TYPE_MENU_VAL})
EXEC_TYPES = frozenset({TYPE_MENU_EXEC})
STATUS_TYPES = frozenset({TYPE_SYS_STAT})

_COMMAND_RE = re.compile(r"^[a-z0-9_]+$")
_SUFFIX_RE = re.compile(r"^--[a-z0-9_]+$")


class PowerStatus(StrEnum):
    """Values returned by ``power_status ?``."""

    STANDBY = "standby"
    STARTUP = "startup"
    ON = "on"
    COOLING1 = "cooling1"
    COOLING2 = "cooling2"
    SAVING_COOLING1 = "saving_cooling1"
    SAVING_COOLING2 = "saving_cooling2"
    SAVING_STANDBY = "saving_standby"
    UPDATE = "update"

    @property
    def is_on(self) -> bool:
        """Light source on (or about to be)."""
        return self in (PowerStatus.ON, PowerStatus.STARTUP)

    @property
    def is_transitioning(self) -> bool:
        """Warming up, cooling down or updating firmware."""
        return self not in (
            PowerStatus.ON,
            PowerStatus.STANDBY,
            PowerStatus.SAVING_STANDBY,
        )


def parse_power_status(value: Any) -> PowerStatus | None:
    """Convert a raw power status, tolerating unknown values."""
    try:
        return PowerStatus(str(value).lower())
    except ValueError:
        if isinstance(value, str) and value.lower().startswith("cooling"):
            return PowerStatus.COOLING1
        return None


@dataclass(frozen=True, slots=True)
class CommandInfo:
    """Metadata returned by ``<command> --info``."""

    command: str
    type: str
    version: str | None = None
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def is_select(self) -> bool:
        return self.type in SELECT_TYPES

    @property
    def is_number(self) -> bool:
        return self.type in NUMBER_TYPES and self.minimum is not None and self.maximum is not None

    @property
    def is_exec(self) -> bool:
        return self.type in EXEC_TYPES

    @property
    def is_status(self) -> bool:
        return self.type in STATUS_TYPES

    @property
    def is_on_off(self) -> bool:
        """A select whose only choices are on/off (rendered as a switch)."""
        return self.is_select and set(self.choices) == {"on", "off"}

    @classmethod
    def from_payload(cls, command: str, payload: Any) -> CommandInfo:
        """Build from the decoded JSON payload."""
        if not isinstance(payload, dict) or not isinstance(payload.get("type"), str):
            raise TypeError(f"Invalid --info payload for {command}: {payload!r}")
        range_value = payload.get("range")
        choices: tuple[str, ...] = ()
        minimum = maximum = step = None
        if isinstance(range_value, list):
            choices = tuple(str(item) for item in range_value)
        elif isinstance(range_value, dict):
            minimum = _finite(range_value.get("min"))
            maximum = _finite(range_value.get("max"))
            step = _finite(range_value.get("step"))
        version = payload.get("version")
        return cls(
            command=command,
            type=payload["type"],
            version=str(version) if version is not None else None,
            choices=choices,
            minimum=minimum,
            maximum=maximum,
            step=step if step and step > 0 else None,
            raw=payload,
        )

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe representation for storage."""
        return {"command": self.command, **self.raw}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CommandInfo:
        payload = {key: value for key, value in data.items() if key != "command"}
        return cls.from_payload(str(data["command"]), payload)


@dataclass(frozen=True, slots=True)
class ProjectorIdentity:
    """Identity of a projector."""

    model: str | None = None
    serial: str | None = None
    mac_address: str | None = None
    firmware: dict[str, str] = field(default_factory=dict)

    @property
    def main_firmware(self) -> str | None:
        return self.firmware.get("main")


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def validate_command(command: str) -> str:
    """Make sure a command name is a single safe token."""
    if not _COMMAND_RE.match(command):
        raise ValueError(f"Invalid ADCP command name: {command!r}")
    return command


def validate_suffix(suffix: str | None) -> str | None:
    if suffix is not None and not _SUFFIX_RE.match(suffix):
        raise ValueError(f"Invalid ADCP option: {suffix!r}")
    return suffix


def encode_value(value: str | int | float | bool) -> str:
    """Encode a value the way ADCP expects: choices quoted, numbers bare."""
    if isinstance(value, bool):
        return '"on"' if value else '"off"'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Value must be finite")
        return str(int(value)) if value.is_integer() else repr(value)
    text = str(value)
    if any(ch in text for ch in '"\r\n') or not text.isprintable():
        raise ValueError(f"Invalid ADCP value: {value!r}")
    return f'"{text}"'


def normalize_serial(value: str | int | None) -> str | None:
    """Serials arrive zero padded over ADCP and as integers over SDAP."""
    if value is None:
        return None
    text = str(value).strip().strip('"').lstrip("0")
    return text or None


def normalize_mac(value: str | None) -> str | None:
    if not value:
        return None
    compact = "".join(ch for ch in value if ch.isalnum()).lower()
    if len(compact) != 12:
        return value.lower()
    return ":".join(compact[i : i + 2] for i in range(0, 12, 2))


def decode_response(text: str) -> Any:
    """Decode a non-error ADCP reply into Python data.

    * ``"hdmi1"``           -> ``"hdmi1"``
    * ``50`` / ``-3``       -> ``50`` / ``-3``
    * ``1.5``               -> ``1.5``
    * ``["a","b"]`` / ``{}`` -> list / dict
    * anything else          -> the stripped string
    """
    text = text.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    if text[:1] in ("[", "{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    try:
        return int(text)
    except ValueError:
        pass
    try:
        number = float(text)
    except ValueError:
        return text
    return number if math.isfinite(number) else text


def merge_object_list(value: Any) -> dict[str, Any]:
    """Merge Sony's ``[{"a":1},{"b":2}]`` replies into ``{"a":1,"b":2}``."""
    result: dict[str, Any] = {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                result.update(item)
    return result


def as_string_list(value: Any) -> list[str]:
    """Normalize ``error ?`` / ``warning ?`` replies."""
    if isinstance(value, list):
        return [str(item) for item in value]
    if value in (None, ""):
        return []
    return [str(value)]
