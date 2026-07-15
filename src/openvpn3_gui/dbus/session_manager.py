"""Direct D-Bus helpers that complement the ``openvpn3`` CLI wrapper.

The CLI is the primary interface (per project requirements: "the UI never
calls subprocesses directly", routed through the openvpn service layer).
However some things are far more efficient/idiomatic over D-Bus directly:

* Checking whether ``net.openvpn.v3.sessions`` / ``net.openvpn.v3.configuration``
  are actually owned on the system bus (cheaper and more reliable than
  shelling out).
* Subscribing to ``PropertiesChanged``/``StatusChange`` signals so the UI
  can react to session state changes in real time instead of polling
  ``sessions-list`` on a timer.

This module only *reads* bus state / subscribes to signals — it never
invokes privileged methods directly; all mutating actions still go through
``openvpn3`` (which itself talks to the D-Bus services under the hood,
using its own D-Bus policy and PolicyKit integration).
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

logger = logging.getLogger(__name__)

SESSIONS_BUS_NAME = "net.openvpn.v3.sessions"
CONFIGURATION_BUS_NAME = "net.openvpn.v3.configuration"
LOG_BUS_NAME = "net.openvpn.v3.log"


@dataclasses.dataclass
class DBusAvailability:
    available: bool
    sessions_owned: bool = False
    configuration_owned: bool = False
    log_owned: bool = False


async def check_dbus_service() -> DBusAvailability:
    """Check whether the openvpn3-linux system-bus services are running."""

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    except GLib.Error as exc:
        logger.warning("Could not connect to system bus: %s", exc)
        return DBusAvailability(available=False)

    def _name_has_owner(name: str) -> bool:
        try:
            result = bus.call_sync(
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                "NameHasOwner",
                GLib.Variant("(s)", (name,)),
                GLib.VariantType("(b)"),
                Gio.DBusCallFlags.NONE,
                2000,
                None,
            )
            return result.unpack()[0]
        except GLib.Error as exc:
            logger.debug("NameHasOwner check failed for %s: %s", name, exc)
            return False

    sessions_owned = _name_has_owner(SESSIONS_BUS_NAME)
    configuration_owned = _name_has_owner(CONFIGURATION_BUS_NAME)
    log_owned = _name_has_owner(LOG_BUS_NAME)

    return DBusAvailability(
        available=sessions_owned or configuration_owned,
        sessions_owned=sessions_owned,
        configuration_owned=configuration_owned,
        log_owned=log_owned,
    )


class SessionSignalWatcher:
    """Subscribes to ``StatusChange``/``PropertiesChanged`` on the sessions service.

    UI pages call :meth:`start` and register a callback to be notified the
    moment a session's state changes, instead of relying purely on a
    polling timer (the polling timer remains as a fallback / for systems
    where signal subscription isn't permitted by the D-Bus policy).
    """

    def __init__(self, on_change: Callable[[str], None]) -> None:
        self._on_change = on_change
        self._subscription_id: int | None = None
        self._bus: Gio.DBusConnection | None = None

    def start(self) -> None:
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error as exc:
            logger.warning("Cannot watch session signals: %s", exc)
            return

        self._subscription_id = self._bus.signal_subscribe(
            SESSIONS_BUS_NAME,
            None,  # any interface
            None,  # any signal (StatusChange, AttentionRequired, etc.)
            None,  # any object path
            None,
            Gio.DBusSignalFlags.NONE,
            self._handle_signal,
        )

    def _handle_signal(
        self, connection, sender_name, object_path, interface_name, signal_name, parameters
    ) -> None:
        logger.debug("D-Bus signal %s on %s", signal_name, object_path)
        self._on_change(object_path)

    def stop(self) -> None:
        if self._bus and self._subscription_id is not None:
            self._bus.signal_unsubscribe(self._subscription_id)
            self._subscription_id = None
