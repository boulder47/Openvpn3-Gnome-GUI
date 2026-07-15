"""Re-exports of shared errors for callers that only import ``openvpn.*``."""

from openvpn3_gui.utils.errors import (  # noqa: F401
    AuthenticationRequired,
    CliExecutionError,
    CliNotFoundError,
    CliTimeoutError,
    ParseError,
    ProfileNotFoundError,
    SessionNotFoundError,
)
