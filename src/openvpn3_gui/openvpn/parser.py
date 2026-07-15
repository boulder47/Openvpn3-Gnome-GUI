"""Parsers that turn ``openvpn3`` CLI text output into typed dataclasses.

The openvpn3-linux CLI is a human-oriented text tool (not JSON), and its
exact formatting has changed across releases. These parsers are written
defensively: they use tolerant regexes/heuristics, log a warning and return
partial data (rather than raising) whenever a field cannot be located, and
are covered by unit tests using captured sample output
(see ``tests/test_parser.py``) so they can be extended as new CLI versions
are encountered.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from openvpn3_gui.models.profile import AuthMethod, Profile, ProfileACL
from openvpn3_gui.models.session import RouteEntry, Session, SessionStatus, TrafficStats

logger = logging.getLogger(__name__)

_KV_KEY_RE = re.compile(r"(?:^\s*|\s{2,})([A-Za-z][A-Za-z0-9 _/-]*?):(?=\s|$)")


def _parse_kv_block(text: str) -> dict[str, str]:
    """Parse ``Key: Value`` blocks used by most openvpn3 subcommands.

    Real ``sessions-list`` output places TWO pairs on one line, aligned in
    columns, e.g.::

            Created: Tue Jul 15 03:16:20 2026            PID: 12345
              Owner: ubuntu                           Device: tun0

    A one-pair-per-line parser swallows ``PID: 12345`` into the *value* of
    ``created`` (which is exactly why Sessions showed no PID/interface).
    Keys are recognised only at line start or after a run of 2+ spaces, so
    colons inside values (timestamps like ``03:16:20``, ``host:port``
    session names) are not mistaken for new keys.
    """

    result: dict[str, str] = {}
    for line in text.splitlines():
        matches = list(_KV_KEY_RE.finditer(line))
        for index, match in enumerate(matches):
            key = match.group(1).strip().lower().replace(" ", "_")
            value_start = match.end()
            value_end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
            result[key] = line[value_start:value_end].strip()
    return result


def _parse_timestamp(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%a %b %d %H:%M:%S %Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    logger.debug("Could not parse timestamp: %r", value)
    return None


_CONFIG_PATH_RE = re.compile(r"(/net/openvpn/v3/configuration/\S+)")
_DATE_HINT_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_NO_TIMESTAMP_PLACEHOLDERS = {"-", "\u2014", "n/a", "none", ""}


def parse_configs_list(text: str) -> list[Profile]:
    """Parse ``openvpn3 configs-list`` output into :class:`Profile` objects.

    openvpn3-linux builds differ on whether ``configs-list`` even prints
    the D-Bus configuration path: some show a
    ``Configuration path / Name / Used`` table, others (observed in the
    wild) show only ``Configuration Name / Last used`` with no path column
    at all. Since no app code actually needs the D-Bus path (every CLI
    call addresses a profile by ``--config <name>``), we first try the
    path-anchored parse and, if it finds nothing, fall back to a
    name-only table parse that synthesizes a local identifier.
    """

    profiles = _parse_with_paths(text)
    if profiles:
        return profiles
    return _parse_name_only(text)


def _parse_with_paths(text: str) -> list[Profile]:
    """Handles CLI output that includes the ``/net/openvpn/v3/configuration/<id>`` path."""

    profiles: list[Profile] = []
    for line in text.splitlines():
        match = _CONFIG_PATH_RE.search(line)
        if not match:
            continue
        config_path = match.group(1)
        remainder = line[match.end() :].strip()
        columns = [c for c in re.split(r"\s{2,}", remainder) if c] if remainder else []

        name = columns[0] if columns else config_path.rsplit("/", 1)[-1]
        last_used = None
        for col in columns[1:]:
            if _DATE_HINT_RE.search(col):
                last_used = _parse_timestamp(col)
                if last_used:
                    break

        profiles.append(Profile(config_path=config_path, name=name, last_used=last_used))
    return profiles


def _parse_name_only(text: str) -> list[Profile]:
    """Handles the path-less ``Configuration Name / Last used`` table format.

    There is no stable object-path identifier available in this format,
    so ``config_path`` is synthesized as ``name:<profile name>`` — safe
    because nothing in the app passes ``config_path`` to the CLI; every
    command addresses profiles via ``--config <name>``.
    """

    profiles: list[Profile] = []
    header_consumed = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or set(stripped) <= {"-"}:
            continue
        if not header_consumed and re.search(r"\bname\b", stripped, re.IGNORECASE):
            header_consumed = True
            continue
        columns = [c for c in re.split(r"\s{2,}", stripped) if c]
        if not columns:
            continue
        name = columns[0]
        last_used = None
        if len(columns) > 1 and columns[1].strip().lower() not in _NO_TIMESTAMP_PLACEHOLDERS:
            last_used = _parse_timestamp(columns[1])
        profiles.append(Profile(config_path=f"name:{name}", name=name, last_used=last_used))
    return profiles


def parse_config_show(text: str, config_path: str, name: str) -> Profile:
    """Parse ``openvpn3 config-show``/``config-dump`` output into a full :class:`Profile`."""

    kv = _parse_kv_block(text)
    remote_match = re.search(r"^remote\s+([^\s]+)\s+(\d+)?", text, re.MULTILINE)
    proto_match = re.search(r"^proto\s+(\S+)", text, re.MULTILINE)
    cipher_match = re.search(r"^(?:cipher|data-ciphers)\s+(\S+)", text, re.MULTILINE)
    comp_match = re.search(r"^comp-lzo\s+(\S+)?|^compress\s+(\S+)?", text, re.MULTILINE)

    auth_method = AuthMethod.UNKNOWN
    if "auth-user-pass" in text:
        auth_method = AuthMethod.USERNAME_PASSWORD
    if "pkcs11-providers" in text or "pkcs11-id" in text:
        auth_method = AuthMethod.PKCS11
    elif "<cert>" in text or "cert " in text:
        auth_method = AuthMethod.CERTIFICATE

    return Profile(
        config_path=config_path,
        name=name,
        remote_host=remote_match.group(1) if remote_match else None,
        remote_port=int(remote_match.group(2))
        if remote_match and remote_match.group(2)
        else None,
        protocol=proto_match.group(1) if proto_match else None,
        cipher=cipher_match.group(1) if cipher_match else None,
        compression=(comp_match.group(1) or comp_match.group(2)) if comp_match else None,
        auth_method=auth_method,
        persistent=kv.get("persistent", "true").lower() != "false",
        raw_config_text=text,
    )


def parse_config_acl(text: str) -> ProfileACL:
    kv = _parse_kv_block(text)
    granted = []
    grant_match = re.search(r"granted access:\s*(.*)", text, re.IGNORECASE)
    if grant_match:
        granted = [u.strip() for u in grant_match.group(1).split(",") if u.strip()]
    return ProfileACL(
        owner=kv.get("owner"),
        public=kv.get("public_access", "false").lower() == "true",
        granted_users=granted,
        locked_down=kv.get("locked_down", "false").lower() == "true",
        sealed=kv.get("sealed", "false").lower() == "true",
    )


_SESSION_STATUS_MAP = {
    "connecting": SessionStatus.CONNECTING,
    "wait for credentials": SessionStatus.WAIT_AUTH,
    "authentication required": SessionStatus.WAIT_AUTH,
    "authenticating": SessionStatus.AUTHENTICATING,
    "connected": SessionStatus.CONNECTED,
    "reconnecting": SessionStatus.RECONNECTING,
    "paused": SessionStatus.PAUSED,
    "disconnecting": SessionStatus.DISCONNECTING,
    "disconnected": SessionStatus.DISCONNECTED,
}


def _map_status(text: str) -> SessionStatus:
    text_low = text.lower()
    for key, status in _SESSION_STATUS_MAP.items():
        if key in text_low:
            return status
    if "error" in text_low or "fail" in text_low:
        return SessionStatus.ERROR
    return SessionStatus.UNKNOWN


def parse_sessions_list(text: str) -> list[Session]:
    """Parse ``openvpn3 sessions-list`` output into :class:`Session` objects.

    Real output separates sessions with dashed rule lines rather than blank
    lines, and packs two key/value pairs per line::

        -----------------------------------------------------------
                Path: /net/openvpn/v3/sessions/abcd...
             Created: Tue Jul 15 03:16:20 2026         PID: 12345
               Owner: ubuntu                        Device: tun0
         Config name: cor1  (Config not available)
        Session name: vpn.example.com
              Status: Connection, Client connected
        -----------------------------------------------------------
    """

    sessions: list[Session] = []
    blocks = re.split(r"\n\s*\n|^\s*-{5,}\s*$", text.strip(), flags=re.MULTILINE)
    for block in blocks:
        if "path:" not in block.lower():
            continue
        path_match = re.search(r"Path:\s*(\S+)", block)
        if not path_match:
            continue

        # Real output packs two key/value pairs onto one line
        # ("Created: ... PID: 12345", "Owner: ubuntu    Device: tun0"),
        # so a line-based KV parser mangles them — every field is instead
        # extracted with its own anchored regex.
        def _field(pattern: str, _block: str = block) -> str | None:
            match = re.search(pattern, _block)
            return match.group(1).strip() if match else None

        config_name = _field(r"Config name:\s*(.+?)(?:\s{2,}|\(|\n|$)") or "unknown"
        config_name = re.sub(r"\s*\(.*?\)\s*$", "", config_name).strip() or "unknown"

        pid_text = _field(r"PID:\s*(\d+)")
        created_text = _field(r"Created:\s*(.+?)(?:\s{2,}PID:|\n|\s*$)") or ""
        status_text = _field(r"Status:\s*(.+?)(?:\n|$)") or ""

        session = Session(
            session_path=path_match.group(1),
            config_name=config_name,
            status=_map_status(status_text) if status_text else SessionStatus.UNKNOWN,
            pid=int(pid_text) if pid_text else None,
            interface=_field(r"Device:\s*(\S+)") or _field(r"Interface:\s*(\S+)"),
            created=_parse_timestamp(created_text),
            owner=_field(r"Owner:\s*(\S+)"),
            server_host=_field(r"Session name:\s*(\S+)"),
        )
        # sessions-list has no separate "connected since" field; the session
        # creation time is the best available anchor for the duration shown
        # on the Dashboard.
        if session.status == SessionStatus.CONNECTED and session.created is not None:
            session.connected_since = session.created
        sessions.append(session)
    return sessions


_STATS_LINE_RE = re.compile(r"^\s*([A-Z_]+)[.\s:]+(\d+)\s*$", re.MULTILINE)


def parse_session_stats(text: str) -> TrafficStats:
    """Parse ``openvpn3 session-stats`` output.

    The CLI pads counter names with dots (``BYTES_IN..........10240``), so
    the generic ``Key: Value`` parser doesn't apply; both formats are
    accepted here.
    """

    kv = {m.group(1).lower(): m.group(2) for m in _STATS_LINE_RE.finditer(text)}
    kv.update({k: v for k, v in _parse_kv_block(text).items() if v.strip().isdigit()})

    def _num(*keys: str) -> int:
        for k in keys:
            if k in kv:
                digits = re.sub(r"[^\d]", "", kv[k])
                if digits:
                    return int(digits)
        return 0

    return TrafficStats(
        bytes_in=_num("bytes_in", "bytes_received"),
        bytes_out=_num("bytes_out", "bytes_sent"),
        packets_in=_num("packets_in", "tun_packets_in"),
        packets_out=_num("packets_out", "tun_packets_out"),
    )


def parse_session_detail(text: str, session: Session) -> Session:
    """Enrich a :class:`Session` from ``openvpn3 sessions-list [--verbose]`` output.

    Field names observed across openvpn3-linux releases (from live systems
    and upstream source): ``Device:`` is the tun interface (some releases
    say ``Interface:``), ``PID:`` or ``Client PID:`` for the backend
    process, ``Session name:`` for the server-assigned name, ``Status:``
    for the state text, plus tun ``IPv4/IPv6 address`` lines in verbose
    mode. All lookups are optional — anything absent keeps its prior value.
    """

    kv = _parse_kv_block(text)

    # Interface: 'Device' on current releases, 'Interface' on some others.
    session.interface = kv.get("device", kv.get("interface", session.interface))

    # PID: 'PID' or 'Client PID' depending on release.
    for pid_key in ("pid", "client_pid"):
        if kv.get(pid_key, "").strip().isdigit():
            session.pid = int(kv[pid_key])
            break

    session.owner = kv.get("owner", session.owner)
    session.vpn_ipv4 = kv.get("ipv4_address", kv.get("tun_ipv4", session.vpn_ipv4))
    session.vpn_ipv6 = kv.get("ipv6_address", kv.get("tun_ipv6", session.vpn_ipv6))
    session.gateway = kv.get("gateway", session.gateway)
    session.protocol = kv.get("protocol", session.protocol)
    session.cipher = kv.get("cipher", session.cipher)
    session.mtu = int(kv["mtu"]) if kv.get("mtu", "").isdigit() else session.mtu

    # 'Session name' is typically 'server:port' — use it for server info
    # when nothing better is known.
    session_name = kv.get("session_name", "")
    if session_name and session.server_host is None:
        host, _sep, port = session_name.rpartition(":")
        if host and port.isdigit():
            session.server_host = host
            session.server_port = int(port)
        else:
            session.server_host = session_name

    status_text = kv.get("status", "")
    if status_text:
        session.status = _map_status(status_text)

    dns_match = re.search(r"DNS servers?:\s*(.+)", text, re.IGNORECASE)
    if dns_match:
        session.dns_servers = [d.strip() for d in dns_match.group(1).split(",") if d.strip()]

    routes: list[RouteEntry] = []
    for line in text.splitlines():
        route_match = re.match(
            r"\s*(\d+\.\d+\.\d+\.\d+(?:/\d+)?)\s+via\s+(\S+)", line
        )
        if route_match:
            routes.append(
                RouteEntry(destination=route_match.group(1), gateway=route_match.group(2))
            )
    if routes:
        session.routes = routes
    return session
