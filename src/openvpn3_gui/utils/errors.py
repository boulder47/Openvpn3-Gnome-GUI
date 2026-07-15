"""Application-wide exception hierarchy.

Keeping a dedicated hierarchy lets the UI layer catch narrow, meaningful
errors (e.g. :class:`AuthenticationRequired`) instead of parsing subprocess
output or ``CalledProcessError`` messages itself.
"""

from __future__ import annotations


class OpenVpnGuiError(Exception):
    """Base class for all application-specific errors."""


class CliNotFoundError(OpenVpnGuiError):
    """Raised when the ``openvpn3`` binary cannot be located."""


class CliExecutionError(OpenVpnGuiError):
    """Raised when an ``openvpn3`` subcommand exits with a non-zero status."""

    def __init__(self, command: list[str], returncode: int, stdout: str, stderr: str):
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(
            f"Command {' '.join(command)!r} failed with exit code {returncode}: "
            f"{stderr.strip() or stdout.strip()}"
        )


class CliTimeoutError(OpenVpnGuiError):
    """Raised when an ``openvpn3`` subcommand exceeds its timeout."""


class ParseError(OpenVpnGuiError):
    """Raised when CLI output cannot be parsed into a structured model."""


class AuthenticationRequired(OpenVpnGuiError):  # noqa: N818 - models a state, reads better without Error suffix
    """Raised when a session needs additional credentials to proceed."""

    def __init__(self, session_path: str, challenge: str | None = None):
        self.session_path = session_path
        self.challenge = challenge
        super().__init__(f"Authentication required for session {session_path}")


class ProfileNotFoundError(OpenVpnGuiError):
    """Raised when a referenced profile/config does not exist."""


class SessionNotFoundError(OpenVpnGuiError):
    """Raised when a referenced session path does not exist."""


class KeyringUnavailableError(OpenVpnGuiError):
    """Raised when the Secret Service (GNOME Keyring) cannot be reached."""


class PolicyKitDeniedError(OpenVpnGuiError):
    """Raised when a privileged action is denied by PolicyKit."""
