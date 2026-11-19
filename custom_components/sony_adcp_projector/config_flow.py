"""Config flow for the Sony Projector (ADCP) integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import probatio as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .adcp import (
    DEFAULT_PORT,
    AdcpAuthenticationError,
    AdcpAuthenticationRequiredError,
    AdcpClient,
    AdcpError,
    ProjectorIdentity,
    async_probe_requires_password,
    normalize_mac,
    normalize_serial,
)
from .catalog import extra_feature
from .const import (
    CONF_EXTRA_COMMANDS,
    CONF_MODEL,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DISCOVERY_WAIT,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

MANUAL = "manual"
CONF_DEVICE = "device"


def _host_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST): TextSelector(),
            vol.Required(CONF_PORT, default=DEFAULT_PORT): NumberSelector(
                NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
            ),
        }
    )


PASSWORD_SCHEMA = vol.Schema(
    {vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
)


class CannotConnect(Exception):
    """The projector could not be reached."""


class InvalidAuth(Exception):
    """The password was rejected."""


class PasswordRequired(Exception):
    """A password is needed."""


async def _async_validate(host: str, port: int, password: str | None) -> ProjectorIdentity:
    client = AdcpClient(host, port, password)
    try:
        return await client.async_get_identity()
    except AdcpAuthenticationRequiredError as err:
        raise PasswordRequired from err
    except AdcpAuthenticationError as err:
        raise InvalidAuth from err
    except AdcpError as err:
        raise CannotConnect from err
    finally:
        await client.async_close()


def _unique_id(identity: ProjectorIdentity) -> str | None:
    return normalize_serial(identity.serial) or normalize_mac(identity.mac_address)


class SonyProjectorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._port: int = DEFAULT_PORT
        self._model: str | None = None
        self._discovered: dict[str, dict[str, Any]] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SonyProjectorOptionsFlow:
        return SonyProjectorOptionsFlow()

    # ------------------------------------------------------------------ #
    # User initiated
    # ------------------------------------------------------------------ #
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Offer projectors heard over SDAP, or manual entry."""
        from . import async_get_sdap_listener  # noqa: PLC0415 - avoid import cycle

        if (listener := await async_get_sdap_listener(self.hass)) is not None:
            if not listener.seen:
                await asyncio.sleep(DISCOVERY_WAIT)
            configured = self._async_current_ids(include_ignore=False)
            self._discovered = {
                adv.host: {"host": adv.host, "serial": adv.serial, "model": adv.model}
                for adv in listener.seen.values()
                if adv.serial not in configured
            }
        if not self._discovered:
            return await self.async_step_manual()
        return await self.async_step_pick()

    async def async_step_pick(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            if user_input[CONF_DEVICE] == MANUAL:
                return await self.async_step_manual()
            device = self._discovered[user_input[CONF_DEVICE]]
            self._host, self._model = device["host"], device["model"]
            return await self._async_connect()
        options = [
            SelectOptionDict(
                value=host,
                label=f"{info['model'] or DEFAULT_NAME} ({host})",
            )
            for host, info in self._discovered.items()
        ]
        options.append(SelectOptionDict(value=MANUAL, label=MANUAL))
        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.LIST,
                            translation_key="device",
                        )
                    )
                }
            ),
        )

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._host = user_input[CONF_HOST].strip()
            self._port = int(user_input[CONF_PORT])
            return await self._async_connect()
        return self._show_manual()

    def _show_manual(self, errors: dict[str, str] | None = None) -> ConfigFlowResult:
        return self.async_show_form(
            step_id="manual",
            data_schema=self.add_suggested_values_to_schema(
                _host_schema(),
                {CONF_HOST: self._host, CONF_PORT: self._port} if self._host else {},
            ),
            errors=errors,
        )

    async def _async_connect(self) -> ConfigFlowResult:
        """Probe the greeting; ask for a password only if the projector wants one."""
        assert self._host is not None
        try:
            needs_password = await async_probe_requires_password(self._host, self._port)
        except AdcpError:
            return self._show_manual({"base": "cannot_connect"})
        if needs_password:
            return await self.async_step_password()
        return await self._async_finish(None)

    async def async_step_password(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._async_finish(user_input[CONF_PASSWORD])
        return self._show_password()

    def _show_password(self, errors: dict[str, str] | None = None) -> ConfigFlowResult:
        return self.async_show_form(
            step_id="password",
            data_schema=PASSWORD_SCHEMA,
            errors=errors,
            description_placeholders={"host": self._host or ""},
        )

    async def _async_finish(self, password: str | None) -> ConfigFlowResult:
        assert self._host is not None
        try:
            identity = await _async_validate(self._host, self._port, password)
        except PasswordRequired:
            return self._show_password()
        except InvalidAuth:
            return self._show_password({"base": "invalid_auth"})
        except CannotConnect:
            if password is not None:
                return self._show_password({"base": "cannot_connect"})
            return self._show_manual({"base": "cannot_connect"})
        if (unique_id := _unique_id(identity)) is None:
            return self.async_abort(reason="no_serial")
        await self.async_set_unique_id(unique_id, raise_on_progress=False)
        self._abort_if_unique_id_configured(updates={CONF_HOST: self._host, CONF_PORT: self._port})
        data: dict[str, Any] = {
            CONF_HOST: self._host,
            CONF_PORT: self._port,
            CONF_SERIAL: identity.serial,
            CONF_MODEL: identity.model,
        }
        if password:
            data[CONF_PASSWORD] = password
        return self.async_create_entry(
            title=identity.model or self._model or DEFAULT_NAME, data=data
        )

    # ------------------------------------------------------------------ #
    # SDAP discovery
    # ------------------------------------------------------------------ #
    async def async_step_integration_discovery(
        self, discovery_info: dict[str, Any]
    ) -> ConfigFlowResult:
        self._host = discovery_info["host"]
        self._model = discovery_info.get("model")
        await self.async_set_unique_id(discovery_info["serial"])
        self._abort_if_unique_id_configured(updates={CONF_HOST: self._host})
        self.context["title_placeholders"] = {
            "model": self._model or DEFAULT_NAME,
            "host": self._host,
        }
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._async_connect()
        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={
                "model": self._model or DEFAULT_NAME,
                "host": self._host or "",
            },
        )

    # ------------------------------------------------------------------ #
    # Re-authentication
    # ------------------------------------------------------------------ #
    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                identity = await _async_validate(
                    entry.data[CONF_HOST], entry.data[CONF_PORT], user_input[CONF_PASSWORD]
                )
            except (InvalidAuth, PasswordRequired):
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(_unique_id(identity))
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=PASSWORD_SCHEMA,
            errors=errors,
            description_placeholders={"name": entry.title},
        )

    # ------------------------------------------------------------------ #
    # Reconfigure (address, port, password)
    # ------------------------------------------------------------------ #
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            password = user_input.get(CONF_PASSWORD) or None
            try:
                identity = await _async_validate(host, port, password)
            except PasswordRequired:
                errors[CONF_PASSWORD] = "password_required"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(_unique_id(identity))
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                data = {**entry.data, CONF_HOST: host, CONF_PORT: port}
                data.pop(CONF_PASSWORD, None)
                if password:
                    data[CONF_PASSWORD] = password
                return self.async_update_reload_and_abort(entry, data=data)
        schema = _host_schema().extend(
            {
                vol.Optional(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                )
            }
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                user_input or {CONF_HOST: entry.data[CONF_HOST], CONF_PORT: entry.data[CONF_PORT]},
            ),
            errors=errors,
        )


class SonyProjectorOptionsFlow(OptionsFlowWithReload):
    """Polling interval and additional ADCP commands."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            raw = user_input.get(CONF_EXTRA_COMMANDS) or []
            specs = [spec.strip() for spec in raw if spec.strip()]
            if any(extra_feature(spec) is None for spec in specs):
                errors[CONF_EXTRA_COMMANDS] = "invalid_command"
            else:
                return self.async_create_entry(
                    data={
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                        CONF_EXTRA_COMMANDS: specs,
                    }
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(CONF_EXTRA_COMMANDS, default=[]): TextSelector(
                    TextSelectorConfig(multiple=True)
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or dict(self.config_entry.options)
            ),
            errors=errors,
        )
