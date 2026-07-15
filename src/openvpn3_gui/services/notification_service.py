"""Desktop notifications via ``Gio.Notification`` (native GNOME notifications).

Kept decoupled from :class:`OpenVpnService` so it can be unit tested without
a running GTK application (a fake ``send`` callable can be injected).
"""

from __future__ import annotations

import logging

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio  # noqa: E402

from openvpn3_gui.models.settings import NotificationSettings

logger = logging.getLogger(__name__)


class NotificationService:
    """Wraps ``Gio.Application.send_notification`` with per-event toggles."""

    def __init__(self, application: Gio.Application, settings: NotificationSettings):
        self._app = application
        self._settings = settings

    def update_settings(self, settings: NotificationSettings) -> None:
        self._settings = settings

    def _notify(self, notif_id: str, title: str, body: str, priority=Gio.NotificationPriority.NORMAL) -> None:
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        notification.set_priority(priority)
        self._app.send_notification(notif_id, notification)
        logger.debug("Notification sent: %s / %s", title, body)

    def connected(self, profile_name: str, server: str | None = None) -> None:
        if not self._settings.on_connect:
            return
        self._notify(
            f"connect-{profile_name}",
            "VPN connected",
            f"Connected to {profile_name}" + (f" ({server})" if server else ""),
        )

    def disconnected(self, profile_name: str) -> None:
        if not self._settings.on_disconnect:
            return
        self._notify(f"disconnect-{profile_name}", "VPN disconnected", f"Disconnected from {profile_name}")

    def error(self, message: str) -> None:
        if not self._settings.on_error:
            return
        self._notify(
            "error", "VPN error", message, priority=Gio.NotificationPriority.HIGH
        )

    def auth_request(self, profile_name: str, prompt: str) -> None:
        if not self._settings.on_auth_request:
            return
        self._notify(
            f"auth-{profile_name}",
            "Authentication required",
            f"{profile_name}: {prompt}",
            priority=Gio.NotificationPriority.HIGH,
        )

    def reconnecting(self, profile_name: str) -> None:
        if not self._settings.on_reconnect:
            return
        self._notify(f"reconnect-{profile_name}", "Reconnecting", f"Reconnecting {profile_name}\u2026")

    def certificate_expiring(self, profile_name: str, days_left: int) -> None:
        if not self._settings.on_cert_expiry:
            return
        self._notify(
            f"cert-expiry-{profile_name}",
            "Certificate expiring soon",
            f"The certificate for '{profile_name}' expires in {days_left} day(s).",
            priority=Gio.NotificationPriority.HIGH,
        )
