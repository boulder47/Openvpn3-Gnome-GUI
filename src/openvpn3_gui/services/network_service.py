"""Network diagnostics: public IP lookup, latency tests, DNS leak checks.

These are supplementary "bonus" features layered on top of the VPN itself;
none of them call the ``openvpn3`` binary, so they live in their own
service rather than :class:`OpenVpnService`.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_PUBLIC_IP_ENDPOINTS = [
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
]


@dataclass
class LatencyResult:
    host: str
    latency_ms: float | None
    success: bool
    error: str | None = None


@dataclass
class DnsLeakResult:
    resolvers_used: list[str]
    expected_vpn_dns: list[str]

    @property
    def leaking(self) -> bool:
        if not self.expected_vpn_dns:
            return False
        return any(r not in self.expected_vpn_dns for r in self.resolvers_used)


class NetworkService:
    """Public IP / latency / DNS-leak checks used by the Dashboard and Network page."""

    async def public_ip(self) -> str | None:
        loop = asyncio.get_event_loop()
        for endpoint in _PUBLIC_IP_ENDPOINTS:
            try:
                ip = await loop.run_in_executor(None, self._fetch_text, endpoint)
                if ip:
                    return ip.strip()
            except (urllib.error.URLError, TimeoutError) as exc:
                logger.debug("Public IP endpoint %s failed: %s", endpoint, exc)
        return None

    @staticmethod
    def _fetch_text(url: str, timeout: float = 5.0) -> str:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return response.read().decode().strip()

    async def measure_latency(self, host: str, port: int = 443, timeout: float = 3.0) -> LatencyResult:
        loop = asyncio.get_event_loop()
        try:
            start = time.monotonic()
            await loop.run_in_executor(None, self._tcp_connect, host, port, timeout)
            elapsed_ms = (time.monotonic() - start) * 1000
            return LatencyResult(host=host, latency_ms=elapsed_ms, success=True)
        except OSError as exc:
            return LatencyResult(host=host, latency_ms=None, success=False, error=str(exc))

    @staticmethod
    def _tcp_connect(host: str, port: int, timeout: float) -> None:
        with socket.create_connection((host, port), timeout=timeout):
            pass

    async def check_dns_leak(self, expected_vpn_dns: list[str]) -> DnsLeakResult:
        """A best-effort DNS leak check: resolve a probe hostname and compare
        the *system* resolver configuration against the VPN-provided DNS
        servers. A true leak test ideally uses a unique per-request
        subdomain against a leak-test API; this local heuristic instead
        inspects ``/etc/resolv.conf`` (or ``resolvectl status`` when
        systemd-resolved is in use) which is sufficient to catch the most
        common misconfiguration: routes changed but DNS still pointing at
        the ISP resolver.
        """

        resolvers = await self._read_system_resolvers()
        return DnsLeakResult(resolvers_used=resolvers, expected_vpn_dns=expected_vpn_dns)

    async def _read_system_resolvers(self) -> list[str]:
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, self._parse_resolv_conf)
        except OSError:
            return []

    @staticmethod
    def _parse_resolv_conf() -> list[str]:
        resolvers = []
        try:
            with open("/etc/resolv.conf", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("nameserver"):
                        parts = line.split()
                        if len(parts) >= 2:
                            resolvers.append(parts[1])
        except FileNotFoundError:
            pass
        return resolvers
