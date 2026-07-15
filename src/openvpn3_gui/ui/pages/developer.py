"""Developer Console: executed command history, stdout/stderr, exit codes, manual execution."""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from openvpn3_gui.openvpn.cli_wrapper import CommandExecution, OpenVpn3Cli
from openvpn3_gui.services.openvpn_service import OpenVpnService
from openvpn3_gui.utils.async_utils import run_async

logger = logging.getLogger(__name__)


class DeveloperConsolePage(Gtk.Box):
    """Exposes the raw CLI wrapper for troubleshooting and manual command execution.

    Manual commands still go through :class:`OpenVpn3Cli`, never a raw shell,
    so the same subprocess-safety guarantees apply here as everywhere else.
    """

    def __init__(self, cli: OpenVpn3Cli, openvpn_service: OpenVpnService) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._cli = cli
        self._service = openvpn_service

        banner = Adw.Banner(
            title="Manual commands run the real openvpn3 CLI. Use with care.",
            revealed=True,
        )
        self.append(banner)

        paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL, vexpand=True)

        # -- History list (top pane) -----------------------------------------
        history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._history_list = Gtk.ListBox(css_classes=["boxed-list"])
        self._history_list.connect("row-selected", self._on_history_row_selected)
        history_scroller = Gtk.ScrolledWindow(vexpand=True)
        history_scroller.set_child(self._history_list)
        history_box.append(Gtk.Label(label="Command history", css_classes=["heading"], halign=Gtk.Align.START, margin_start=12, margin_top=8))
        history_box.append(history_scroller)
        paned.set_start_child(history_box)

        # -- Detail + manual execution (bottom pane) -------------------------
        detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)

        self._detail_view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        detail_scroller = Gtk.ScrolledWindow(min_content_height=180)
        detail_scroller.set_child(self._detail_view)
        detail_box.append(detail_scroller)

        exec_row = Gtk.Box(spacing=8)
        self._command_entry = Gtk.Entry(placeholder_text="e.g. sessions-list, configs-list, version", hexpand=True)
        self._command_entry.connect("activate", self._on_run_clicked)
        exec_row.append(self._command_entry)
        run_button = Gtk.Button(label="Run", css_classes=["suggested-action"])
        run_button.connect("clicked", self._on_run_clicked)
        exec_row.append(run_button)
        detail_box.append(exec_row)

        paned.set_end_child(detail_box)
        self.append(paned)

        self._cli.history.subscribe(lambda execution: GLib.idle_add(self._add_history_row, execution))
        for execution in self._cli.history.snapshot():
            self._add_history_row(execution)

    def _add_history_row(self, execution: CommandExecution) -> None:
        title = " ".join(execution.command[1:]) or execution.command[0]
        subtitle = f"exit={execution.returncode} · {execution.duration_ms:.0f} ms"
        row = Adw.ActionRow(title=title, subtitle=subtitle)
        icon_name = "emblem-ok-symbolic" if execution.returncode == 0 else "dialog-error-symbolic"
        row.add_prefix(Gtk.Image.new_from_icon_name(icon_name))
        row.execution = execution  # type: ignore[attr-defined]
        self._history_list.prepend(row)

    def _on_history_row_selected(self, _listbox: Gtk.ListBox, row: Adw.ActionRow | None) -> None:
        if row is None:
            return
        execution: CommandExecution = row.execution
        buffer = self._detail_view.get_buffer()
        text = (
            f"$ {' '.join(execution.command)}\n\n"
            f"Exit code: {execution.returncode}\n"
            f"Duration: {execution.duration_ms:.1f} ms\n"
            f"Started: {execution.started_at.isoformat()}\n\n"
            f"--- stdout ---\n{execution.stdout}\n"
            f"--- stderr ---\n{execution.stderr}\n"
        )
        buffer.set_text(text)

    def _on_run_clicked(self, _widget: Gtk.Widget) -> None:
        command_text = self._command_entry.get_text().strip()
        if not command_text:
            return
        args = command_text.split()
        run_async(self._cli.run(args), on_error=self._on_run_error)

    def _on_run_error(self, exc: Exception) -> None:
        buffer = self._detail_view.get_buffer()
        buffer.set_text(f"Command failed:\n{exc}")
