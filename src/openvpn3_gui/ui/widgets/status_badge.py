"""A small colored pill/badge widget for session and log severity status."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from openvpn3_gui.models.session import SessionStatus

_STATUS_STYLE = {
    SessionStatus.CONNECTED: ("success", "Connected"),
    SessionStatus.CONNECTING: ("accent", "Connecting"),
    SessionStatus.AUTHENTICATING: ("accent", "Authenticating"),
    SessionStatus.WAIT_AUTH: ("warning", "Waiting for credentials"),
    SessionStatus.RECONNECTING: ("warning", "Reconnecting"),
    SessionStatus.PAUSED: ("dim-label", "Paused"),
    SessionStatus.DISCONNECTING: ("warning", "Disconnecting"),
    SessionStatus.DISCONNECTED: ("dim-label", "Disconnected"),
    SessionStatus.ERROR: ("error", "Error"),
    SessionStatus.UNKNOWN: ("dim-label", "Unknown"),
}


class StatusBadge(Gtk.Label):
    """Pill-shaped status label, colored via Libadwaita's semantic CSS classes."""

    def __init__(self, status: SessionStatus = SessionStatus.UNKNOWN) -> None:
        super().__init__()
        self.add_css_class("caption")
        self.add_css_class("status-badge")
        self.set_status(status)

    def set_status(self, status: SessionStatus) -> None:
        css_class, text = _STATUS_STYLE.get(status, _STATUS_STYLE[SessionStatus.UNKNOWN])
        for cls in ("success", "accent", "warning", "error", "dim-label"):
            self.remove_css_class(cls)
        self.add_css_class(css_class)
        self.set_text(text)
