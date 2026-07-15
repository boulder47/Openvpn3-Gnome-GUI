"""Editor for a profile's tags and notes (local GUI metadata, not part of the .ovpn)."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from openvpn3_gui.models.profile import Profile
from openvpn3_gui.services.openvpn_service import OpenVpnService


class ProfileMetadataDialog(Adw.Dialog):
    def __init__(self, profile: Profile, service: OpenVpnService) -> None:
        super().__init__(title=f"Edit {profile.display_name}", content_width=440)
        self._profile = profile
        self._service = service

        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        save_button = Gtk.Button(label="Save")
        save_button.add_css_class("suggested-action")
        save_button.connect("clicked", self._on_save)
        header.pack_end(save_button)
        toolbar_view.add_top_bar(header)

        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="Metadata")

        self._tags_row = Adw.EntryRow(title="Tags (comma-separated)")
        self._tags_row.set_text(", ".join(profile.tags))
        group.add(self._tags_row)

        self._notes_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD)
        self._notes_view.get_buffer().set_text(profile.notes)
        notes_frame = Gtk.Frame()
        notes_frame.set_child(self._notes_view)
        notes_row = Adw.PreferencesRow(title="Notes", activatable=False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
        box.append(Gtk.Label(label="Notes", halign=Gtk.Align.START, css_classes=["heading"]))
        box.append(notes_frame)
        notes_row.set_child(box)
        group.add(notes_row)

        page.add(group)
        toolbar_view.set_content(page)
        self.set_child(toolbar_view)

    def _on_save(self, _button: Gtk.Button) -> None:
        tags = [t.strip() for t in self._tags_row.get_text().split(",") if t.strip()]
        buffer = self._notes_view.get_buffer()
        notes = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        self._service.set_tags(self._profile, tags)
        self._service.set_notes(self._profile, notes)
        self.close()
