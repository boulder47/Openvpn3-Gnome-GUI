"""Connection Manager page: connect/disconnect/reconnect, auth flow, history."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from openvpn3_gui.models.profile import Profile
from openvpn3_gui.services.openvpn_service import OpenVpnService
from openvpn3_gui.ui.dialogs.auth_dialog import AuthPromptDialog
from openvpn3_gui.utils.async_utils import run_async

logger = logging.getLogger(__name__)


@dataclass
class ConnectionHistoryItem:
    profile_name: str
    started_at: datetime
    ended_at: datetime | None = None
    outcome: str = "in progress"


class ConnectionsPage(Gtk.Box):
    """Lets the user pick a profile, connect, watch the live auth transcript, and disconnect."""

    def __init__(self, openvpn_service: OpenVpnService, window) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._service = openvpn_service
        self._window = window
        self._history: list[ConnectionHistoryItem] = []
        self._active_profile: Profile | None = None

        toolbar = Adw.ToolbarView()
        header_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
        )

        self._profile_dropdown = Gtk.DropDown(model=Gtk.StringList())
        self._profiles: list[Profile] = []
        header_box.append(Gtk.Label(label="Profile:"))
        header_box.append(self._profile_dropdown)

        self._connect_button = Gtk.Button(label="Connect", css_classes=["suggested-action"])
        self._connect_button.connect("clicked", self._on_connect_clicked)
        header_box.append(self._connect_button)

        self._disconnect_button = Gtk.Button(label="Disconnect", css_classes=["destructive-action"])
        self._disconnect_button.set_sensitive(False)
        self._disconnect_button.connect("clicked", self._on_disconnect_clicked)
        header_box.append(self._disconnect_button)

        self._reconnect_button = Gtk.Button(label="Reconnect")
        self._reconnect_button.set_sensitive(False)
        self._reconnect_button.connect("clicked", self._on_reconnect_clicked)
        header_box.append(self._reconnect_button)

        self._auto_reconnect_switch = Gtk.Switch(active=True, valign=Gtk.Align.CENTER)
        header_box.append(Gtk.Label(label="Auto-reconnect:"))
        header_box.append(self._auto_reconnect_switch)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_start(12)
        content.set_margin_end(12)
        content.append(header_box)

        transcript_group = Adw.PreferencesGroup(title="Connection transcript")
        self._transcript_view = Gtk.TextView(
            editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR
        )
        transcript_scroller = Gtk.ScrolledWindow(min_content_height=220)
        transcript_scroller.set_child(self._transcript_view)
        transcript_row = Adw.PreferencesRow(activatable=False)
        transcript_row.set_child(transcript_scroller)
        transcript_group.add(transcript_row)
        content.append(transcript_group)

        history_group = Adw.PreferencesGroup(title="Connection history")
        self._history_list = Gtk.ListBox(css_classes=["boxed-list"])
        history_row = Adw.PreferencesRow(activatable=False)
        history_row.set_child(self._history_list)
        history_group.add(history_row)
        content.append(history_group)

        toolbar.set_content(content)
        self.append(toolbar)

        self._refresh_profiles()

    def _refresh_profiles(self) -> None:
        run_async(self._service.list_profiles(), on_done=self._on_profiles_loaded)

    def _on_profiles_loaded(self, profiles: list[Profile]) -> None:
        self._profiles = profiles
        model = Gtk.StringList()
        for profile in profiles:
            model.append(profile.display_name)
        self._profile_dropdown.set_model(model)

    def start_connection(self, profile: Profile) -> None:
        """Entry point used by the Profiles page's quick-connect button."""

        if profile not in self._profiles:
            self._profiles.append(profile)
            self._on_profiles_loaded(self._profiles)
        try:
            index = self._profiles.index(profile)
            self._profile_dropdown.set_selected(index)
        except ValueError:
            pass
        self._connect(profile)

    def _on_connect_clicked(self, _button: Gtk.Button) -> None:
        index = self._profile_dropdown.get_selected()
        if index == Gtk.INVALID_LIST_POSITION or index >= len(self._profiles):
            return
        self._connect(self._profiles[index])

    def _connect(self, profile: Profile) -> None:
        self._active_profile = profile
        self._append_transcript(f"--- Connecting to {profile.display_name} ---")
        self._connect_button.set_sensitive(False)
        history_item = ConnectionHistoryItem(profile.display_name, datetime.now())
        self._history.insert(0, history_item)
        self._render_history()
        run_async(
            self._run_connect_stream(profile, history_item),
            on_error=lambda exc: self._on_connect_failed(exc, history_item),
        )

    async def _run_connect_stream(self, profile: Profile, history_item: ConnectionHistoryItem) -> None:
        async def credential_callback(prompt: str):
            return await self._prompt_credential(profile, prompt)

        async for line in self._service.connect(profile, credential_callback=credential_callback):
            GLib.idle_add(self._append_transcript, line)
        history_item.ended_at = datetime.now()
        history_item.outcome = "connected"
        GLib.idle_add(self._on_connected, profile)

    async def _prompt_credential(self, profile: Profile, prompt: str) -> str | None:
        is_secret = "password" in prompt.lower() or "pin" in prompt.lower()
        dialog = AuthPromptDialog(prompt, is_secret=is_secret)
        value, remember = await dialog.run(self._window)
        if value and remember:
            field = self._service._guess_credential_field(prompt)  # noqa: SLF001
            await self._service.save_credential(profile, field, value)
        return value

    def _on_connected(self, profile: Profile) -> None:
        self._connect_button.set_sensitive(True)
        self._disconnect_button.set_sensitive(True)
        self._reconnect_button.set_sensitive(True)
        self._append_transcript(f"--- Connected to {profile.display_name} ---")
        self._render_history()

    def _on_connect_failed(self, exc: Exception, history_item: ConnectionHistoryItem) -> None:
        history_item.ended_at = datetime.now()
        history_item.outcome = f"failed: {exc}"
        self._connect_button.set_sensitive(True)
        self._append_transcript(f"--- Connection failed: {exc} ---")
        self._render_history()

    def _on_disconnect_clicked(self, _button: Gtk.Button) -> None:
        run_async(self._disconnect_active())

    async def _disconnect_active(self) -> None:
        sessions = await self._service.list_sessions()
        if not self._active_profile:
            return
        for session in sessions:
            if session.config_name == self._active_profile.name:
                await self._service.disconnect(session)
        GLib.idle_add(self._on_disconnected)

    def _on_disconnected(self) -> None:
        self._disconnect_button.set_sensitive(False)
        self._reconnect_button.set_sensitive(False)
        self._append_transcript("--- Disconnected ---")

    def _on_reconnect_clicked(self, _button: Gtk.Button) -> None:
        run_async(self._reconnect_active())

    async def _reconnect_active(self) -> None:
        sessions = await self._service.list_sessions()
        if not self._active_profile:
            return
        for session in sessions:
            if session.config_name == self._active_profile.name:
                await self._service.set_auto_reconnect(
                    session, self._auto_reconnect_switch.get_active()
                )
                await self._service.reconnect(session)
        GLib.idle_add(lambda: self._append_transcript("--- Reconnecting ---"))

    def _append_transcript(self, line: str) -> None:
        buffer = self._transcript_view.get_buffer()
        buffer.insert(buffer.get_end_iter(), line + "\n")
        self._transcript_view.scroll_to_iter(buffer.get_end_iter(), 0.0, False, 0, 0)

    def _render_history(self) -> None:
        for child in list(self._history_list):
            self._history_list.remove(child)
        for item in self._history[:20]:
            row = Adw.ActionRow(title=item.profile_name, subtitle=item.outcome)
            row.add_suffix(Gtk.Label(label=item.started_at.strftime("%H:%M:%S")))
            self._history_list.append(row)
