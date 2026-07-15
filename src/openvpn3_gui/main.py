"""Application entry point."""

from __future__ import annotations

import argparse
import sys

from openvpn3_gui.utils.logging_config import configure_logging


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="openvpn3-gui")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--no-log-file", action="store_true", help="Disable writing logs to disk"
    )
    parser.add_argument(
        "--minimized", action="store_true", help="Start hidden in the tray"
    )
    return parser.parse_known_args(argv[1:])[0]


def main() -> int:
    args = parse_args(sys.argv)
    configure_logging(debug=args.debug, log_to_file=not args.no_log_file)

    from openvpn3_gui.application import OpenVpnGuiApplication

    app = OpenVpnGuiApplication()
    # We've already parsed our own flags (--debug, --no-log-file,
    # --minimized) above with argparse. Passing the full argv into
    # Gio.Application.run() makes it try to parse those same flags itself
    # and fail with "Unknown option --debug" since they were never
    # registered as GApplication options — so only the program name is
    # forwarded here.
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
