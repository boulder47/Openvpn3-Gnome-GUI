"""An ``Adw.ActionRow`` representing one profile inside the Profile Manager list."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk  # noqa: E402

from openvpn3_gui.models.profile import Profile

_MENU_ACTIONS = [
    ("rename", "Rename"),
    ("duplicate", "Duplicate"),
    ("export", "Export…"),
    ("edit", "Edit tags/notes"),
    ("acl", "Manage ACL"),
    ("remove", "Remove"),
]


class ProfileRow(Adw.ActionRow):
    """Displays a profile's name, remote host, tags, and quick actions."""

    def __init__(
        self,
        profile: Profile,
        on_connect: Callable[[Profile], None],
        on_favorite_toggle: Callable[[Profile, bool], None],
        on_menu_action: Callable[[str, Profile], None],
    ) -> None:
        super().__init__(title=profile.display_name)
        self.profile = profile

        subtitle_parts = []
        if profile.remote_host:
            subtitle_parts.append(profile.remote_host)
        if profile.tags:
            subtitle_parts.append(", ".join(f"#{t}" for t in profile.tags))
        self.set_subtitle(" · ".join(subtitle_parts) if subtitle_parts else "No remote info")

        icon = Gtk.Image.new_from_icon_name("network-vpn-symbolic")
        self.add_prefix(icon)

        self.favorite_button = Gtk.ToggleButton(
            icon_name="starred-symbolic" if profile.favorite else "non-starred-symbolic"
        )
        self.favorite_button.set_active(profile.favorite)
        self.favorite_button.add_css_class("flat")
        self.favorite_button.connect("toggled", self._on_favorite_toggled, on_favorite_toggle)
        self.add_suffix(self.favorite_button)

        connect_button = Gtk.Button(icon_name="media-playback-start-symbolic")
        connect_button.add_css_class("flat")
        connect_button.set_tooltip_text("Connect")
        connect_button.connect("clicked", lambda _b: on_connect(profile))
        self.add_suffix(connect_button)

        # Gtk.MenuButton has no "clicked" signal in GTK4 — it shows its
        # popover automatically from a menu model. Build the model and its
        # backing action group once, up front, rather than lazily.
        menu_button = Gtk.MenuButton(icon_name="view-more-symbolic")
        menu_button.add_css_class("flat")
        menu_button.set_menu_model(self._build_menu_model())
        self.insert_action_group("profile", self._build_action_group(profile, on_menu_action))
        self.add_suffix(menu_button)

        self.set_activatable_widget(connect_button)

    @staticmethod
    def _build_menu_model() -> Gio.Menu:
        menu = Gio.Menu()
        for action_name, label in _MENU_ACTIONS:
            menu.append(label, f"profile.{action_name}")
        return menu

    @staticmethod
    def _build_action_group(
        profile: Profile, on_menu_action: Callable[[str, Profile], None]
    ) -> Gio.SimpleActionGroup:
        action_group = Gio.SimpleActionGroup()
        for action_name, _label in _MENU_ACTIONS:
            action = Gio.SimpleAction.new(action_name, None)
            action.connect(
                "activate", lambda _a, _p, n=action_name: on_menu_action(n, profile)
            )
            action_group.add_action(action)
        return action_group

    def _on_favorite_toggled(self, button: Gtk.ToggleButton, callback) -> None:
        active = button.get_active()
        button.set_icon_name("starred-symbolic" if active else "non-starred-symbolic")
        callback(self.profile, active)
