"""Network page: tunnel info, routes, MTU, split tunneling, DNS leak/latency/public IP tests."""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from openvpn3_gui.models.session import Session, SessionStatus
from openvpn3_gui.services.network_service import NetworkService
from openvpn3_gui.services.openvpn_service import OpenVpnService
from openvpn3_gui.utils.async_utils import run_async

logger = logging.getLogger(__name__)


class NetworkPage(Gtk.Box):
    def __init__(self, openvpn_service: OpenVpnService, network_service: NetworkService) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._service = openvpn_service
        self._network = network_service

        scroller = Gtk.ScrolledWindow(vexpand=True)
        clamp = Adw.Clamp(maximum_size=800)
        clamp.set_margin_top(24)
        clamp.set_margin_bottom(24)
        clamp.set_margin_start(12)
        clamp.set_margin_end(12)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        clamp.set_child(content)
        scroller.set_child(clamp)
        self.append(scroller)

        tunnel_group = Adw.PreferencesGroup(title="Tunnel")
        self._interface_row = Adw.ActionRow(title="Interface")
        self._mtu_row = Adw.ActionRow(title="MTU")
        self._ipv4_row = Adw.ActionRow(title="IPv4 address")
        self._ipv6_row = Adw.ActionRow(title="IPv6 address")
        self._split_tunnel_row = Adw.SwitchRow(
            title="Split tunneling",
            subtitle="Route only specific subnets through the VPN (requires profile support)",
        )
        for row in (self._interface_row, self._mtu_row, self._ipv4_row, self._ipv6_row, self._split_tunnel_row):
            tunnel_group.add(row)
        content.append(tunnel_group)

        routes_group = Adw.PreferencesGroup(title="Routes")
        self._routes_list = Gtk.ListBox(css_classes=["boxed-list"])
        routes_row = Adw.PreferencesRow(activatable=False)
        routes_row.set_child(self._routes_list)
        routes_group.add(routes_row)
        content.append(routes_group)

        diagnostics_group = Adw.PreferencesGroup(title="Diagnostics")
        public_ip_row = Adw.ActionRow(title="Public IP checker")
        self._public_ip_result = Gtk.Label(label="—")
        public_ip_row.add_suffix(self._public_ip_result)
        check_ip_button = Gtk.Button(label="Check")
        check_ip_button.connect("clicked", self._on_check_public_ip)
        public_ip_row.add_suffix(check_ip_button)
        diagnostics_group.add(public_ip_row)

        latency_row = Adw.ActionRow(title="Latency test", subtitle="Measures TCP connect time to the VPN gateway")
        self._latency_result = Gtk.Label(label="—")
        latency_row.add_suffix(self._latency_result)
        latency_button = Gtk.Button(label="Test")
        latency_button.connect("clicked", self._on_test_latency)
        latency_row.add_suffix(latency_button)
        diagnostics_group.add(latency_row)

        dns_leak_row = Adw.ActionRow(
            title="DNS leak test", subtitle="Compares system resolvers to VPN-provided DNS"
        )
        self._dns_leak_result = Gtk.Label(label="—")
        dns_leak_row.add_suffix(self._dns_leak_result)
        dns_leak_button = Gtk.Button(label="Test")
        dns_leak_button.connect("clicked", self._on_test_dns_leak)
        dns_leak_row.add_suffix(dns_leak_button)
        diagnostics_group.add(dns_leak_row)

        content.append(diagnostics_group)

        traffic_group = Adw.PreferencesGroup(title="Traffic statistics")
        self._traffic_in_row = Adw.ActionRow(title="Received")
        self._traffic_out_row = Adw.ActionRow(title="Sent")
        traffic_group.add(self._traffic_in_row)
        traffic_group.add(self._traffic_out_row)
        content.append(traffic_group)

        self._active_session: Session | None = None
        self.refresh()

    def refresh(self) -> None:
        run_async(self._load_active_session(), on_done=self._apply_session)

    async def _load_active_session(self) -> Session | None:
        sessions = await self._service.list_sessions()
        active = next((s for s in sessions if s.status == SessionStatus.CONNECTED), None)
        if active:
            active = await self._service.get_session_detail(active)
        return active

    def _apply_session(self, session: Session | None) -> None:
        self._active_session = session
        for child in list(self._routes_list):
            self._routes_list.remove(child)

        if session is None:
            self._interface_row.set_subtitle("Not connected")
            return

        self._interface_row.set_subtitle(session.interface or "—")
        self._mtu_row.set_subtitle(str(session.mtu) if session.mtu else "—")
        self._ipv4_row.set_subtitle(session.vpn_ipv4 or "—")
        self._ipv6_row.set_subtitle(session.vpn_ipv6 or "—")
        self._traffic_in_row.set_subtitle(f"{session.stats.bytes_in:,} bytes")
        self._traffic_out_row.set_subtitle(f"{session.stats.bytes_out:,} bytes")

        for route in session.routes:
            row = Adw.ActionRow(title=route.destination, subtitle=f"via {route.gateway or '?'}")
            self._routes_list.append(row)
        if not session.routes:
            placeholder = Adw.ActionRow(title="No routes reported")
            placeholder.set_sensitive(False)
            self._routes_list.append(placeholder)

    def _on_check_public_ip(self, _button: Gtk.Button) -> None:
        self._public_ip_result.set_label("Checking…")
        run_async(self._network.public_ip(), on_done=lambda ip: self._public_ip_result.set_label(ip or "Unavailable"))

    def _on_test_latency(self, _button: Gtk.Button) -> None:
        host = (self._active_session.server_host if self._active_session else None) or "1.1.1.1"
        self._latency_result.set_label("Testing…")
        run_async(
            self._network.measure_latency(host),
            on_done=lambda r: self._latency_result.set_label(
                f"{r.latency_ms:.0f} ms" if r.success else f"Failed: {r.error}"
            ),
        )

    def _on_test_dns_leak(self, _button: Gtk.Button) -> None:
        expected = self._active_session.dns_servers if self._active_session else []
        self._dns_leak_result.set_label("Testing…")
        run_async(
            self._network.check_dns_leak(expected),
            on_done=lambda r: self._dns_leak_result.set_label(
                "Possible leak detected" if r.leaking else "No leak detected"
            ),
        )
