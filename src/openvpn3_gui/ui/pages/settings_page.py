"""Settings page: theme, language, notifications, logging, startup, CLI path, automation."""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from openvpn3_gui.models.settings import ThemePreference
from openvpn3_gui.settings.app_settings import SettingsController
from openvpn3_gui.storage.keyring import CredentialStore

logger = logging.getLogger(__name__)

_THEME_OPTIONS = ["System", "Light", "Dark"]
_THEME_VALUES = [ThemePreference.SYSTEM, ThemePreference.LIGHT, ThemePreference.DARK]

_LANGUAGE_OPTIONS = ["System default", "English", "Deutsch", "Español", "Français", "日本語"]
_LANGUAGE_CODES = ["system", "en", "de", "es", "fr", "ja"]


class SettingsPage(Gtk.Box):
    def __init__(self, settings_controller: SettingsController, credential_store: CredentialStore) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._controller = settings_controller
        self._credentials = credential_store

        prefs = Adw.PreferencesPage()
        prefs.add(self._build_appearance_group())
        prefs.add(self._build_startup_group())
        prefs.add(self._build_notifications_group())
        prefs.add(self._build_logging_group())
        prefs.add(self._build_advanced_group())
        prefs.add(self._build_import_export_group())

        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_child(prefs)
        self.append(scroller)

    # -- Appearance ---------------------------------------------------------

    def _build_appearance_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Appearance")

        theme_row = Adw.ComboRow(title="Theme", model=Gtk.StringList.new(_THEME_OPTIONS))
        theme_row.set_selected(_THEME_VALUES.index(self._controller.settings.theme))
        theme_row.connect("notify::selected", self._on_theme_changed)
        group.add(theme_row)

        language_row = Adw.ComboRow(title="Language", model=Gtk.StringList.new(_LANGUAGE_OPTIONS))
        try:
            language_row.set_selected(_LANGUAGE_CODES.index(self._controller.settings.language))
        except ValueError:
            language_row.set_selected(0)
        language_row.connect("notify::selected", self._on_language_changed)
        group.add(language_row)

        return group

    def _on_theme_changed(self, row: Adw.ComboRow, _pspec) -> None:
        value = _THEME_VALUES[row.get_selected()]
        self._controller.update(lambda s: setattr(s, "theme", value))

    def _on_language_changed(self, row: Adw.ComboRow, _pspec) -> None:
        value = _LANGUAGE_CODES[row.get_selected()]
        self._controller.update(lambda s: setattr(s, "language", value))

    # -- Startup / tray -------------------------------------------------------

    def _build_startup_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Startup and tray")

        minimize_row = Adw.SwitchRow(title="Minimize to tray", subtitle="Keep running in the background when closed")
        minimize_row.set_active(self._controller.settings.minimize_to_tray)
        minimize_row.connect(
            "notify::active",
            lambda r, _p: self._controller.update(lambda s: setattr(s, "minimize_to_tray", r.get_active())),
        )
        group.add(minimize_row)

        start_min_row = Adw.SwitchRow(title="Start minimized")
        start_min_row.set_active(self._controller.settings.start_minimized)
        start_min_row.connect(
            "notify::active",
            lambda r, _p: self._controller.update(lambda s: setattr(s, "start_minimized", r.get_active())),
        )
        group.add(start_min_row)

        login_row = Adw.SwitchRow(title="Connect on login")
        login_row.set_active(self._controller.settings.automation.connect_on_login)
        login_row.connect(
            "notify::active",
            lambda r, _p: self._controller.update(
                lambda s: setattr(s.automation, "connect_on_login", r.get_active())
            ),
        )
        group.add(login_row)

        boot_row = Adw.SwitchRow(title="Connect on boot", subtitle="Requires a systemd user service (see Installation Guide)")
        boot_row.set_active(self._controller.settings.automation.connect_on_boot)
        boot_row.connect(
            "notify::active",
            lambda r, _p: self._controller.update(
                lambda s: setattr(s.automation, "connect_on_boot", r.get_active())
            ),
        )
        group.add(boot_row)

        network_row = Adw.SwitchRow(title="Reconnect when network becomes available")
        network_row.set_active(self._controller.settings.automation.reconnect_on_network_available)
        network_row.connect(
            "notify::active",
            lambda r, _p: self._controller.update(
                lambda s: setattr(s.automation, "reconnect_on_network_available", r.get_active())
            ),
        )
        group.add(network_row)

        resume_row = Adw.SwitchRow(title="Reconnect on resume from suspend")
        resume_row.set_active(self._controller.settings.automation.reconnect_on_resume)
        resume_row.connect(
            "notify::active",
            lambda r, _p: self._controller.update(
                lambda s: setattr(s.automation, "reconnect_on_resume", r.get_active())
            ),
        )
        group.add(resume_row)

        cron_row = Adw.EntryRow(title="Scheduled reconnect (cron expression)")
        cron_row.set_text(self._controller.settings.automation.scheduled_reconnect_cron)
        cron_row.connect(
            "changed",
            lambda r: self._controller.update(
                lambda s: setattr(s.automation, "scheduled_reconnect_cron", r.get_text())
            ),
        )
        group.add(cron_row)

        return group

    # -- Notifications --------------------------------------------------------

    def _build_notifications_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Notifications")
        notif = self._controller.settings.notifications

        def add_toggle(title: str, attr: str) -> None:
            row = Adw.SwitchRow(title=title)
            row.set_active(getattr(notif, attr))
            row.connect(
                "notify::active",
                lambda r, _p, a=attr: self._controller.update(
                    lambda s: setattr(s.notifications, a, r.get_active())
                ),
            )
            group.add(row)

        add_toggle("On connect", "on_connect")
        add_toggle("On disconnect", "on_disconnect")
        add_toggle("On error", "on_error")
        add_toggle("On authentication request", "on_auth_request")
        add_toggle("On reconnect", "on_reconnect")
        add_toggle("On certificate expiry", "on_cert_expiry")

        expiry_row = Adw.SpinRow.new_with_range(1, 180, 1)
        expiry_row.set_title("Certificate expiry warning (days before)")
        expiry_row.set_value(notif.cert_expiry_warning_days)
        expiry_row.connect(
            "notify::value",
            lambda r, _p: self._controller.update(
                lambda s: setattr(s.notifications, "cert_expiry_warning_days", int(r.get_value()))
            ),
        )
        group.add(expiry_row)

        return group

    # -- Logging --------------------------------------------------------------

    def _build_logging_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Logging")
        logging_settings = self._controller.settings.logging

        debug_row = Adw.SwitchRow(title="Debug mode", subtitle="Verbose logs from both the app and openvpn3")
        debug_row.set_active(logging_settings.debug_mode)
        debug_row.connect(
            "notify::active",
            lambda r, _p: self._controller.update(lambda s: setattr(s.logging, "debug_mode", r.get_active())),
        )
        group.add(debug_row)

        file_row = Adw.SwitchRow(title="Log to file", subtitle="~/.local/state/openvpn3-gui/openvpn3-gui.log")
        file_row.set_active(logging_settings.log_to_file)
        file_row.connect(
            "notify::active",
            lambda r, _p: self._controller.update(lambda s: setattr(s.logging, "log_to_file", r.get_active())),
        )
        group.add(file_row)

        return group

    # -- Advanced --------------------------------------------------------------

    def _build_advanced_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Advanced")

        cli_row = Adw.EntryRow(title="openvpn3 CLI path (blank = auto-detect via PATH)")
        cli_row.set_text(self._controller.settings.cli_path or "")
        cli_row.connect(
            "changed",
            lambda r: self._controller.update(lambda s: setattr(s, "cli_path", r.get_text() or None)),
        )
        group.add(cli_row)

        update_row = Adw.SwitchRow(title="Check for updates on startup")
        update_row.set_active(self._controller.settings.check_for_updates)
        update_row.connect(
            "notify::active",
            lambda r, _p: self._controller.update(lambda s: setattr(s, "check_for_updates", r.get_active())),
        )
        group.add(update_row)

        dev_row = Adw.SwitchRow(title="Developer mode", subtitle="Enables the Developer Console tab")
        dev_row.set_active(self._controller.settings.developer_mode)
        dev_row.connect(
            "notify::active",
            lambda r, _p: self._controller.update(lambda s: setattr(s, "developer_mode", r.get_active())),
        )
        group.add(dev_row)

        keyring_row = Adw.ActionRow(
            title="Credential storage",
            subtitle="Available (GNOME Keyring / Secret Service)"
            if self._credentials.available
            else "Unavailable — credentials will not be saved between sessions",
        )
        group.add(keyring_row)

        scripts_group_label = Adw.ActionRow(title="Pre/post connect scripts are configured per-profile", subtitle="See a profile's context menu")
        group.add(scripts_group_label)

        return group

    # -- Import/export --------------------------------------------------------

    def _build_import_export_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Backup and restore settings")

        row = Adw.ActionRow(title="Export settings")
        export_button = Gtk.Button(label="Export…")
        export_button.connect("clicked", self._on_export_clicked)
        row.add_suffix(export_button)
        group.add(row)

        import_row = Adw.ActionRow(title="Import settings")
        import_button = Gtk.Button(label="Import…")
        import_button.connect("clicked", self._on_import_clicked)
        import_row.add_suffix(import_button)
        group.add(import_row)

        return group

    def _on_export_clicked(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog(title="Export settings", initial_name="openvpn3-gui-settings.json")
        dialog.save(None, None, self._finish_export)

    def _finish_export(self, dialog: Gtk.FileDialog, result) -> None:
        try:
            gfile = dialog.save_finish(result)
        except Exception:  # noqa: BLE001
            return
        if gfile:
            self._controller.export_to(gfile.get_path())

    def _on_import_clicked(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog(title="Import settings")
        dialog.open(None, None, self._finish_import)

    def _finish_import(self, dialog: Gtk.FileDialog, result) -> None:
        try:
            gfile = dialog.open_finish(result)
        except Exception:  # noqa: BLE001
            return
        if gfile:
            self._controller.import_from(gfile.get_path())
