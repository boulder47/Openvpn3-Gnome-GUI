"""Access-control list (ACL) editor for a profile.

Wraps ``openvpn3 config-acl``: public access toggle, grant/revoke per-user
access, and lock-down. All mutations go through
:meth:`OpenVpnService.set_profile_acl`.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from openvpn3_gui.models.profile import Profile
from openvpn3_gui.services.openvpn_service import OpenVpnService
from openvpn3_gui.utils.async_utils import run_async


class AclDialog(Adw.Dialog):
    def __init__(self, profile: Profile, service: OpenVpnService) -> None:
        super().__init__(title=f"Access control — {profile.display_name}", content_width=440)
        self._profile = profile
        self._service = service

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(Adw.HeaderBar())

        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(title="Sharing")

        self._public_row = Adw.SwitchRow(
            title="Public access", subtitle="Allow any local user to use this profile"
        )
        self._public_row.set_active(bool(profile.acl and profile.acl.public))
        self._public_row.connect("notify::active", self._on_public_toggled)
        group.add(self._public_row)

        self._lockdown_row = Adw.SwitchRow(
            title="Lock down", subtitle="Only the owner may view secrets"
        )
        self._lockdown_row.set_active(bool(profile.acl and profile.acl.locked_down))
        self._lockdown_row.connect("notify::active", self._on_lockdown_toggled)
        group.add(self._lockdown_row)

        grant_group = Adw.PreferencesGroup(
            title="Granted users",
            description="System usernames allowed to use this profile",
        )
        self._grant_entry = Adw.EntryRow(title="Add username")
        add_button = Gtk.Button(icon_name="list-add-symbolic")
        add_button.add_css_class("flat")
        add_button.connect("clicked", self._on_grant_clicked)
        self._grant_entry.add_suffix(add_button)
        grant_group.add(self._grant_entry)

        self._users_list = Gtk.ListBox(css_classes=["boxed-list"])
        for user in (profile.acl.granted_users if profile.acl else []):
            self._users_list.append(self._make_user_row(user))
        users_row = Adw.PreferencesRow(activatable=False)
        users_row.set_child(self._users_list)
        grant_group.add(users_row)

        page.add(group)
        page.add(grant_group)
        toolbar_view.set_content(page)
        self.set_child(toolbar_view)

    def _make_user_row(self, username: str) -> Adw.ActionRow:
        row = Adw.ActionRow(title=username)
        revoke_button = Gtk.Button(icon_name="list-remove-symbolic")
        revoke_button.add_css_class("flat")
        revoke_button.connect("clicked", lambda _b, u=username, r=row: self._on_revoke_clicked(u, r))
        row.add_suffix(revoke_button)
        return row

    def _on_public_toggled(self, row: Adw.SwitchRow, _pspec) -> None:
        run_async(self._service.set_profile_acl(self._profile, public=row.get_active()))

    def _on_lockdown_toggled(self, row: Adw.SwitchRow, _pspec) -> None:
        run_async(self._service.set_profile_acl(self._profile, lock_down=row.get_active()))

    def _on_grant_clicked(self, _button: Gtk.Button) -> None:
        username = self._grant_entry.get_text().strip()
        if not username:
            return
        run_async(self._service.set_profile_acl(self._profile, grant_user=username))
        self._users_list.append(self._make_user_row(username))
        self._grant_entry.set_text("")

    def _on_revoke_clicked(self, username: str, row: Adw.ActionRow) -> None:
        run_async(self._service.set_profile_acl(self._profile, revoke_user=username))
        self._users_list.remove(row)
