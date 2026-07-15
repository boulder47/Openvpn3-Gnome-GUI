"""Live Logs page: real-time viewer with search/regex filter, severity colors, export."""

from __future__ import annotations

import logging
import re
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from openvpn3_gui.models.log_entry import LogSeverity
from openvpn3_gui.services.openvpn_service import OpenVpnService
from openvpn3_gui.utils.async_utils import run_async
from openvpn3_gui.utils.logging_config import LOG_BUFFER, LogRecordEntry

logger = logging.getLogger(__name__)

_SEVERITY_TAGS = {
    LogSeverity.FATAL: "sev-error",
    LogSeverity.CRITICAL: "sev-error",
    LogSeverity.ERROR: "sev-error",
    LogSeverity.WARNING: "sev-warning",
    LogSeverity.NOTICE: "sev-notice",
    LogSeverity.INFO: "sev-info",
    LogSeverity.VERBOSE: "sev-dim",
    LogSeverity.DEBUG: "sev-dim",
    LogSeverity.TRACE: "sev-dim",
}


class LogsPage(Gtk.Box):
    def __init__(self, openvpn_service: OpenVpnService) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._service = openvpn_service
        self._all_lines: list[str] = []
        self._streaming_task = None

        toolbar = Gtk.Box(spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self._search_entry = Gtk.SearchEntry(placeholder_text="Filter (plain text)…", hexpand=True)
        self._search_entry.connect("search-changed", lambda *_: self._apply_filter())
        toolbar.append(self._search_entry)

        self._regex_toggle = Gtk.ToggleButton(label=".*", tooltip_text="Treat filter as regex")
        self._regex_toggle.connect("toggled", lambda *_: self._apply_filter())
        toolbar.append(self._regex_toggle)

        self._debug_toggle = Gtk.ToggleButton(label="Debug mode")
        self._debug_toggle.connect("toggled", self._on_debug_toggled)
        toolbar.append(self._debug_toggle)

        self._live_toggle = Gtk.ToggleButton(label="Live tail", active=True)
        self._live_toggle.connect("toggled", self._on_live_toggled)
        toolbar.append(self._live_toggle)

        export_button = Gtk.Button(icon_name="document-save-symbolic", tooltip_text="Export logs")
        export_button.connect("clicked", self._on_export_clicked)
        toolbar.append(export_button)

        copy_button = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text="Copy visible logs")
        copy_button.connect("clicked", self._on_copy_clicked)
        toolbar.append(copy_button)

        clear_button = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text="Clear")
        clear_button.connect("clicked", self._on_clear_clicked)
        toolbar.append(clear_button)

        self.append(toolbar)

        self._text_view = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        buffer = self._text_view.get_buffer()
        for tag_name in set(_SEVERITY_TAGS.values()):
            buffer.create_tag(tag_name)
        self._apply_tag_colors()

        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_child(self._text_view)
        scroller.set_margin_start(12)
        scroller.set_margin_end(12)
        scroller.set_margin_bottom(12)
        self.append(scroller)

        LOG_BUFFER.subscribe(self._on_app_log)
        for entry in LOG_BUFFER.snapshot():
            self._append_app_log(entry)

        self._start_live_tail()

    def _apply_tag_colors(self) -> None:
        buffer = self._text_view.get_buffer()
        colors = {
            "sev-error": Gdk.RGBA(red=0.86, green=0.2, blue=0.2, alpha=1),
            "sev-warning": Gdk.RGBA(red=0.85, green=0.55, blue=0.0, alpha=1),
            "sev-notice": Gdk.RGBA(red=0.2, green=0.45, blue=0.85, alpha=1),
            "sev-info": Gdk.RGBA(red=0.55, green=0.55, blue=0.55, alpha=1),
            "sev-dim": Gdk.RGBA(red=0.6, green=0.6, blue=0.6, alpha=1),
        }
        for name, rgba in colors.items():
            tag = buffer.get_tag_table().lookup(name)
            if tag:
                tag.set_property("foreground-rgba", rgba)

    def _start_live_tail(self) -> None:
        self._streaming_task = run_async(self._tail_openvpn_logs(), on_error=self._on_tail_error)

    async def _tail_openvpn_logs(self) -> None:
        verbosity = 6 if self._debug_toggle.get_active() else 4
        try:
            async for line in self._service.tail_logs(verbosity=verbosity):
                GLib.idle_add(self._append_openvpn_line, line)
        except Exception as exc:  # noqa: BLE001
            logger.debug("openvpn3 log stream ended: %s", exc)

    def _on_tail_error(self, exc: Exception) -> None:
        logger.info("Live openvpn3 log stream unavailable: %s", exc)

    def _on_debug_toggled(self, _button: Gtk.ToggleButton) -> None:
        if self._streaming_task:
            self._streaming_task.cancel()
        self._start_live_tail()

    def _on_live_toggled(self, button: Gtk.ToggleButton) -> None:
        if not button.get_active() and self._streaming_task:
            self._streaming_task.cancel()
        elif button.get_active():
            self._start_live_tail()

    def _append_openvpn_line(self, line: str) -> None:
        self._all_lines.append(line)
        self._apply_filter(new_line=line)

    def _on_app_log(self, entry: LogRecordEntry) -> None:
        GLib.idle_add(self._append_app_log, entry)

    def _append_app_log(self, entry: LogRecordEntry) -> None:
        line = f"[{entry.timestamp.strftime('%H:%M:%S')}] {entry.level:<8} {entry.logger}: {entry.message}"
        self._all_lines.append(line)
        self._apply_filter(new_line=line)

    def _severity_tag_for_line(self, line: str) -> str:
        upper = line.upper()
        if "ERROR" in upper or "FATAL" in upper or "CRITICAL" in upper:
            return "sev-error"
        if "WARN" in upper:
            return "sev-warning"
        if "NOTICE" in upper:
            return "sev-notice"
        if "DEBUG" in upper or "TRACE" in upper or "VERBOSE" in upper:
            return "sev-dim"
        return "sev-info"

    def _matches_filter(self, line: str) -> bool:
        query = self._search_entry.get_text()
        if not query:
            return True
        if self._regex_toggle.get_active():
            try:
                return re.search(query, line) is not None
            except re.error:
                return False
        return query.lower() in line.lower()

    def _apply_filter(self, new_line: str | None = None) -> None:
        if new_line is not None and self._matches_filter(new_line):
            self._append_to_view(new_line)
            return
        if new_line is not None:
            return  # filtered out, nothing to do
        # Full re-render (search text or regex toggle changed).
        buffer = self._text_view.get_buffer()
        buffer.set_text("")
        for line in self._all_lines:
            if self._matches_filter(line):
                self._append_to_view(line)

    def _append_to_view(self, line: str) -> None:
        buffer = self._text_view.get_buffer()
        tag_name = self._severity_tag_for_line(line)
        end_iter = buffer.get_end_iter()
        buffer.insert_with_tags_by_name(end_iter, line + "\n", tag_name)
        self._text_view.scroll_to_iter(buffer.get_end_iter(), 0.0, False, 0, 0)

    def _on_clear_clicked(self, _button: Gtk.Button) -> None:
        self._all_lines.clear()
        self._text_view.get_buffer().set_text("")

    def _on_copy_clicked(self, _button: Gtk.Button) -> None:
        buffer = self._text_view.get_buffer()
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        clipboard = self.get_clipboard()
        clipboard.set(text)

    def _on_export_clicked(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog(
            title="Export logs",
            initial_name=f"openvpn3-logs-{datetime.now():%Y%m%d-%H%M%S}.log",
        )
        dialog.save(None, None, self._finish_export)

    def _finish_export(self, dialog: Gtk.FileDialog, result) -> None:
        try:
            gfile = dialog.save_finish(result)
        except Exception:  # noqa: BLE001
            return
        if gfile is None:
            return
        buffer = self._text_view.get_buffer()
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        try:
            with open(gfile.get_path(), "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            logger.error("Failed to export logs: %s", exc)
