"""Profile Manager page: import/export, search/filter/sort, tags, ACLs, notes."""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from openvpn3_gui.models.profile import Profile
from openvpn3_gui.services.openvpn_service import OpenVpnService
from openvpn3_gui.ui.dialogs.confirm_dialog import confirm
from openvpn3_gui.ui.dialogs.import_dialog import ImportProfileDialog
from openvpn3_gui.ui.widgets.profile_row import ProfileRow
from openvpn3_gui.utils.async_utils import run_async

logger = logging.getLogger(__name__)

_SORT_MODES = ["Name (A-Z)", "Name (Z-A)", "Last used", "Favorites first"]


class ProfilesPage(Gtk.Box):
    def __init__(self, openvpn_service: OpenVpnService, window) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._service = openvpn_service
        self._window = window
        self._profiles: list[Profile] = []
        self._sort_mode = 0

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_top(12)
        toolbar.set_margin_bottom(12)
        toolbar.set_margin_start(12)
        toolbar.set_margin_end(12)

        self._search_entry = Gtk.SearchEntry(placeholder_text="Search profiles…", hexpand=True)
        self._search_entry.connect("search-changed", lambda *_: self._apply_filter())
        toolbar.append(self._search_entry)

        self._sort_dropdown = Gtk.DropDown.new_from_strings(_SORT_MODES)
        self._sort_dropdown.connect("notify::selected", self._on_sort_changed)
        toolbar.append(self._sort_dropdown)

        import_button = Gtk.Button(label="Import", icon_name="list-add-symbolic")
        import_button.add_css_class("suggested-action")
        import_button.connect("clicked", self._on_import_clicked)
        toolbar.append(import_button)

        refresh_button = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Refresh")
        refresh_button.connect("clicked", lambda *_: self.refresh())
        toolbar.append(refresh_button)

        self.append(toolbar)

        self._listbox = Gtk.ListBox(css_classes=["boxed-list"])
        self._listbox.set_margin_start(12)
        self._listbox.set_margin_end(12)
        self._listbox.set_margin_bottom(12)

        self._status_page = Adw.StatusPage(
            title="No profiles yet",
            description="Import an .ovpn file to get started",
            icon_name="folder-symbolic",
        )

        self._stack = Gtk.Stack()
        self._stack.add_named(self._status_page, "empty")
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_child(self._listbox)
        self._stack.add_named(scroller, "list")
        self.append(self._stack)

        self.refresh()

    def refresh(self) -> None:
        run_async(self._service.list_profiles(), on_done=self._on_profiles_loaded, on_error=self._on_error)

    def _on_profiles_loaded(self, profiles: list[Profile]) -> None:
        self._profiles = profiles
        self._apply_filter()

    def _on_error(self, exc: Exception) -> None:
        logger.error("Failed to load profiles: %s", exc)
        toast = Adw.Toast(title=f"Could not load profiles: {exc}")
        self._get_toast_overlay().add_toast(toast)

    def _get_toast_overlay(self) -> Adw.ToastOverlay:
        # ProfilesPage is embedded directly in the window's Gtk.Stack; we
        # lazily wrap ourselves in a toast overlay on first use.
        parent = self.get_parent()
        if isinstance(parent, Adw.ToastOverlay):
            return parent
        overlay = Adw.ToastOverlay()
        return overlay

    def _on_sort_changed(self, dropdown: Gtk.DropDown, _pspec) -> None:
        self._sort_mode = dropdown.get_selected()
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self._search_entry.get_text()
        filtered = [p for p in self._profiles if p.matches_query(query)]

        if self._sort_mode == 0:
            filtered.sort(key=lambda p: p.display_name.lower())
        elif self._sort_mode == 1:
            filtered.sort(key=lambda p: p.display_name.lower(), reverse=True)
        elif self._sort_mode == 2:
            filtered.sort(key=lambda p: p.last_used or p.display_name, reverse=True)
        elif self._sort_mode == 3:
            filtered.sort(key=lambda p: (not p.favorite, p.display_name.lower()))

        for child in list(self._listbox):
            self._listbox.remove(child)

        if not filtered:
            self._stack.set_visible_child_name("empty")
            return
        self._stack.set_visible_child_name("list")

        for profile in filtered:
            row = ProfileRow(
                profile,
                on_connect=self._on_connect_requested,
                on_favorite_toggle=self._on_favorite_toggle,
                on_menu_action=self._on_row_menu_action,
            )
            self._listbox.append(row)

    def _on_import_clicked(self, _button: Gtk.Button) -> None:
        dialog = ImportProfileDialog(
            on_import_file=self._on_import_file,
            on_import_url=self._on_import_url,
        )
        dialog.present(self._window)

    def _on_import_file(self, path: str, name: str, persistent: bool) -> None:
        run_async(
            self._service.import_profile(path, name=name, persistent=persistent),
            on_done=lambda _p: self.refresh(),
            on_error=self._on_error,
        )

    def _on_import_url(self, url: str, name: str) -> None:
        run_async(
            self._service.import_profile_from_url(url, name=name),
            on_done=lambda _p: self.refresh(),
            on_error=self._on_error,
        )

    def _on_connect_requested(self, profile: Profile) -> None:
        # Delegate to the Connections page logic by switching tabs and
        # triggering connect there, so auth handling stays in one place.
        connections_page = self._window._pages["connections"]
        self._window.stack.set_visible_child_name("connections")
        connections_page.start_connection(profile)

    def _on_favorite_toggle(self, profile: Profile, favorite: bool) -> None:
        self._service.set_favorite(profile, favorite)

    def _on_row_menu_action(self, action: str, profile: Profile) -> None:
        handlers = {
            "rename": self._on_rename,
            "duplicate": self._on_duplicate,
            "export": self._on_export,
            "edit": self._on_edit_metadata,
            "acl": self._on_manage_acl,
            "remove": self._on_remove,
        }
        handler = handlers.get(action)
        if handler:
            handler(profile)

    def _on_rename(self, profile: Profile) -> None:
        dialog = Adw.AlertDialog(heading="Rename profile", body=f"New name for '{profile.name}'")
        entry = Gtk.Entry(text=profile.name)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("rename", "Rename")
        dialog.set_response_appearance("rename", Adw.ResponseAppearance.SUGGESTED)

        def _on_response(_d, response: str) -> None:
            if response == "rename":
                new_name = entry.get_text().strip()
                if new_name:
                    run_async(
                        self._service.rename_profile(profile, new_name),
                        on_done=lambda _p: self.refresh(),
                        on_error=self._on_error,
                    )

        dialog.connect("response", _on_response)
        dialog.present(self._window)

    def _on_duplicate(self, profile: Profile) -> None:
        run_async(
            self._service.duplicate_profile(profile, f"{profile.name}-copy"),
            on_done=lambda _p: self.refresh(),
            on_error=self._on_error,
        )

    def _on_export(self, profile: Profile) -> None:
        dialog = Gtk.FileDialog(title="Export profile", initial_name=f"{profile.name}.ovpn")
        dialog.save(self._window, None, lambda d, r: self._finish_export(d, r, profile))

    def _finish_export(self, dialog: Gtk.FileDialog, result, profile: Profile) -> None:
        try:
            gfile = dialog.save_finish(result)
        except Exception:  # noqa: BLE001
            return
        if gfile is None:
            return
        run_async(
            self._service.export_profile(profile, gfile.get_path()),
            on_error=self._on_error,
        )

    def _on_edit_metadata(self, profile: Profile) -> None:
        from openvpn3_gui.ui.dialogs.profile_metadata_dialog import ProfileMetadataDialog

        dialog = ProfileMetadataDialog(profile, self._service)
        dialog.present(self._window)
        dialog.connect("closed", lambda *_: self.refresh())

    def _on_manage_acl(self, profile: Profile) -> None:
        from openvpn3_gui.ui.dialogs.acl_dialog import AclDialog

        dialog = AclDialog(profile, self._service)
        dialog.present(self._window)

    def _on_remove(self, profile: Profile) -> None:
        confirm(
            self._window,
            heading=f"Remove '{profile.display_name}'?",
            body="This deletes the imported configuration and its saved credentials. This cannot be undone.",
            confirm_label="Remove",
            on_confirmed=lambda: run_async(
                self._service.remove_profile(profile),
                on_done=lambda _r: self.refresh(),
                on_error=self._on_error,
            ),
        )
