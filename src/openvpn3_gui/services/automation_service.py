"""Automation engine: connect on login/boot, scheduled reconnects, hook orchestration.

* **Connect on login** — managed via an XDG autostart entry
  (``~/.config/autostart/org.openvpn3.Gui.desktop``) that launches the app
  with ``--minimized --autoconnect``.
* **Connect on boot** — the GUI is a per-user application; a true "on boot,
  before login" connection is out of scope for a session app, so we
  generate a *systemd user* unit template the user can enable with
  lingering (``loginctl enable-linger``). The Installation Guide documents
  this; :meth:`install_boot_unit` writes the unit file.
* **Scheduled reconnect** — a lightweight in-process cron evaluator (no
  external dependency) checked once per minute.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from openvpn3_gui.models.settings import AutomationSettings

logger = logging.getLogger(__name__)

AUTOSTART_DIR = Path(
    os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
) / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "org.openvpn3.Gui.desktop"

SYSTEMD_USER_DIR = Path(
    os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
) / "systemd" / "user"
BOOT_UNIT_FILE = SYSTEMD_USER_DIR / "openvpn3-gui-autoconnect.service"

_AUTOSTART_TEMPLATE = """[Desktop Entry]
Type=Application
Name=OpenVPN3 GUI
Comment=Automatically connect to VPN on login
Exec=openvpn3-gui --minimized --autoconnect
Icon=org.openvpn3.Gui
X-GNOME-Autostart-enabled=true
"""

_BOOT_UNIT_TEMPLATE = """[Unit]
Description=OpenVPN3 GUI auto-connect (profile: {profile})
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/openvpn3 session-start --config {profile}
RemainAfterExit=yes

[Install]
WantedBy=default.target
"""


def _cron_field_matches(field: str, value: int) -> bool:
    """Minimal cron field matcher supporting ``*``, lists, ranges, and steps."""

    if field == "*":
        return True
    for part in field.split(","):
        if part.startswith("*/"):
            step = int(part[2:])
            if step and value % step == 0:
                return True
        elif "-" in part:
            lo, hi = part.split("-", 1)
            if int(lo) <= value <= int(hi):
                return True
        elif part.isdigit() and int(part) == value:
            return True
    return False


def cron_matches(expression: str, when: datetime) -> bool:
    """Evaluate a 5-field cron expression against a datetime (minute resolution)."""

    fields = expression.split()
    if len(fields) != 5:
        logger.warning("Invalid cron expression: %r", expression)
        return False
    minute, hour, day, month, weekday = fields
    return (
        _cron_field_matches(minute, when.minute)
        and _cron_field_matches(hour, when.hour)
        and _cron_field_matches(day, when.day)
        and _cron_field_matches(month, when.month)
        and _cron_field_matches(weekday, when.isoweekday() % 7)
    )


class AutomationService:
    """Owns login-autostart files, the boot unit, and the scheduled-reconnect timer."""

    def __init__(
        self,
        settings: AutomationSettings,
        reconnect_callback: Callable[[], None],
    ) -> None:
        self._settings = settings
        self._reconnect_callback = reconnect_callback
        self._task: asyncio.Task | None = None
        self._last_fired_minute: str | None = None

    def update_settings(self, settings: AutomationSettings) -> None:
        self._settings = settings
        self.apply_login_autostart()

    # -- Connect on login --------------------------------------------------

    def apply_login_autostart(self) -> None:
        if self._settings.connect_on_login:
            AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
            AUTOSTART_FILE.write_text(_AUTOSTART_TEMPLATE)
            logger.info("Installed autostart entry at %s", AUTOSTART_FILE)
        elif AUTOSTART_FILE.exists():
            AUTOSTART_FILE.unlink()
            logger.info("Removed autostart entry")

    # -- Connect on boot -----------------------------------------------------

    def install_boot_unit(self, profile_name: str) -> Path:
        """Write the systemd user unit; the user enables it per the install guide.

        The unit invokes ``openvpn3 session-start`` directly (openvpn3-linux
        handles its own privilege separation), so no root service is needed.
        """

        SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
        BOOT_UNIT_FILE.write_text(_BOOT_UNIT_TEMPLATE.format(profile=profile_name))
        logger.info("Wrote boot unit to %s", BOOT_UNIT_FILE)
        return BOOT_UNIT_FILE

    # -- Scheduled reconnect ---------------------------------------------------

    def start(self) -> None:
        if self._task is None:
            loop = asyncio.get_event_loop()
            self._task = loop.create_task(self._scheduler_loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    async def _scheduler_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            if not self._settings.scheduled_reconnect_enabled:
                continue
            now = datetime.now()
            minute_key = now.strftime("%Y%m%d%H%M")
            if minute_key == self._last_fired_minute:
                continue
            if cron_matches(self._settings.scheduled_reconnect_cron, now):
                self._last_fired_minute = minute_key
                logger.info("Scheduled reconnect fired (%s)", self._settings.scheduled_reconnect_cron)
                try:
                    self._reconnect_callback()
                except Exception:  # pragma: no cover
                    logger.exception("Scheduled reconnect callback failed")
