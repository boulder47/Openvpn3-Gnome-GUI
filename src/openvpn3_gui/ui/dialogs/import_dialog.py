"""Profile import dialog: local ``.ovpn`` file or a remote URL."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk  # noqa: E402


class ImportProfileDialog(Adw.Dialog):
    """Collects a source (file picker or URL) plus a display name and persistence flag."""

    def __init__(
        self,
        on_import_file: Callable[[str, str, bool], None],
        on_import_url: Callable[[str, str], None],
    ) -> None:
        super().__init__(title="Import Profile", content_width=460)
        self._on_import_file = on_import_file
        self._on_import_url = on_import_url
        self._selected_path: str | None = None

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(Adw.HeaderBar())

        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="Source")

        self.name_row = Adw.EntryRow(title="Profile name")
        group.add(self.name_row)

        self.persistent_row = Adw.SwitchRow(title="Persistent", subtitle="Keep after logout")
        self.persistent_row.set_active(True)
        group.add(self.persistent_row)

        file_row = Adw.ActionRow(title="Import from file", subtitle="Choose a .ovpn file")
        file_button = Gtk.Button(label="Browse…")
        file_button.connect("clicked", self._on_browse_clicked)
        file_row.add_suffix(file_button)
        file_row.set_activatable_widget(file_button)
        group.add(file_row)

        self.url_row = Adw.EntryRow(title="…or import from URL")
        import_url_button = Gtk.Button(label="Fetch")
        import_url_button.add_css_class("flat")
        import_url_button.connect("clicked", self._on_import_url_clicked)
        self.url_row.add_suffix(import_url_button)
        group.add(self.url_row)

        page.add(group)
        toolbar_view.set_content(page)
        self.set_child(toolbar_view)

    def _on_browse_clicked(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog(title="Select an OpenVPN profile")
        filter_ovpn = Gtk.FileFilter(name="OpenVPN profiles (*.ovpn, *.conf)")
        filter_ovpn.add_pattern("*.ovpn")
        filter_ovpn.add_pattern("*.conf")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filter_ovpn)
        dialog.set_filters(filters)
        dialog.open(None, None, self._on_file_selected)

    def _on_file_selected(self, dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
        try:
            gfile = dialog.open_finish(result)
        except Exception:  # noqa: BLE001 - user cancelled or platform error
            return
        if gfile is None:
            return
        path = gfile.get_path()
        name = self.name_row.get_text() or gfile.get_basename().rsplit(".", 1)[0]
        self._on_import_file(path, name, self.persistent_row.get_active())
        self.close()

    def _on_import_url_clicked(self, _button: Gtk.Button) -> None:
        url = self.url_row.get_text().strip()
        if not url:
            return
        name = self.name_row.get_text() or url.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        self._on_import_url(url, name)
        self.close()
