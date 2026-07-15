#!/usr/bin/env python3
"""A fake ``openvpn3`` binary for integration tests.

Speaks just enough of the real CLI's surface (subcommands + output shapes)
for the wrapper/service integration tests to exercise the full stack
without a real VPN or D-Bus services.
"""

import sys
import time

CONFIGS_OUTPUT = """\
Configuration path                                          Name           Used
--------------------------------------------------------------------------------
/net/openvpn/v3/configuration/test0001                      fake-profile   2026-07-01 09:30:00
"""

SESSIONS_OUTPUT = """\
-----------------------------------------------------------------------------
        Path: /net/openvpn/v3/sessions/test9001
     Created: Tue Jul 15 03:16:20 2026                 PID: 1234
       Owner: tester                               Device: tun0
 Config name: fake-profile  (Config not available)
Session name: vpn.example.com
      Status: Connection, Client connected
-----------------------------------------------------------------------------
"""

SESSIONS_VERBOSE_OUTPUT = """\
-----------------------------------------------------------------------------
        Path: /net/openvpn/v3/sessions/test9001
     Created: Tue Jul 15 03:16:20 2026                 PID: 1234
       Owner: tester                               Device: tun0
 Config name: fake-profile  (Config not available)
Session name: vpn.example.com
      Status: Connection, Client connected
IPv4 address: 10.8.0.2
     Gateway: 10.8.0.1
    Protocol: udp
         MTU: 1500
DNS servers: 10.8.0.1, 1.1.1.1
-----------------------------------------------------------------------------
"""

STATS_OUTPUT = """\
Connection statistics:
     BYTES_IN...................4096
     BYTES_OUT..................1024
"""


def main() -> int:
    args = sys.argv[1:]
    if not args:
        return 1
    cmd = args[0]

    if cmd == "version":
        print("openvpn3 (fake) 99.0")
        return 0
    if cmd == "help":
        print("Available commands:")
        print("  version        show version")
        print("  configs-list   list configurations")
        print("  sessions-list  list sessions")
        print("  session-start  start a session")
        return 0
    if cmd == "configs-list":
        print(CONFIGS_OUTPUT, end="")
        return 0
    if cmd == "config-import":
        print(
            "Configuration imported. Configuration path: "
            "/net/openvpn/v3/configuration/test0002-imported"
        )
        return 0
    if cmd == "config-import-noname":
        # Simulates an openvpn3 build whose import confirmation doesn't
        # include the configuration path, to exercise the fallback path.
        print("Configuration imported.")
        return 0
    if cmd == "config-show":
        print("client\nremote fake.example.com 1194\nproto udp\nauth-user-pass")
        return 0
    if cmd == "config-remove":
        print("Configuration removed.")
        return 0
    if cmd == "sessions-list":
        if "--verbose" in args:
            print(SESSIONS_VERBOSE_OUTPUT, end="")
        else:
            print(SESSIONS_OUTPUT, end="")
        return 0
    if cmd == "session-stats":
        print(STATS_OUTPUT, end="")
        return 0
    if cmd == "session-manage":
        if "--query" in args:
            # Mirrors the real CLI: exit 8, unrecognized option.
            print("openvpn3/session-manage: unrecognized option '--query'", file=sys.stderr)
            return 8
        print("OK")
        return 0
    if cmd == "session-start":
        print("Session path: /net/openvpn/v3/sessions/test9002")
        sys.stdout.flush()
        time.sleep(0.05)
        print("Connected")
        return 0
    if cmd == "log":
        if "--log-level" in args:
            print("Log line 1: session established")
            print("Log line 2: tunnel up")
            return 0
        if "--level" in args:
            print("unrecognized option '--level'", file=sys.stderr)
            return 2
        print("Log line 1: session established")
        return 0
    if cmd == "fail":
        print("boom", file=sys.stderr)
        return 3
    if cmd == "hang":
        time.sleep(60)
        return 0
    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
