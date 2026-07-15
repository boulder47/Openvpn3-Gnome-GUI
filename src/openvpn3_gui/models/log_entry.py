"""Data model for a single OpenVPN 3 log line (as opposed to app-internal logs)."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import IntEnum


class LogSeverity(IntEnum):
    """Mirrors openvpn3-linux's syslog-style severity levels."""

    FATAL = 0
    CRITICAL = 1
    ERROR = 2
    WARNING = 3
    NOTICE = 4
    INFO = 5
    VERBOSE = 6
    DEBUG = 7
    TRACE = 8

    @classmethod
    def from_text(cls, text: str) -> LogSeverity:
        mapping = {
            "fatal": cls.FATAL,
            "critical": cls.CRITICAL,
            "error": cls.ERROR,
            "warn": cls.WARNING,
            "warning": cls.WARNING,
            "notice": cls.NOTICE,
            "info": cls.INFO,
            "verbose": cls.VERBOSE,
            "debug": cls.DEBUG,
            "trace": cls.TRACE,
        }
        return mapping.get(text.strip().lower(), cls.INFO)

    @property
    def css_class(self) -> str:
        """Libadwaita/GTK CSS class used for colored severity badges."""

        return {
            LogSeverity.FATAL: "error",
            LogSeverity.CRITICAL: "error",
            LogSeverity.ERROR: "error",
            LogSeverity.WARNING: "warning",
            LogSeverity.NOTICE: "accent",
            LogSeverity.INFO: "dim-label",
            LogSeverity.VERBOSE: "dim-label",
            LogSeverity.DEBUG: "dim-label",
            LogSeverity.TRACE: "dim-label",
        }[self]


@dataclasses.dataclass
class LogEntry:
    timestamp: datetime
    severity: LogSeverity
    module: str | None
    message: str
    session_path: str | None = None
    raw_line: str = ""

    def matches(self, query: str, min_severity: LogSeverity | None = None) -> bool:
        if min_severity is not None and self.severity > min_severity:
            return False
        if not query:
            return True
        return query.lower() in self.message.lower()
