"""The Adw.Application: composition root for all services (dependency injection)."""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib  # noqa: E402

from openvpn3_gui import __app_id__, __version__
from openvpn3_gui.dbus.log_watcher import NetworkAvailabilityWatcher, ResumeWatcher
from openvpn3_gui.openvpn.cli_wrapper import OpenVpn3Cli
from openvpn3_gui.services.automation_service import AutomationService
from openvpn3_gui.services.backup_service import BackupService, TrafficHistoryStore
from openvpn3_gui.services.certificate_service import CertificateService
from openvpn3_gui.services.monitor_service import MonitorService
from openvpn3_gui.services.network_service import NetworkService
from openvpn3_gui.services.notification_service import NotificationService
from openvpn3_gui.services.openvpn_service import OpenVpnService
from openvpn3_gui.services.plugin_service import PluginContext, PluginService
from openvpn3_gui.services.script_runner import ScriptRunner
from openvpn3_gui.settings.app_settings import SettingsController
from openvpn3_gui.storage.keyring import CredentialStore
from openvpn3_gui.storage.profile_store import ProfileMetadataStore
from openvpn3_gui.tray.status_icon import TrayIcon
from openvpn3_gui.utils.async_utils import get_or_create_loop, run_async
from openvpn3_gui.utils.i18n import init_i18n

logger = logging.getLogger(__name__)


