"""A fake Sony projector that speaks ADCP over a real local TCP socket."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import shlex
from typing import Any

CHALLENGE = "a1b2c3d4"

ON_OFF = ["on", "off"]

DEFAULT_INFOS: dict[str, dict[str, Any]] = {
    "input": {"type": "menu_sel", "version": "1.0", "range": ["hdmi1", "hdmi2", "dp1"]},
    "picture_mode": {
        "type": "menu_sel",
        "version": "1.0",
        "range": ["cinema_film1", "cinema_film2", "reference", "game", "user1"],
    },
    "aspect": {"type": "menu_sel", "version": "1.0", "range": ["normal", "squeeze", "stretch"]},
    "pic_pos_sel": {"type": "menu_sel", "version": "1.0", "range": ["custom1", "custom2"]},
    "pic_pos_save": {"type": "menu_exec", "version": "1.0", "range": ["custom1", "custom2"]},
    "picture_mode_reset": {"type": "menu_exec", "version": "1.0"},
    "brightness": {"type": "menu_num", "version": "1.0", "range": {"min": 0, "max": 100}},
    "light_output_val": {"type": "menu_num", "version": "1.0", "range": {"min": 0, "max": 100}},
    "real_cre": {"type": "menu_sel", "version": "1.0", "range": ON_OFF},
    "blank": {"type": "menu_sel", "version": "1.0", "range": ON_OFF},
    "blanking --top": {"type": "menu_num", "version": "1.0", "range": {"min": 0, "max": 50}},
}

DEFAULT_VALUES: dict[str, Any] = {
    "input": "hdmi1",
    "picture_mode": "cinema_film1",
    "aspect": "normal",
    "pic_pos_sel": "custom1",
    "brightness": 50,
    "light_output_val": 80,
    "real_cre": "on",
    "blank": "off",
    "blanking --top": 0,
}


class FakeProjector:
    """Minimal but faithful ADCP server."""

    def __init__(
        self,
        *,
        password: str | None = None,
        power: str = "on",
        model: str = "VPL-GTZ380",
        serial: str | None = "0012345",
        info_needs_query_form: frozenset[str] = frozenset(),
    ) -> None:
        self.password = password
        self.power = power
        self.model = model
        self.serial = serial
        self.infos = copy.deepcopy(DEFAULT_INFOS)
        self.values = dict(DEFAULT_VALUES)
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.received: list[str] = []
        self.connections = 0
        self.info_needs_query_form = info_needs_query_form
        self.drop_next = False
        self._server: asyncio.Server | None = None
        self.port = 0

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server.close_clients()
            await self._server.wait_closed()

    # ------------------------------------------------------------------ #
    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1

        async def send(text: str) -> None:
            writer.write(text.encode() + b"\r\n")
            await writer.drain()

        try:
            if self.password is None:
                await send("NOKEY")
            else:
                await send(CHALLENGE)
                line = (await reader.readuntil(b"\r\n")).decode().strip()
                expected = hashlib.sha256((CHALLENGE + self.password).encode()).hexdigest()
                if line != expected:
                    await send("err_auth")
                    writer.close()
                    return
                await send("ok")
            while True:
                raw = await reader.readuntil(b"\r\n")
                line = raw.decode().strip()
                self.received.append(line)
                if self.drop_next:
                    self.drop_next = False
                    writer.close()
                    return
                await send(self.respond(line))
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    # ------------------------------------------------------------------ #
    def respond(self, line: str) -> str:
        tokens = shlex.split(line)
        name = tokens[0]
        options = [t for t in tokens[1:] if t.startswith("--") and t not in ("--info", "--range")]
        key = " ".join([name, *options])
        query = tokens[-1] == "?"
        info_query = "--info" in tokens

        system = {
            "power_status": json.dumps(self.power),
            "error": json.dumps(self.errors or ["no_err"]),
            "warning": json.dumps(self.warnings or ["no_warn"]),
            "timer": json.dumps([{"operation": 1234}, {"light_src": 1000}]),
            "version": json.dumps([{"main": "1.020"}, {"laser": "0.21"}]),
            "modelname": json.dumps(self.model),
            "serialnum": json.dumps(self.serial),
            "mac_address": json.dumps("08-00-46-aa-bb-cc"),
            "signal": json.dumps("3840x2160/24p" if self.power == "on" else "Invalid"),
        }
        if self.serial is None and name in ("serialnum", "mac_address"):
            return "err_cmd"
        if name in system and query:
            return system[name]
        if name == "power":
            self.power = "on" if tokens[1] == "on" else "standby"
            return "ok"
        if name == "key":
            return "ok"
        if key not in self.infos:
            return "err_cmd"
        info = self.infos[key]
        if self.power != "on":
            return "err_inactive"
        if info_query:
            if name in self.info_needs_query_form and "?" not in tokens:
                return "err_option"
            return json.dumps(info)
        if query:
            return json.dumps(self.values[key])
        if info["type"] == "menu_exec":
            if len(tokens) > 1 + len(options):
                choice = tokens[-1]
                if choice not in info.get("range", []):
                    return "err_val"
            return "ok"
        value_token = tokens[-1]
        if info["type"] == "menu_num":
            try:
                value: Any = int(value_token)
            except ValueError:
                return "err_val"
            bounds = info["range"]
            if not bounds["min"] <= value <= bounds["max"]:
                return "err_val"
        else:
            value = value_token
            if value not in info["range"]:
                return "err_val"
        self.values[key] = value
        return "ok"
