"""Exceptions raised by the ADCP client."""

from __future__ import annotations


class AdcpError(Exception):
    """Base class for all ADCP errors."""


class AdcpConnectionError(AdcpError):
    """The projector could not be reached or the connection dropped."""


class AdcpTimeoutError(AdcpConnectionError):
    """The projector did not answer in time."""


class AdcpOutcomeUnknownError(AdcpConnectionError):
    """A non-idempotent command was sent but its acknowledgement was lost."""


class AdcpAuthenticationError(AdcpError):
    """The projector rejected the password."""


class AdcpAuthenticationRequiredError(AdcpAuthenticationError):
    """The projector requires a password but none was configured."""


class AdcpCommandError(AdcpError):
    """The projector answered a command with an ``err_*`` code.

    Codes documented by Sony:

    * ``err_cmd``       - command not supported by this model
    * ``err_option``    - option (e.g. ``--range``) not supported
    * ``err_val``       - value out of range / invalid choice
    * ``err_inactive``  - command exists but is not usable right now
      (projector in standby, no signal, setting greyed out in the menu...)
    * ``err_internal1`` / ``err_internal2`` - projector internal error
    """

    def __init__(self, command: str, code: str) -> None:
        super().__init__(f"{command!r} -> {code}")
        self.command = command
        self.code = code

    @property
    def unsupported(self) -> bool:
        """True when the model does not know the command at all."""
        return self.code in ("err_cmd", "err_option")

    @property
    def inactive(self) -> bool:
        """True when the command exists but is unavailable in the current state."""
        return self.code == "err_inactive"