class OpenVpnGuiApplication(Adw.Application):
    """Composition root. Builds every service once and hands them to the window."""

    def __init__(self) -> None:
        super().__init__(
            application_id=__app_id__,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.settings_controller = SettingsController()
        cli_path = self.settings_controller.settings.cli_path
        self.cli = OpenVpn3Cli(binary_path=cli_path)
        self.credential_store = CredentialStore()
        self.profile_metadata_store = ProfileMetadataStore()
        self.openvpn_service = OpenVpnService(
            cli=self.cli,
            credential_store=self.credential_store,
            metadata_store=self.profile_metadata_store,
        )
        self.network_service = NetworkService()
        self.notification_service: NotificationService | None = None
        self.monitor_service = MonitorService(self.openvpn_service, self.network_service)
        self.script_runner = ScriptRunner()
        self.certificate_service = CertificateService()
        self.backup_service = BackupService(self.openvpn_service)
        self.traffic_history = TrafficHistoryStore()
        self.plugin_service = PluginService()
        self.automation_service = AutomationService(
            self.settings_controller.settings.automation,
            reconnect_callback=lambda: run_async(self._reconnect_dead_sessions()),
        )
        self.tray_icon: TrayIcon | None = None

        self._network_watcher: NetworkAvailabilityWatcher | None = None
        self._resume_watcher: ResumeWatcher | None = None

        self._install_actions()

    def do_startup(self) -> None:  # noqa: N802 - GObject virtual method
        Adw.Application.do_startup(self)
        get_or_create_loop()  # start the GLib-driven asyncio pump early
        init_i18n(self.settings_controller.settings.language)
        self.notification_service = NotificationService(
            self, self.settings_controller.settings.notifications
        )
        self._apply_theme()
        self._load_css()
        self.settings_controller.subscribe(self._on_settings_changed)
        self._setup_automation_watchers()
        self.monitor_service.start()
        self.automation_service.apply_login_autostart()
        self.automation_service.start()
        self._setup_tray()
        if self.settings_controller.settings.developer_mode:
            self.plugin_service.load_all(
                PluginContext(
                    openvpn_service=self.openvpn_service,
                    network_service=self.network_service,
                    settings=self.settings_controller.settings,
                    show_toast=lambda msg: logger.info("Plugin toast: %s", msg),
                )
            )
        run_async(self._check_certificate_expiry())
        logger.info("OpenVPN3 GUI v%s starting up", __version__)

    def _load_css(self) -> None:
        from pathlib import Path

        import gi as _gi

        _gi.require_version("Gdk", "4.0")
        from gi.repository import Gdk, Gtk

        candidates = [
            Path("/app/share/openvpn3-gui/style.css"),  # Flatpak
            Path("/usr/share/openvpn3-gui/style.css"),
            Path(__file__).resolve().parents[2] / "data" / "style.css",  # dev tree
        ]
        css_file = next((p for p in candidates if p.exists()), None)
        if css_file is None:
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(str(css_file))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def _on_settings_changed(self, settings) -> None:
        self._apply_theme()
        if self.notification_service is not None:
            self.notification_service.update_settings(settings.notifications)
        self.automation_service.update_settings(settings.automation)

    def _setup_tray(self) -> None:
        self.tray_icon = TrayIcon(
            on_show_window=lambda: GLib.idle_add(self.activate),
            on_quit=lambda: GLib.idle_add(self.quit),
            on_connect_profile=self._tray_connect_profile,
            on_disconnect_all=lambda: run_async(self._disconnect_all_sessions()),
        )
        self.tray_icon.set_favorites(self.settings_controller.settings.favorite_profiles)

    def _tray_connect_profile(self, profile_name: str) -> None:
        async def _connect() -> None:
            profiles = await self.openvpn_service.list_profiles()
            profile = next((p for p in profiles if p.name == profile_name), None)
            if profile is None:
                logger.warning("Tray connect: profile %s not found", profile_name)
                return
            async for _line in self.openvpn_service.connect(profile):
                pass
            if self.notification_service:
                self.notification_service.connected(profile_name)

        run_async(_connect())

    async def _disconnect_all_sessions(self) -> None:
        for session in await self.openvpn_service.list_sessions():
            if session.is_active:
                await self.openvpn_service.disconnect(session)

    async def _check_certificate_expiry(self) -> None:
        notif = self.settings_controller.settings.notifications
        if not notif.on_cert_expiry or not self.certificate_service.available:
            return
        try:
            profiles = await self.openvpn_service.list_profiles()
            detailed = []
            for profile in profiles:
                try:
                    detailed.append(await self.openvpn_service.get_profile_detail(profile))
                except Exception:  # noqa: BLE001
                    logger.debug("Skipping cert check for %s (detail unavailable)", profile.name)
                    continue
            for profile, days_left in self.certificate_service.profiles_expiring_within(
                detailed, notif.cert_expiry_warning_days
            ):
                if self.notification_service:
                    self.notification_service.certificate_expiring(profile.name, days_left)
        except Exception:  # noqa: BLE001
            logger.exception("Certificate expiry check failed")

    def do_activate(self) -> None:  # noqa: N802
        from openvpn3_gui.ui.window import OpenVpnGuiWindow

        window = self.props.active_window
        if window is None:
            window = OpenVpnGuiWindow(application=self)
        window.present()

    def _apply_theme(self) -> None:
        from openvpn3_gui.models.settings import ThemePreference

        style_manager = self.get_style_manager()
        mapping = {
            ThemePreference.SYSTEM: Adw.ColorScheme.DEFAULT,
            ThemePreference.LIGHT: Adw.ColorScheme.FORCE_LIGHT,
            ThemePreference.DARK: Adw.ColorScheme.FORCE_DARK,
        }
        style_manager.set_color_scheme(mapping[self.settings_controller.settings.theme])

    def _setup_automation_watchers(self) -> None:
        automation = self.settings_controller.settings.automation

        if automation.reconnect_on_network_available:
            self._network_watcher = NetworkAvailabilityWatcher(self._on_network_available)
            self._network_watcher.start()

        if automation.reconnect_on_resume:
            self._resume_watcher = ResumeWatcher(self._on_resume)
            self._resume_watcher.start()

    def _on_network_available(self) -> None:
        logger.info("Network became available; checking for sessions to reconnect")
        run_async(self._reconnect_dead_sessions())

    def _on_resume(self) -> None:
        logger.info("Resumed from suspend; checking for sessions to reconnect")
        run_async(self._reconnect_dead_sessions())

    async def _reconnect_dead_sessions(self) -> None:
        from openvpn3_gui.models.session import SessionStatus

        sessions = await self.openvpn_service.list_sessions()
        for session in sessions:
            if session.auto_reconnect and session.status in (
                SessionStatus.DISCONNECTED,
                SessionStatus.ERROR,
            ):
                await self.openvpn_service.reconnect(session)

    def _install_actions(self) -> None:
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<primary>q"])

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about)
        self.add_action(about_action)

    def _on_about(self, *_args) -> None:
        about = Adw.AboutDialog(
            application_name="OpenVPN3 GUI",
            application_icon=__app_id__,
            developer_name="OpenVPN3 GUI Contributors",
            version=__version__,
            license_type=Adw.License.GPL_3_0,
            website="https://github.com/example/openvpn3-gui",
            issue_url="https://github.com/example/openvpn3-gui/issues",
            comments="A native GTK4/Libadwaita frontend for openvpn3-linux.",
        )
        about.present(self.props.active_window)
