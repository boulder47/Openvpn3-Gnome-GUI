"""Main application window: adaptive sidebar + content, GNOME HIG compliant."""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from openvpn3_gui.ui.pages.connections import ConnectionsPage
from openvpn3_gui.ui.pages.dashboard import DashboardPage
from openvpn3_gui.ui.pages.developer import DeveloperConsolePage
from openvpn3_gui.ui.pages.logs import LogsPage
from openvpn3_gui.ui.pages.network import NetworkPage
from openvpn3_gui.ui.pages.profiles import ProfilesPage
from openvpn3_gui.ui.pages.sessions import SessionsPage
from openvpn3_gui.ui.pages.settings_page import SettingsPage

logger = logging.getLogger(__name__)

_NAV_ITEMS = [
    ("dashboard", "Dashboard", "network-vpn-symbolic"),
    ("profiles", "Profiles", "folder-symbolic"),
    ("connections", "Connections", "network-transmit-receive-symbolic"),
    ("sessions", "Sessions", "view-list-symbolic"),
    ("logs", "Live Logs", "text-x-generic-symbolic"),
    ("network", "Network", "network-wired-symbolic"),
    ("settings", "Settings", "preferences-system-symbolic"),
    ("developer", "Developer Console", "utilities-terminal-symbolic"),
]


class OpenVpnGuiWindow(Adw.ApplicationWindow):
    """Top-level window using ``Adw.NavigationSplitView`` for the sidebar layout."""

    def __init__(self, application: Adw.Application) -> None:
        super().__init__(application=application, title="OpenVPN3")
        self.set_default_size(1180, 760)
        self.app = application

        self.split_view = Adw.NavigationSplitView()
        self.split_view.set_min_sidebar_width(220)
        self.split_view.set_max_sidebar_width(320)
        self.set_content(self.split_view)

        self.split_view.set_sidebar(self._build_sidebar())
        self.stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.CROSSFADE, hexpand=True, vexpand=True
        )
        self._pages: dict[str, Gtk.Widget] = {}
        self._build_pages()

        content_toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self._global_search_button = Gtk.ToggleButton(icon_name="system-search-symbolic")
        self._global_search_button.set_tooltip_text("Search everywhere (Ctrl+F)")
        self._global_search_button.connect("toggled", self._on_global_search_toggled)
        header.pack_end(self._global_search_button)
        content_toolbar.add_top_bar(header)
        content_toolbar.set_content(self.stack)
        self.content_page = Adw.NavigationPage(title="Dashboard", child=content_toolbar)
        self.split_view.set_content(self.content_page)

        self._install_shortcuts()
        self.connect("close-request", self._on_close_request)

        # Update the visible page's title in the content header.
        self.stack.connect("notify::visible-child-name", self._on_page_changed)
        self.stack.set_visible_child_name("dashboard")

    def _on_close_request(self, _window) -> bool:
        """Hide to tray instead of quitting when 'minimize to tray' is enabled."""

        settings = self.app.settings_controller.settings
        tray = getattr(self.app, "tray_icon", None)
        if settings.minimize_to_tray and tray is not None and tray.available:
            self.set_visible(False)
            return True  # stop the default close behavior
        return False

    # -- Sidebar --------------------------------------------------------------

    def _build_sidebar(self) -> Adw.NavigationPage:
        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="OpenVPN3", subtitle="VPN Manager"))
        toolbar_view.add_top_bar(header)

        listbox = Gtk.ListBox(css_classes=["navigation-sidebar"])
        listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)

        for name, label, icon in _NAV_ITEMS:
            row = Adw.ActionRow(title=label)
            row.add_prefix(Gtk.Image.new_from_icon_name(icon))
            row.set_activatable(True)
            row.name = name  # type: ignore[attr-defined]
            listbox.append(row)

        listbox.connect("row-activated", self._on_nav_row_activated)
        listbox.select_row(listbox.get_row_at_index(0))

        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_child(listbox)
        toolbar_view.set_content(scroller)

        return Adw.NavigationPage(title="OpenVPN3", child=toolbar_view)

    def _on_nav_row_activated(self, _listbox: Gtk.ListBox, row: Adw.ActionRow) -> None:
        name = getattr(row, "name", None)
        if name:
            self.stack.set_visible_child_name(name)
            self.split_view.set_show_content(True)

    def _on_page_changed(self, *_args) -> None:
        name = self.stack.get_visible_child_name()
        for nav_name, label, _icon in _NAV_ITEMS:
            if nav_name == name:
                self.content_page.set_title(label)
                break

    # -- Pages ------------------------------------------------------------------

    def _build_pages(self) -> None:
        app = self.app
        pages = {
            "dashboard": DashboardPage(
                openvpn_service=app.openvpn_service,
                network_service=app.network_service,
                monitor_service=app.monitor_service,
            ),
            "profiles": ProfilesPage(openvpn_service=app.openvpn_service, window=self),
            "connections": ConnectionsPage(openvpn_service=app.openvpn_service, window=self),
            "sessions": SessionsPage(openvpn_service=app.openvpn_service),
            "logs": LogsPage(openvpn_service=app.openvpn_service),
            "network": NetworkPage(
                openvpn_service=app.openvpn_service, network_service=app.network_service
            ),
            "settings": SettingsPage(
                settings_controller=app.settings_controller,
                credential_store=app.credential_store,
            ),
            "developer": DeveloperConsolePage(cli=app.cli, openvpn_service=app.openvpn_service),
        }
        for name, widget in pages.items():
            self._pages[name] = widget
            self.stack.add_named(widget, name)

    # -- Global search / shortcuts ------------------------------------------------

    def _on_global_search_toggled(self, button: Gtk.ToggleButton) -> None:
        if not button.get_active():
            return
        from openvpn3_gui.ui.dialogs.global_search import GlobalSearchDialog

        dialog = GlobalSearchDialog(window=self)
        dialog.connect("closed", lambda *_: button.set_active(False))
        dialog.present(self)

    def _install_shortcuts(self) -> None:
        controller = Gtk.ShortcutController()
        controller.set_scope(Gtk.ShortcutScope.GLOBAL)

        def add(accel: str, callback) -> None:
            trigger = Gtk.ShortcutTrigger.parse_string(accel)
            action = Gtk.CallbackAction.new(lambda *_a: (callback(), True)[1])
            controller.add_shortcut(Gtk.Shortcut.new(trigger, action))

        add("<Control>f", lambda: self._global_search_button.set_active(True))
        add("<Control>1", lambda: self.stack.set_visible_child_name("dashboard"))
        add("<Control>2", lambda: self.stack.set_visible_child_name("profiles"))
        add("<Control>3", lambda: self.stack.set_visible_child_name("connections"))
        add("<Control>4", lambda: self.stack.set_visible_child_name("sessions"))
        add("<Control>5", lambda: self.stack.set_visible_child_name("logs"))
        add("<Control>comma", lambda: self.stack.set_visible_child_name("settings"))
        add("<Control><Shift>d", lambda: self.stack.set_visible_child_name("developer"))

        self.add_controller(controller)
