"""Tray/status icon via the StatusNotifierItem (SNI) D-Bus protocol.

GNOME Shell removed legacy tray icons; SNI is the modern protocol used by
the AppIndicator/KStatusNotifierItem ecosystem and rendered by the widely
installed "AppIndicator and KStatusNotifierItem Support" Shell extension
(preinstalled on Ubuntu). We prefer ``AyatanaAppIndicator3`` when its
typelib is present (Ubuntu ships it), and degrade gracefully to
"no tray, background-run only" otherwise — the app still minimizes to the
background and can be re-activated via its single-instance GApplication.

The quick menu offers: current status, connect for each favorite profile,
disconnect-all, show window, and quit.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

try:
    import gi

    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator

    gi.require_version("Gtk", "3.0")  # Ayatana indicator menus are GTK3-based
    _TRAY_AVAILABLE = True
except (ImportError, ValueError):  # pragma: no cover - environment dependent
    _TRAY_AVAILABLE = False
    AppIndicator = None  # type: ignore

_ICON_CONNECTED = "network-vpn-symbolic"
_ICON_DISCONNECTED = "network-vpn-disabled-symbolic"
_ICON_ACQUIRING = "network-vpn-acquiring-symbolic"


class TrayIcon:
    """Facade so the rest of the app never needs to know whether a tray exists."""

    def __init__(
        self,
        on_show_window: Callable[[], None],
        on_quit: Callable[[], None],
        on_connect_profile: Callable[[str], None],
        on_disconnect_all: Callable[[], None],
    ) -> None:
        self._on_show_window = on_show_window
        self._on_quit = on_quit
        self._on_connect_profile = on_connect_profile
        self._on_disconnect_all = on_disconnect_all
        self._indicator = None
        self._favorites: list[str] = []
        self._status_text = "Disconnected"

        if not _TRAY_AVAILABLE:
            logger.info("AppIndicator not available; tray icon disabled")
            return

        self._indicator = AppIndicator.Indicator.new(
            "openvpn3-gui",
            _ICON_DISCONNECTED,
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self._indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self._rebuild_menu()

    @property
    def available(self) -> bool:
        return self._indicator is not None

    def set_connected(self, connected: bool, profile_name: str | None = None) -> None:
        self._status_text = f"Connected — {profile_name}" if connected else "Disconnected"
        if self._indicator is None:
            return
        self._indicator.set_icon_full(
            _ICON_CONNECTED if connected else _ICON_DISCONNECTED, self._status_text
        )
        self._rebuild_menu()

    def set_connecting(self) -> None:
        self._status_text = "Connecting…"
        if self._indicator is not None:
            self._indicator.set_icon_full(_ICON_ACQUIRING, self._status_text)

    def set_favorites(self, favorite_profile_names: list[str]) -> None:
        self._favorites = favorite_profile_names
        if self._indicator is not None:
            self._rebuild_menu()

    def _rebuild_menu(self) -> None:  # pragma: no cover - requires GTK3 tray env
        from gi.repository import Gtk as Gtk3

        menu = Gtk3.Menu()

        status_item = Gtk3.MenuItem(label=self._status_text)
        status_item.set_sensitive(False)
        menu.append(status_item)
        menu.append(Gtk3.SeparatorMenuItem())

        for name in self._favorites:
            item = Gtk3.MenuItem(label=f"Connect: {name}")
            item.connect("activate", lambda _i, n=name: self._on_connect_profile(n))
            menu.append(item)
        if self._favorites:
            menu.append(Gtk3.SeparatorMenuItem())

        disconnect_item = Gtk3.MenuItem(label="Disconnect all")
        disconnect_item.connect("activate", lambda _i: self._on_disconnect_all())
        menu.append(disconnect_item)

        show_item = Gtk3.MenuItem(label="Show window")
        show_item.connect("activate", lambda _i: self._on_show_window())
        menu.append(show_item)

        quit_item = Gtk3.MenuItem(label="Quit")
        quit_item.connect("activate", lambda _i: self._on_quit())
        menu.append(quit_item)

        menu.show_all()
        self._indicator.set_menu(menu)
