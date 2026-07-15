"""Structured logging configuration for OpenVPN3 GUI.

All modules obtain loggers via ``logging.getLogger(__name__)``. This module
configures a single, application-wide handler chain so log output is
consistent whether it lands in the systemd journal, a rotating file, or the
in-app Developer Console (see :mod:`openvpn3_gui.ui.pages.developer`).
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

APP_LOG_DIR = Path(
    os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))
) / "openvpn3-gui"


@dataclass
class LogRecordEntry:
    """A single structured log line, kept in-memory for the Live Logs page."""

    timestamp: datetime
    level: str
    logger: str
    message: str
    source: str = "app"  # "app" | "openvpn3" | "dbus"

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "logger": self.logger,
            "message": self.message,
            "source": self.source,
        }


class InMemoryLogBuffer:
    """A bounded ring buffer that the UI polls/subscribes to for live logs."""

    def __init__(self, maxlen: int = 5000) -> None:
        self._buffer: deque[LogRecordEntry] = deque(maxlen=maxlen)
        self._listeners: list = []

    def append(self, entry: LogRecordEntry) -> None:
        self._buffer.append(entry)
        for listener in list(self._listeners):
            try:
                listener(entry)
            except Exception:  # pragma: no cover - listeners must not raise
                logging.getLogger(__name__).exception("Log listener failed")

    def subscribe(self, callback) -> None:
        self._listeners.append(callback)

    def unsubscribe(self, callback) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def snapshot(self) -> list[LogRecordEntry]:
        return list(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()


LOG_BUFFER = InMemoryLogBuffer()


class BufferHandler(logging.Handler):
    """Feeds every emitted record into :data:`LOG_BUFFER` for the UI."""

    def emit(self, record: logging.LogRecord) -> None:
        entry = LogRecordEntry(
            timestamp=datetime.fromtimestamp(record.created, tz=UTC),
            level=record.levelname,
            logger=record.name,
            message=record.getMessage(),
            source="app",
        )
        LOG_BUFFER.append(entry)


class JsonFormatter(logging.Formatter):
    """Newline-delimited JSON formatter for the on-disk log file."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(debug: bool = False, log_to_file: bool = True) -> None:
    """Initialise root logging handlers. Safe to call once at startup."""

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    root.handlers.clear()

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    root.addHandler(console)
    root.addHandler(BufferHandler())

    if log_to_file:
        APP_LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            APP_LOG_DIR / "openvpn3-gui.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
        )
        file_handler.setFormatter(JsonFormatter())
        root.addHandler(file_handler)

    logging.getLogger(__name__).info("Logging configured (debug=%s)", debug)
