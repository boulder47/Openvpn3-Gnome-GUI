"""Dataclasses describing the application's persisted settings."""

from __future__ import annotations

import dataclasses
from enum import StrEnum


class ThemePreference(StrEnum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


@dataclasses.dataclass
class NotificationSettings:
    on_connect: bool = True
    on_disconnect: bool = True
    on_error: bool = True
    on_auth_request: bool = True
    on_reconnect: bool = True
    on_cert_expiry: bool = True
    cert_expiry_warning_days: int = 30


@dataclasses.dataclass
class AutomationSettings:
    connect_on_login: bool = False
    connect_on_login_profile: str | None = None
    connect_on_boot: bool = False
    reconnect_on_network_available: bool = True
    reconnect_on_resume: bool = True
    scheduled_reconnect_enabled: bool = False
    scheduled_reconnect_cron: str = "0 4 * * *"  # daily at 04:00
    pre_connect_script: str | None = None
    post_connect_script: str | None = None
    pre_disconnect_script: str | None = None
    post_disconnect_script: str | None = None
    script_env: dict[str, str] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class LoggingSettings:
    debug_mode: bool = False
    log_to_file: bool = True
    max_log_lines_in_ui: int = 5000


@dataclasses.dataclass
class AppSettings:
    theme: ThemePreference = ThemePreference.SYSTEM
    language: str = "system"
    cli_path: str | None = None
    minimize_to_tray: bool = True
    start_minimized: bool = False
    check_for_updates: bool = True
    notifications: NotificationSettings = dataclasses.field(
        default_factory=NotificationSettings
    )
    automation: AutomationSettings = dataclasses.field(default_factory=AutomationSettings)
    logging: LoggingSettings = dataclasses.field(default_factory=LoggingSettings)
    favorite_profiles: list[str] = dataclasses.field(default_factory=list)
    developer_mode: bool = False
