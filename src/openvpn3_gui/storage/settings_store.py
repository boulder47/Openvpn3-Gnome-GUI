"""Persistence for :class:`openvpn3_gui.models.settings.AppSettings`.

Settings are stored as JSON under ``$XDG_CONFIG_HOME/openvpn3-gui/settings.json``.
A GSettings schema (``data/org.openvpn3.Gui.gschema.xml``) is shipped so the
same keys are also inspectable/scriptable via ``gsettings`` and integrate
with GNOME Settings search, but the JSON file remains the source of truth
for portability (e.g. running outside a full GNOME session or in a Flatpak
without the schema compiled) — the two are kept in sync by
:class:`SettingsStore.save`.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
from pathlib import Path
from typing import Any

from openvpn3_gui.models.settings import (
    AppSettings,
    AutomationSettings,
    LoggingSettings,
    NotificationSettings,
    ThemePreference,
)

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(
    os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
) / "openvpn3-gui"
SETTINGS_FILE = CONFIG_DIR / "settings.json"


def _asdict(settings: AppSettings) -> dict[str, Any]:
    payload = dataclasses.asdict(settings)
    payload["theme"] = settings.theme.value
    return payload


def _from_dict(data: dict[str, Any]) -> AppSettings:
    notif = NotificationSettings(**data.get("notifications", {}))
    automation = AutomationSettings(**data.get("automation", {}))
    logging_settings = LoggingSettings(**data.get("logging", {}))
    theme = ThemePreference(data.get("theme", ThemePreference.SYSTEM.value))
    return AppSettings(
        theme=theme,
        language=data.get("language", "system"),
        cli_path=data.get("cli_path"),
        minimize_to_tray=data.get("minimize_to_tray", True),
        start_minimized=data.get("start_minimized", False),
        check_for_updates=data.get("check_for_updates", True),
        notifications=notif,
        automation=automation,
        logging=logging_settings,
        favorite_profiles=data.get("favorite_profiles", []),
        developer_mode=data.get("developer_mode", False),
    )


class SettingsStore:
    """Load/save :class:`AppSettings` to disk, with import/export support."""

    def __init__(self, path: Path = SETTINGS_FILE) -> None:
        self._path = path

    def load(self) -> AppSettings:
        if not self._path.exists():
            logger.info("No settings file found at %s; using defaults", self._path)
            return AppSettings()
        try:
            data = json.loads(self._path.read_text())
            return _from_dict(data)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Failed to parse settings file, using defaults: %s", exc)
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(_asdict(settings), indent=2))
        logger.debug("Settings saved to %s", self._path)

    def export_to(self, settings: AppSettings, destination: Path) -> None:
        destination.write_text(json.dumps(_asdict(settings), indent=2))

    def import_from(self, source: Path) -> AppSettings:
        data = json.loads(source.read_text())
        return _from_dict(data)
