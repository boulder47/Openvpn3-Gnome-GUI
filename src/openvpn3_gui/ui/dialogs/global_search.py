"""Global search dialog (Ctrl+F): profiles, sessions, logs, settings, and commands."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from openvpn3_gui.utils.async_utils import run_async

_SETTINGS_INDEX = [
    ("Theme", "settings"),
    ("Language", "settings"),
    ("Notifications", "settings"),
    ("Logging", "settings"),
    ("Startup", "settings"),
    ("CLI path", "settings"),
    ("Update checks", "settings"),
    ("Automation", "settings"),
]

_COMMAND_INDEX = [
    ("Connect", "connections"),
    ("Disconnect", "connections"),
    ("Import profile", "profiles"),
    ("View live logs", "logs"),
    ("Open developer console", "developer"),
]


class GlobalSearchDialog(Adw.Dialog):
    """A single search box that fans out across every major data source."""

    def __init__(self, window) -> None:
        super().__init__(title="Search Everywhere", content_width=560, content_height=480)
        self._window = window

        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar(show_title=False)
        self._search_entry = Gtk.SearchEntry(placeholder_text="Search profiles, sessions, logs, settings…")
        self._search_entry.set_hexpand(True)
        self._search_entry.connect("search-changed", self._on_search_changed)
        header.set_title_widget(self._search_entry)
        toolbar_view.add_top_bar(header)

        self._results_box = Gtk.ListBox(css_classes=["boxed-list"])
        self._results_box.connect("row-activated", self._on_row_activated)
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_child(self._results_box)
        toolbar_view.set_content(scroller)
        self.set_child(toolbar_view)

    def present(self, parent) -> None:  # type: ignore[override]
        super().present(parent)
        self._search_entry.grab_focus()

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        query = entry.get_text().strip()
        for child in list(self._results_box):
            self._results_box.remove(child)
        if not query:
            return
        run_async(self._collect_results(query), on_done=self._populate_results)

    async def _collect_results(self, query: str) -> list[tuple[str, str, str]]:
        """Returns (title, subtitle/target-page, icon) tuples."""

        results: list[tuple[str, str, str]] = []
        service = self._window.app.openvpn_service

        profiles = await service.list_profiles()
        for profile in profiles:
            if profile.matches_query(query):
                results.append((profile.display_name, "profiles", "folder-symbolic"))

        sessions = await service.list_sessions()
        for session in sessions:
            if query.lower() in session.config_name.lower():
                results.append((f"Session: {session.config_name}", "sessions", "view-list-symbolic"))

        for label, target in _SETTINGS_INDEX:
            if query.lower() in label.lower():
                results.append((f"Setting: {label}", target, "preferences-system-symbolic"))

        for label, target in _COMMAND_INDEX:
            if query.lower() in label.lower():
                results.append((f"Command: {label}", target, "utilities-terminal-symbolic"))

        return results

    def _populate_results(self, results: list[tuple[str, str, str]]) -> None:
        if not results:
            row = Adw.ActionRow(title="No results")
            row.set_sensitive(False)
            self._results_box.append(row)
            return
        for title, target, icon in results:
            row = Adw.ActionRow(title=title)
            row.add_prefix(Gtk.Image.new_from_icon_name(icon))
            row.name = target  # type: ignore[attr-defined]
            self._results_box.append(row)

    def _on_row_activated(self, _listbox: Gtk.ListBox, row: Adw.ActionRow) -> None:
        target = getattr(row, "name", None)
        if target:
            self._window.stack.set_visible_child_name(target)
        self.close()
