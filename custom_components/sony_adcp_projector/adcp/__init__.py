"""Standalone async implementation of Sony's ADCP and SDAP protocols.

This package has no Home Assistant dependencies so it can be published to
PyPI on its own later (Home Assistant's library-separation rule).
"""

from .client import (
    DEFAULT_PORT,
    AdcpClient,
    async_probe_requires_password,
)
from .discovery import SDAP_PORT, SdapAdvertisement, SdapListener, parse_sdap
from .errors import (
    AdcpAuthenticationError,
    AdcpAuthenticationRequiredError,
    AdcpCommandError,
    AdcpConnectionError,
    AdcpError,
    AdcpOutcomeUnknownError,
    AdcpTimeoutError,
)
from .models import (
    CommandInfo,
    PowerStatus,
    ProjectorIdentity,
    decode_response,
    encode_value,
    normalize_mac,
    normalize_serial,
)

__all__ = [
    "DEFAULT_PORT",
    "SDAP_PORT",
    "AdcpAuthenticationError",
    "AdcpAuthenticationRequiredError",
    "AdcpClient",
    "AdcpCommandError",
    "AdcpConnectionError",
    "AdcpError",
    "AdcpOutcomeUnknownError",
    "AdcpTimeoutError",
    "CommandInfo",
    "PowerStatus",
    "ProjectorIdentity",
    "SdapAdvertisement",
    "SdapListener",
    "async_probe_requires_password",
    "decode_response",
    "encode_value",
    "normalize_mac",
    "normalize_serial",
    "parse_sdap",
]
