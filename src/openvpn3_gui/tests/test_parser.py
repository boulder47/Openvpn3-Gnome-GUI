"""Unit tests for openvpn3 CLI output parsers."""

from __future__ import annotations

from openvpn3_gui.models.profile import AuthMethod
from openvpn3_gui.models.session import SessionStatus
from openvpn3_gui.openvpn.parser import (
    parse_config_acl,
    parse_config_show,
    parse_configs_list,
    parse_session_stats,
    parse_sessions_list,
)

CONFIGS_LIST_SAMPLE = """\
Configuration path                                          Name           Used
--------------------------------------------------------------------------------
/net/openvpn/v3/configuration/aaaa1111                      home-office    2026-07-01 09:30:00
/net/openvpn/v3/configuration/bbbb2222                      work-eu        2026-06-12 18:04:11
"""

# A differently-columned real-world variant (extra "Used From"/"Owner"
# columns, different header wording) that a header-driven parser would
# have mis-parsed — this is the regression test for that bug.
CONFIGS_LIST_ALT_SAMPLE = """\
     Configuration path                                      Config name        Used From    Last used                Owner
------------------------------------------------------------------------------------------------------------------------------
     /net/openvpn/v3/configuration/cccc3333                  cor1               N/A          2026-07-14 01:53:00       ubuntu
     /net/openvpn/v3/configuration/dddd4444                  cor2               N/A          N/A                       ubuntu
"""

# Real-world sample: some openvpn3-linux builds print NO D-Bus path column
# at all in `configs-list`, only name + last-used. Captured verbatim from
# a live system.
CONFIGS_LIST_NAME_ONLY_SAMPLE = """\
Configuration Name                                        Last used
------------------------------------------------------------------------------
Abc                                                       -
Cor                                                       -
Sor                                                       -
cor1                                                      -
corner                                                    -
------------------------------------------------------------------------------
"""

CONFIG_SHOW_SAMPLE = """\
client
dev tun
proto udp
remote vpn.example.com 1194
cipher AES-256-GCM
compress lz4
auth-user-pass
<ca>
-----BEGIN CERTIFICATE-----
MIIB...
-----END CERTIFICATE-----
</ca>
"""

SESSIONS_LIST_SAMPLE = """\
Path: /net/openvpn/v3/sessions/cccc3333
Created: 2026-07-13 08:00:00
Owner: alice
PID: 4321
Config name: home-office
Status: Connection, Client connected

Path: /net/openvpn/v3/sessions/dddd4444
Created: 2026-07-13 08:10:00
Owner: alice
PID: 4400
Config name: work-eu
Status: Web authentication required to connect
"""

# Real-world format: dashed separators between sessions, TWO key/value
# pairs per line ('Created: ... PID: ...', 'Owner: ... Device: ...'), and
# a parenthetical annotation after the config name. A one-pair-per-line
# parser swallowed PID into 'created' and Device into 'owner' — the exact
# cause of Sessions showing no PID/interface on a live system.
SESSIONS_LIST_REAL_SAMPLE = """\
-----------------------------------------------------------------------------
        Path: /net/openvpn/v3/sessions/6d95bae8s2651s43absaa0bsbed9913d079c
     Created: Tue Jul 15 03:16:20 2026                 PID: 24310
       Owner: ubuntu                               Device: tun0
 Config name: cor1  (Config not available)
Session name: vpn.example.com
      Status: Connection, Client connected
-----------------------------------------------------------------------------
"""

SESSIONS_VERBOSE_REAL_SAMPLE = """\
-----------------------------------------------------------------------------
        Path: /net/openvpn/v3/sessions/6d95bae8s2651s43absaa0bsbed9913d079c
     Created: Tue Jul 15 03:16:20 2026                 PID: 24310
       Owner: ubuntu                               Device: tun0
 Config name: cor1  (Config not available)
Session name: vpn.example.com
      Status: Connection, Client connected
IPv4 address: 10.8.0.2
     Gateway: 10.8.0.1
    Protocol: udp
         MTU: 1500
DNS servers: 10.8.0.1, 1.1.1.1
-----------------------------------------------------------------------------
"""

SESSION_STATS_SAMPLE = """\
Connection statistics:
     BYTES_IN...................10240
     BYTES_OUT..................2048
     PACKETS_IN.................100
     PACKETS_OUT................50
"""

ACL_SAMPLE = """\
Owner: alice
Public access: false
Locked down: true
Users granted access: bob, carol
"""


