"""Dashboard page: at-a-glance VPN status, stats, and a live bandwidth graph."""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from openvpn3_gui.models.session import Session, SessionStatus, TrafficStats
from openvpn3_gui.services.monitor_service import HealthSnapshot, MonitorService
from openvpn3_gui.services.network_service import NetworkService
from openvpn3_gui.services.openvpn_service import OpenVpnService
from openvpn3_gui.ui.widgets.bandwidth_graph import BandwidthGraph
from openvpn3_gui.ui.widgets.status_badge import StatusBadge
from openvpn3_gui.utils.async_utils import run_async

logger = logging.getLogger(__name__)


def _format_bytes(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} PB"


def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class DashboardPage(Gtk.Box):
    """Primary landing page summarizing overall VPN + system health."""

    def __init__(
        self,
        openvpn_service: OpenVpnService,
        network_service: NetworkService,
        monitor_service: MonitorService,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._service = openvpn_service
        self._network = network_service
        self._monitor = monitor_service
        self._active_session: Session | None = None
        self._last_stats: TrafficStats | None = None
        self._tick = 0
        self._cached_public_ip: str | None = None
        self._cached_latency_ms: float | None = None

        scroller = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=900, tightening_threshold=600)
        clamp.set_margin_top(24)
        clamp.set_margin_bottom(24)
        clamp.set_margin_start(12)
        clamp.set_margin_end(12)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        clamp.set_child(content)
        scroller.set_child(clamp)
        self.append(scroller)

        self._status_row = self._build_status_banner()
        content.append(self._status_row)

        self._stats_grid = self._build_stats_grid()
        content.append(self._stats_grid)

        graph_group = Adw.PreferencesGroup(title="Live bandwidth")
        self._graph = BandwidthGraph()
        graph_row = Adw.PreferencesRow(activatable=False)
        graph_row.set_child(self._graph)
        graph_group.add(graph_row)
        content.append(graph_group)

        health_group = Adw.PreferencesGroup(title="System health")
        self._health_service_row = Adw.ActionRow(title="openvpn3 service")
        self._health_dbus_row = Adw.ActionRow(title="D-Bus")
        self._health_internet_row = Adw.ActionRow(title="Internet connectivity")
        self._health_tunnel_row = Adw.ActionRow(title="Tunnel health")
        for row in (
            self._health_service_row,
            self._health_dbus_row,
            self._health_internet_row,
            self._health_tunnel_row,
        ):
            health_group.add(row)
        content.append(health_group)

        self._monitor.subscribe(self._on_health_snapshot)
        GLib.timeout_add_seconds(2, self._refresh)
        self._refresh()

    def _build_status_banner(self) -> Gtk.Widget:
        group = Adw.PreferencesGroup()
        self._profile_row = Adw.ActionRow(title="Not connected", subtitle="No active VPN session")
        self._profile_row.add_prefix(Gtk.Image.new_from_icon_name("network-vpn-symbolic"))
        self._status_badge = StatusBadge()
        self._profile_row.add_suffix(self._status_badge)
        group.add(self._profile_row)
        return group

    def _build_stats_grid(self) -> Gtk.Widget:
        grid = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True)

        def make_stat(title: str) -> Adw.PreferencesGroup:
            g = Adw.PreferencesGroup(title=title)
            return g

        self._stat_values: dict[str, Gtk.Label] = {}

        specs = [
            ("public_ip", "Public IP"),
            ("vpn_ip", "VPN IP"),
            ("duration", "Duration"),
            ("upload", "Upload"),
            ("download", "Download"),
            ("dns", "DNS"),
            ("gateway", "Gateway"),
            ("protocol", "Protocol"),
            ("latency", "Latency"),
            ("interface", "Interface"),
        ]
        for index, (key, title) in enumerate(specs):
            row = Adw.ActionRow(title=title)
            value_label = Gtk.Label(label="—", css_classes=["dim-label"])
            row.add_suffix(value_label)
            self._stat_values[key] = value_label
            group = Adw.PreferencesGroup()
            group.add(row)
            grid.attach(group, index % 2, index // 2, 1, 1)
        return grid

    def _refresh(self) -> bool:
        run_async(self._load(), on_done=self._apply_status, on_error=self._on_error)
        return True  # keep the GLib timeout running

    async def _load(self) -> dict:
        sessions = await self._service.list_sessions()
        active = next((s for s in sessions if s.status == SessionStatus.CONNECTED), None)
        if active is not None:
            active = await self._service.get_session_detail(active)

        # Session state and traffic stats refresh every tick (2 s), but the
        # external probes (public-IP HTTP fetch, TCP latency to the VPN
        # server) are throttled to roughly every 30 s — hitting external
        # endpoints every 2 seconds is wasteful and rude.
        probe_now = self._tick % 15 == 0
        self._tick += 1
        if probe_now:
            self._cached_public_ip = await self._network.public_ip()
            if active is not None and active.server_host:
                result = await self._network.measure_latency(active.server_host)
                self._cached_latency_ms = result.latency_ms if result.success else None
        if active is not None:
            active.latency_ms = self._cached_latency_ms
        return {"active": active, "public_ip": self._cached_public_ip}

    def _apply_status(self, data: dict) -> None:
        active: Session | None = data["active"]
        public_ip = data["public_ip"]
        self._active_session = active

        if active is None:
            self._profile_row.set_title("Not connected")
            self._profile_row.set_subtitle("No active VPN session")
            self._status_badge.set_status(SessionStatus.DISCONNECTED)
            for key in self._stat_values:
                self._stat_values[key].set_label("—")
            self._stat_values["public_ip"].set_label(public_ip or "—")
            return

        self._profile_row.set_title(active.config_name)
        self._profile_row.set_subtitle(active.server_host or active.session_path)
        self._status_badge.set_status(active.status)

        duration = active.duration
        self._stat_values["duration"].set_label(
            _format_duration(duration.total_seconds()) if duration else "—"
        )
        self._stat_values["public_ip"].set_label(public_ip or "—")
        self._stat_values["vpn_ip"].set_label(active.vpn_ipv4 or active.vpn_ipv6 or "—")
        self._stat_values["upload"].set_label(_format_bytes(active.stats.bytes_out))
        self._stat_values["download"].set_label(_format_bytes(active.stats.bytes_in))
        self._stat_values["dns"].set_label(", ".join(active.dns_servers) or "—")
        self._stat_values["gateway"].set_label(active.gateway or "—")
        self._stat_values["protocol"].set_label(active.protocol or "—")
        self._stat_values["latency"].set_label(
            f"{active.latency_ms:.0f} ms" if active.latency_ms else "—"
        )
        self._stat_values["interface"].set_label(active.interface or "—")

        if self._last_stats is not None:
            elapsed = (active.stats.sampled_at - self._last_stats.sampled_at).total_seconds()
            elapsed = max(elapsed, 1.0)
            down_bps = max((active.stats.bytes_in - self._last_stats.bytes_in) / elapsed, 0)
            up_bps = max((active.stats.bytes_out - self._last_stats.bytes_out) / elapsed, 0)
            self._graph.push_sample(down_bps, up_bps)
        self._last_stats = active.stats

    def _on_error(self, exc: Exception) -> None:
        logger.warning("Dashboard refresh failed: %s", exc)

    def _on_health_snapshot(self, snapshot: HealthSnapshot) -> None:
        def _set(row: Adw.ActionRow, ok: bool) -> None:
            row.set_subtitle("OK" if ok else "Unavailable")
            icon: Gtk.Image | None = getattr(row, "_health_icon", None)
            if icon is None:
                icon = Gtk.Image()
                row.add_suffix(icon)
                row._health_icon = icon  # type: ignore[attr-defined]
            icon.set_from_icon_name(
                "emblem-ok-symbolic" if ok else "dialog-warning-symbolic"
            )

        GLib.idle_add(_set, self._health_service_row, snapshot.openvpn3_service_ok)
        GLib.idle_add(_set, self._health_dbus_row, snapshot.dbus_ok)
        GLib.idle_add(_set, self._health_internet_row, snapshot.internet_ok)
        GLib.idle_add(_set, self._health_tunnel_row, snapshot.tunnel_ok)
