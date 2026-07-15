"""Data models representing a live (or historical) OpenVPN 3 session."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta
from enum import StrEnum


class SessionStatus(StrEnum):
    CONNECTING = "connecting"
    WAIT_AUTH = "wait_auth"
    AUTHENTICATING = "authenticating"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    PAUSED = "paused"
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclasses.dataclass
class RouteEntry:
    destination: str
    gateway: str | None = None
    metric: int | None = None
    interface: str | None = None
    ipv6: bool = False


@dataclasses.dataclass
class TrafficStats:
    bytes_in: int = 0
    bytes_out: int = 0
    packets_in: int = 0
    packets_out: int = 0
    sampled_at: datetime = dataclasses.field(default_factory=datetime.now)

    @property
    def total_bytes(self) -> int:
        return self.bytes_in + self.bytes_out


@dataclasses.dataclass
class SessionSample:
    """One point-in-time sample used to draw the live bandwidth graph."""

    timestamp: datetime
    bytes_in_per_sec: float
    bytes_out_per_sec: float


@dataclasses.dataclass
class Session:
    """A single VPN session/tunnel as reported by ``openvpn3 sessions-list``."""

    session_path: str  # D-Bus object path
    config_name: str
    status: SessionStatus = SessionStatus.UNKNOWN
    pid: int | None = None
    interface: str | None = None
    created: datetime | None = None
    connected_since: datetime | None = None
    server_host: str | None = None
    server_port: int | None = None
    protocol: str | None = None
    vpn_ipv4: str | None = None
    vpn_ipv6: str | None = None
    public_ip: str | None = None
    dns_servers: list[str] = dataclasses.field(default_factory=list)
    gateway: str | None = None
    routes: list[RouteEntry] = dataclasses.field(default_factory=list)
    cipher: str | None = None
    compression: str | None = None
    mtu: int | None = None
    latency_ms: float | None = None
    stats: TrafficStats = dataclasses.field(default_factory=TrafficStats)
    history: list[SessionSample] = dataclasses.field(default_factory=list)
    owner: str | None = None
    restart_count: int = 0
    auto_reconnect: bool = True

    @property
    def duration(self) -> timedelta | None:
        if self.connected_since is None:
            return None
        return datetime.now(self.connected_since.tzinfo) - self.connected_since

    @property
    def is_active(self) -> bool:
        return self.status in (
            SessionStatus.CONNECTED,
            SessionStatus.CONNECTING,
            SessionStatus.AUTHENTICATING,
            SessionStatus.RECONNECTING,
        )
