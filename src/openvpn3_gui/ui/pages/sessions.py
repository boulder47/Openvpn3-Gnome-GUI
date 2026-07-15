"""Session View page: all active sessions, their PIDs/routes/DNS/ACL, and controls."""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from openvpn3_gui.models.session import Session
from openvpn3_gui.services.openvpn_service import OpenVpnService
from openvpn3_gui.ui.dialogs.confirm_dialog import confirm
from openvpn3_gui.ui.widgets.status_badge import StatusBadge
from openvpn3_gui.utils.async_utils import run_async

logger = logging.getLogger(__name__)


class SessionsPage(Gtk.Box):
    def __init__(self, openvpn_service: OpenVpnService) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._service = openvpn_service

        toolbar = Gtk.Box(margin_top=12, margin_bottom=12, margin_start=12, margin_end=12, spacing=8)
        refresh_button = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Refresh")
        refresh_button.connect("clicked", lambda *_: self.refresh())
        toolbar.append(Gtk.Label(label="Active sessions", css_classes=["title-4"], hexpand=True, halign=Gtk.Align.START))
        toolbar.append(refresh_button)
        self.append(toolbar)

        self._list = Gtk.ListBox(css_classes=["boxed-list"])
        self._list.set_margin_start(12)
        self._list.set_margin_end(12)
        self._list.set_margin_bottom(12)
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_child(self._list)
        self.append(scroller)

        GLib.timeout_add_seconds(5, self._refresh_timer)
        self.refresh()

    def _refresh_timer(self) -> bool:
        self.refresh()
        return True

    def refresh(self) -> None:
        run_async(self._service.list_sessions(), on_done=self._on_sessions_loaded, on_error=self._on_error)

    def _on_error(self, exc: Exception) -> None:
        logger.warning("Could not list sessions: %s", exc)

    def _on_sessions_loaded(self, sessions: list[Session]) -> None:
        for child in list(self._list):
            self._list.remove(child)
        if not sessions:
            placeholder = Adw.ActionRow(title="No active sessions")
            placeholder.set_sensitive(False)
            self._list.append(placeholder)
            return
        for session in sessions:
            self._list.append(self._build_row(session))

    def _build_row(self, session: Session) -> Adw.ExpanderRow:
        row = Adw.ExpanderRow(title=session.config_name, subtitle=session.session_path)
        badge = StatusBadge(session.status)
        row.add_suffix(badge)

        detail_grid = Gtk.Grid(column_spacing=16, row_spacing=6, margin_top=8, margin_bottom=8, margin_start=16, margin_end=16)
        fields = [
            ("PID", str(session.pid) if session.pid else "—"),
            ("Interface", session.interface or "—"),
            ("Owner", session.owner or "—"),
            ("Restarts", str(session.restart_count)),
        ]
        for i, (label, value) in enumerate(fields):
            detail_grid.attach(Gtk.Label(label=label, css_classes=["dim-label"], halign=Gtk.Align.START), 0, i, 1, 1)
            detail_grid.attach(Gtk.Label(label=value, halign=Gtk.Align.START), 1, i, 1, 1)
        detail_row = Adw.PreferencesRow(activatable=False)
        detail_row.set_child(detail_grid)
        row.add_row(detail_row)

        action_box = Gtk.Box(spacing=8, margin_top=8, margin_bottom=8, margin_start=16, margin_end=16)
        disconnect_btn = Gtk.Button(label="Disconnect", css_classes=["destructive-action"])
        disconnect_btn.connect("clicked", lambda *_: self._on_disconnect(session))
        restart_btn = Gtk.Button(label="Restart")
        restart_btn.connect("clicked", lambda *_: self._on_restart(session))
        action_box.append(disconnect_btn)
        action_box.append(restart_btn)
        action_row = Adw.PreferencesRow(activatable=False)
        action_row.set_child(action_box)
        row.add_row(action_row)

        run_async(self._service.get_session_detail(session), on_done=lambda s: self._populate_routes(row, s))
        return row

    def _populate_routes(self, row: Adw.ExpanderRow, session: Session) -> None:
        if not session.routes and not session.dns_servers:
            return
        text_lines = []
        if session.dns_servers:
            text_lines.append("DNS: " + ", ".join(session.dns_servers))
        for route in session.routes:
            text_lines.append(f"Route: {route.destination} via {route.gateway or '?'}")
        label = Gtk.Label(
            label="\n".join(text_lines),
            halign=Gtk.Align.START,
            margin_start=16,
            margin_end=16,
            margin_bottom=8,
            wrap=True,
        )
        info_row = Adw.PreferencesRow(activatable=False)
        info_row.set_child(label)
        row.add_row(info_row)

    def _on_disconnect(self, session: Session) -> None:
        confirm(
            self,
            heading=f"Disconnect '{session.config_name}'?",
            body="The tunnel will be torn down immediately.",
            confirm_label="Disconnect",
            on_confirmed=lambda: run_async(
                self._service.disconnect(session), on_done=lambda _r: self.refresh()
            ),
        )

    def _on_restart(self, session: Session) -> None:
        run_async(self._service.reconnect(session), on_done=lambda _r: self.refresh())