class TestParseConfigsList:
    def test_parses_two_profiles(self) -> None:
        profiles = parse_configs_list(CONFIGS_LIST_SAMPLE)
        assert len(profiles) == 2
        assert profiles[0].config_path == "/net/openvpn/v3/configuration/aaaa1111"
        assert profiles[0].name == "home-office"
        assert profiles[0].last_used is not None
        assert profiles[0].last_used.year == 2026

    def test_empty_output(self) -> None:
        assert parse_configs_list("") == []

    def test_ignores_junk_lines(self) -> None:
        text = "some banner\n" + CONFIGS_LIST_SAMPLE
        profiles = parse_configs_list(text)
        assert len(profiles) == 2

    def test_alternate_column_layout_still_parses(self) -> None:
        """Regression test: header-driven parsing previously broke on any
        real-world table whose header wording/column count differed from
        the assumed sample (e.g. extra 'Used From'/'Owner' columns)."""

        profiles = parse_configs_list(CONFIGS_LIST_ALT_SAMPLE)
        assert len(profiles) == 2
        assert profiles[0].config_path == "/net/openvpn/v3/configuration/cccc3333"
        assert profiles[0].name == "cor1"
        assert profiles[0].last_used is not None
        assert profiles[0].last_used.year == 2026
        assert profiles[1].name == "cor2"
        assert profiles[1].last_used is None  # "N/A" never matches the date heuristic

    def test_path_less_format_still_parses(self) -> None:
        """Regression test: this openvpn3-linux build prints only
        'Configuration Name / Last used' with no D-Bus path column at all.
        Captured verbatim from a live system report."""

        profiles = parse_configs_list(CONFIGS_LIST_NAME_ONLY_SAMPLE)
        names = [p.name for p in profiles]
        assert names == ["Abc", "Cor", "Sor", "cor1", "corner"]
        assert all(p.last_used is None for p in profiles)  # all rows show "-"
        assert all(p.config_path for p in profiles)  # synthesized, but never empty
        assert len({p.config_path for p in profiles}) == 5  # all unique


class TestParseConfigShow:
    def test_extracts_remote_and_crypto(self) -> None:
        profile = parse_config_show(CONFIG_SHOW_SAMPLE, "/net/openvpn/v3/configuration/x", "home-office")
        assert profile.remote_host == "vpn.example.com"
        assert profile.remote_port == 1194
        assert profile.protocol == "udp"
        assert profile.cipher == "AES-256-GCM"
        assert profile.compression == "lz4"

    def test_detects_userpass_auth(self) -> None:
        profile = parse_config_show(CONFIG_SHOW_SAMPLE, "/x", "n")
        assert profile.auth_method == AuthMethod.USERNAME_PASSWORD

    def test_detects_pkcs11(self) -> None:
        text = CONFIG_SHOW_SAMPLE.replace("auth-user-pass", "pkcs11-id 'token'")
        profile = parse_config_show(text, "/x", "n")
        assert profile.auth_method == AuthMethod.PKCS11


class TestParseSessionsList:
    def test_parses_sessions(self) -> None:
        sessions = parse_sessions_list(SESSIONS_LIST_SAMPLE)
        assert len(sessions) == 2
        assert sessions[0].session_path == "/net/openvpn/v3/sessions/cccc3333"
        assert sessions[0].pid == 4321
        assert sessions[0].config_name == "home-office"
        assert sessions[0].status == SessionStatus.CONNECTED
        assert sessions[0].owner == "alice"

    def test_empty(self) -> None:
        assert parse_sessions_list("") == []

    def test_real_world_two_pairs_per_line_format(self) -> None:
        """Regression test: PID and Device share lines with Created/Owner in
        real output; the old parser swallowed them into the wrong values."""

        sessions = parse_sessions_list(SESSIONS_LIST_REAL_SAMPLE)
        assert len(sessions) == 1
        s = sessions[0]
        assert s.pid == 24310
        assert s.interface == "tun0"
        assert s.owner == "ubuntu"
        assert s.config_name == "cor1"  # parenthetical stripped
        assert s.status == SessionStatus.CONNECTED
        assert s.created is not None
        assert s.created.year == 2026

    def test_second_session_wait_auth_status(self) -> None:
        sessions = parse_sessions_list(SESSIONS_LIST_SAMPLE)
        assert sessions[1].status == SessionStatus.WAIT_AUTH


class TestParseSessionDetail:
    def test_verbose_block_enriches_session(self) -> None:
        from openvpn3_gui.models.session import Session
        from openvpn3_gui.openvpn.parser import parse_session_detail

        session = Session(
            session_path="/net/openvpn/v3/sessions/6d95bae8s2651s43absaa0bsbed9913d079c",
            config_name="cor1",
        )
        session = parse_session_detail(SESSIONS_VERBOSE_REAL_SAMPLE, session)
        assert session.pid == 24310
        assert session.interface == "tun0"
        assert session.vpn_ipv4 == "10.8.0.2"
        assert session.gateway == "10.8.0.1"
        assert session.protocol == "udp"
        assert session.mtu == 1500
        assert session.dns_servers == ["10.8.0.1", "1.1.1.1"]
        assert session.server_host == "vpn.example.com"
        assert session.status == SessionStatus.CONNECTED


class TestParseSessionStats:
    def test_extracts_byte_counters(self) -> None:
        stats = parse_session_stats(SESSION_STATS_SAMPLE)
        assert stats.bytes_in == 10240
        assert stats.bytes_out == 2048
        assert stats.packets_in == 100
        assert stats.packets_out == 50


class TestParseAcl:
    def test_parses_acl(self) -> None:
        acl = parse_config_acl(ACL_SAMPLE)
        assert acl.owner == "alice"
        assert acl.public is False
        assert acl.locked_down is True
        assert acl.granted_users == ["bob", "carol"]
