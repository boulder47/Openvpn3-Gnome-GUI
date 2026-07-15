"""Secure credential storage using the freedesktop Secret Service (GNOME Keyring).

Plaintext secrets are never written to disk by this application. Optional
credential saving (per requirements) always goes through ``libsecret`` via
PyGObject's ``Secret`` bindings. If the Secret Service is unavailable (e.g.
headless/minimal environments), saving is disabled gracefully and the user
is prompted for credentials on every connect instead.
"""

from __future__ import annotations

import logging

from openvpn3_gui.utils.errors import KeyringUnavailableError

logger = logging.getLogger(__name__)

try:
    import gi

    gi.require_version("Secret", "1")
    from gi.repository import Secret

    _SECRET_AVAILABLE = True
except (ImportError, ValueError):  # pragma: no cover - environment dependent
    _SECRET_AVAILABLE = False
    Secret = None  # type: ignore

_SCHEMA_NAME = "org.openvpn3.Gui.Credential"

if _SECRET_AVAILABLE:
    _SCHEMA = Secret.Schema.new(
        _SCHEMA_NAME,
        Secret.SchemaFlags.NONE,
        {
            "profile": Secret.SchemaAttributeType.STRING,
            "field": Secret.SchemaAttributeType.STRING,
        },
    )


class CredentialStore:
    """Async-friendly facade over libsecret for storing VPN credentials.

    Fields stored per profile: ``username``, ``password``, ``otp_seed``
    (only if the user explicitly opts in), and ``private_key_passphrase``.
    Nothing is ever cached in process memory beyond the lifetime of a single
    connect attempt.
    """

    def __init__(self) -> None:
        if not _SECRET_AVAILABLE:
            logger.warning(
                "libsecret (Secret-1 typelib) not available; credential "
                "saving will be disabled and users must re-enter secrets "
                "each connection."
            )

    @property
    def available(self) -> bool:
        return _SECRET_AVAILABLE

    def _require_available(self) -> None:
        if not _SECRET_AVAILABLE:
            raise KeyringUnavailableError(
                "GNOME Keyring / Secret Service is not available on this system."
            )

    async def store(self, profile_name: str, field: str, secret: str) -> None:
        self._require_available()
        attributes = {"profile": profile_name, "field": field}
        label = f"OpenVPN3 GUI: {profile_name} ({field})"

        def _do_store() -> bool:
            return Secret.password_store_sync(
                _SCHEMA, attributes, Secret.COLLECTION_DEFAULT, label, secret, None
            )

        ok = await _run_blocking(_do_store)
        if not ok:
            raise KeyringUnavailableError("Failed to store credential in keyring")

    async def retrieve(self, profile_name: str, field: str) -> str | None:
        self._require_available()
        attributes = {"profile": profile_name, "field": field}

        def _do_lookup() -> str | None:
            return Secret.password_lookup_sync(_SCHEMA, attributes, None)

        return await _run_blocking(_do_lookup)

    async def delete(self, profile_name: str, field: str | None = None) -> None:
        self._require_available()
        attributes = {"profile": profile_name}
        if field:
            attributes["field"] = field

        def _do_clear() -> bool:
            return Secret.password_clear_sync(_SCHEMA, attributes, None)

        await _run_blocking(_do_clear)

    async def delete_all_for_profile(self, profile_name: str) -> None:
        await self.delete(profile_name)


async def _run_blocking(func):
    """Run a blocking libsecret call in a thread so the GLib/asyncio loop is not blocked."""

    import asyncio

    return await asyncio.get_event_loop().run_in_executor(None, func)
