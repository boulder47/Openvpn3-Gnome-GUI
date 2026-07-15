"""System-level D-Bus signal watchers used by the Automation engine.

Two things the Automation settings promise ("reconnect on network available",
"reconnect on resume from suspend") require listening to system services
that have nothing to do with openvpn3 itself:

* ``org.freedesktop.NetworkManager`` — ``StateChanged`` signal for
  connectivity transitions.
* ``org.freedesktop.login1`` — ``PrepareForSleep`` signal, emitted just
  before suspend (``False``) and immediately after resume (``True``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

logger = logging.getLogger(__name__)

NM_BUS_NAME = "org.freedesktop.NetworkManager"
LOGIN1_BUS_NAME = "org.freedesktop.login1"


class NetworkAvailabilityWatcher:
    """Invokes ``on_available()`` whenever NetworkManager reports full connectivity."""

    STATE_CONNECTED_GLOBAL = 70

    def __init__(self, on_available: Callable[[], None]) -> None:
        self._on_available = on_available
        self._bus: Gio.DBusConnection | None = None
        self._sub_id: int | None = None

    def start(self) -> None:
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error as exc:
            logger.warning("Cannot watch NetworkManager state: %s", exc)
            return
        self._sub_id = self._bus.signal_subscribe(
            NM_BUS_NAME,
            NM_BUS_NAME,
            "StateChanged",
            "/org/freedesktop/NetworkManager",
            None,
            Gio.DBusSignalFlags.NONE,
            self._handle_state_changed,
        )

    def _handle_state_changed(
        self, connection, sender_name, object_path, interface_name, signal_name, parameters
    ) -> None:
        try:
            (state,) = parameters.unpack()
        except (ValueError, AttributeError):
            return
        if state == self.STATE_CONNECTED_GLOBAL:
            logger.info("NetworkManager reports global connectivity")
            self._on_available()

    def stop(self) -> None:
        if self._bus and self._sub_id is not None:
            self._bus.signal_unsubscribe(self._sub_id)
            self._sub_id = None


class ResumeWatcher:
    """Invokes ``on_resume()`` when logind reports the system woke from suspend."""

    def __init__(self, on_resume: Callable[[], None]) -> None:
        self._on_resume = on_resume
        self._bus: Gio.DBusConnection | None = None
        self._sub_id: int | None = None

    def start(self) -> None:
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error as exc:
            logger.warning("Cannot watch logind sleep signals: %s", exc)
            return
        self._sub_id = self._bus.signal_subscribe(
            LOGIN1_BUS_NAME,
            LOGIN1_BUS_NAME + ".Manager",
            "PrepareForSleep",
            "/org/freedesktop/login1",
            None,
            Gio.DBusSignalFlags.NONE,
            self._handle_prepare_for_sleep,
        )

    def _handle_prepare_for_sleep(
        self, connection, sender_name, object_path, interface_name, signal_name, parameters
    ) -> None:
        try:
            (about_to_sleep,) = parameters.unpack()
        except (ValueError, AttributeError):
            return
        if not about_to_sleep:
            logger.info("System resumed from suspend")
            self._on_resume()

    def stop(self) -> None:
        if self._bus and self._sub_id is not None:
            self._bus.signal_unsubscribe(self._sub_id)
            self._sub_id = None
