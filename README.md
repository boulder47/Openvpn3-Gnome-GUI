I wrote this for myself because I was tired of using the terminal for VPN start and stop.

# OpenVPN3 GUI

A native GNOME (GTK4 + Libadwaita) graphical frontend for
[openvpn3-linux](https://github.com/OpenVPN/openvpn3-linux). It wraps the
`openvpn3` command-line tool behind a typed, testable service layer and
exposes profile management, connections, live sessions, logs, and network
diagnostics through a polished, HIG-compliant desktop application — no
terminal required for day-to-day use.

![Ubuntu 24.04+](https://img.shields.io/badge/Ubuntu-24.04%2B-orange)
![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue)
![GTK4 + Libadwaita](https://img.shields.io/badge/GTK-4%20%2B%20Libadwaita-green)
![License GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-lightgrey)

---

## Table of contents

- [Features](#features)
- [UI tour](#ui-tour)
- [Installation](#installation)
  - [Debian package (recommended)](#1-debian-package-recommended)
  - [Flatpak](#2-flatpak)
  - [AppImage](#3-appimage)
  - [From source](#4-from-source-development)
- [Building](#building)
- [Running](#running)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Security model](#security-model)
- [Architecture](#architecture)
- [Testing](#testing)
- [Known limitations](#known-limitations)
- [License](#license)

---

## Features

### Dashboard
Live connection status, connected profile and server, public IP, VPN
tunnel IP, session duration, upload/download totals with a real-time
bandwidth graph, DNS servers, gateway, protocol, measured latency, and
tunnel interface — plus a continuously updated system-health panel
(openvpn3 service reachability, D-Bus, internet connectivity, tunnel
health).

### Profile Manager
- Import `.ovpn`/`.conf` files from disk or a URL
- Export, rename, duplicate, and remove profiles (with confirmation)
- Live search across name/host/tags/notes, four sort modes
  (name A–Z/Z–A, last used, favorites first)
- Favorites (starred), free-form tags, and notes — stored locally
  alongside the profiles openvpn3-linux itself manages
- Full ACL management: public access toggle, per-user grant/revoke,
  lock-down (`config-acl`)
- Certificate inspection with expiry warnings (via `cryptography`)

### Connection Manager
Connect / disconnect / reconnect, an auto-reconnect toggle per session,
a live connection transcript showing the raw CLI exchange, and an
in-app connection history.

### Authentication
Username/password, certificate, PKCS#11 PIN, and OTP/MFA challenges are
detected on the `session-start` stream and answered through native
dialogs. Credentials can optionally be saved to the **GNOME Keyring**
(Secret Service) — never written to disk in plaintext.

### Live Logs
Real-time tail of both the openvpn3 log stream and the app's own
structured logs in one view, with plain-text or regex filtering,
severity coloring, a debug-verbosity toggle, copy-to-clipboard, and
export to file.

### Sessions
Every active session with PID, interface, owner, status, and restart
count, expandable to show DNS servers and pushed routes, with per-session
disconnect/restart controls. Auto-refreshes every 5 seconds.

### Network
Tunnel interface, MTU, IPv4/IPv6 addresses, pushed routes, and traffic
counters for the active session, plus three built-in diagnostics: a
public-IP checker, a latency test (TCP connect time to the VPN gateway),
and a DNS-leak test (compares system resolvers against VPN-provided DNS).

### Notifications & tray
Native GNOME notifications for connect, disconnect, errors,
authentication requests, reconnects, and certificate expiry — each
individually toggleable in Settings. An AppIndicator/StatusNotifierItem
tray icon (when the GNOME Shell AppIndicator extension is installed)
shows live status, offers quick-connect for favorite profiles, and
hide-to-tray on window close.

### Automation
- Connect on login (XDG autostart entry)
- Connect on boot (generated `systemd --user` unit)
- Reconnect when the network becomes available (NetworkManager D-Bus
  signal) or on resume from suspend (logind D-Bus signal)
- Cron-style scheduled reconnects
- Pre/post connect/disconnect hook scripts with custom environment
  variables and a persisted execution log

### Settings
Theme (system/light/dark), language, per-event notification toggles,
debug logging, custom `openvpn3` CLI path, developer mode (enables the
Developer Console and the plugin loader), and full settings
import/export.

### Developer Console
Every command the app has executed against `openvpn3` — full argument
vector, exit code, duration, stdout, and stderr — plus a box to run any
subcommand manually. Manual commands are tokenized and executed directly
(`exec`, never a shell), so the same subprocess-safety guarantees apply
here as everywhere else in the app.

### Also included
Global search across profiles, sessions, settings, and commands
(`Ctrl+F`); keyboard shortcuts for the main pages; a small plugin system
(`services/plugin_service.py`) for user-supplied Python extensions; full
backup/restore archives (settings, tags/favorites/notes, exported
profiles — credentials are deliberately excluded); and per-profile
traffic history.

### Under the hood
- **One wrapper, one gate.** Every `openvpn3` invocation goes through
  `openvpn/cli_wrapper.py` — argument vectors via
  `asyncio.create_subprocess_exec`, never a shell. No other module spawns
  the CLI directly.
- **Never runs as root.** Privileged tunnel operations are performed by
  the openvpn3-linux D-Bus system services, which enforce their own
  PolicyKit actions. The app itself never calls `sudo`/`pkexec`.
- **Defensive parsing.** openvpn3-linux's text output has changed shape
  across releases (and even across installs of the *same* release — see
  [Known limitations](#known-limitations)); the parsers degrade to
  partial data and log a warning rather than raising, and every observed
  real-world format is pinned with a regression test.

---

## UI tour

Sidebar navigation: **Dashboard · Profiles · Connections · Sessions ·
Live Logs · Network · Settings · Developer Console.** Adaptive
Libadwaita layout, dark/light/system theming, toasts for background
errors, and GNOME HIG-compliant widgets throughout.

---

## Installation

### 0. Prerequisite: openvpn3-linux

The GUI is a frontend; tunnels are created by openvpn3-linux's own D-Bus
system services.

```bash
sudo apt update
sudo apt install openvpn3
openvpn3 version   # sanity check
```

If your distribution doesn't package it, see
<https://openvpn.net/openvpn3-linux/> — OpenVPN's own apt repository
covers current Ubuntu LTS releases.

### 1. Debian package (recommended)

```bash
sudo apt install devscripts debhelper dh-python pybuild-plugin-pyproject \
                  python3-all python3-pytest python3-pytest-asyncio
git clone https://github.com/example/openvpn3-gui && cd openvpn3-gui
cp -r packaging/debian debian
dpkg-buildpackage -us -uc -b
sudo apt install ../openvpn3-gui_0.1.0-1_all.deb
```

Runtime dependencies are declared in the package and installed
automatically: `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`,
`gir1.2-secret-1`, `python3-cryptography`, `openvpn3`. For the tray icon,
also install `gir1.2-ayatanaappindicator3-0.1` and
`gnome-shell-extension-appindicator` (the latter usually ships with
Ubuntu already).

> **If `dpkg-checkbuilddeps` fails on `python3-all`:** either the package
> isn't installed (`sudo apt install python3-all`), or your system's
> default `python3` is older than 3.12 (check with `python3 --version`).
> `debian/control` declares the real minimum via `X-Python3-Version: >=
> 3.12`, read by `dh_python3` — there's no packaging-level workaround for
> a genuinely older interpreter; you'll need to build on Ubuntu 24.04+ or
> another distribution shipping Python 3.12+.

### 2. Flatpak

```bash
flatpak install org.gnome.Platform//46 org.gnome.Sdk//46
cd packaging/flatpak
flatpak-builder --user --install --force-clean build-dir org.openvpn3.Gui.json
```

Because `openvpn3` must run on the **host** (it talks to system D-Bus
services managing kernel tunnels), grant the sandbox host-spawn access:

```bash
flatpak override --user --talk-name=org.freedesktop.Flatpak org.openvpn3.Gui
```

Then in **Settings → Advanced → CLI path**, enter:

```
flatpak-spawn --host openvpn3
```

### 3. AppImage

```bash
./packaging/appimage/build-appimage.sh
./build/appimage/openvpn3-gui-0.1.0-x86_64.AppImage
```

Bundles the Python layer only; relies on the host's GTK4/Libadwaita
stack (present on any Ubuntu 24.04+/GNOME 46+ system) and a host
`openvpn3`.

### 4. From source (development)

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-secret-1 \
                  python3-cryptography openvpn3
git clone https://github.com/example/openvpn3-gui && cd openvpn3-gui
python3 -m venv --system-site-packages .venv && source .venv/bin/activate
pip install -e ".[dev]"
openvpn3-gui --debug
```

`--system-site-packages` is required so the venv can see the distro's
PyGObject/GTK bindings (they aren't meaningfully pip-installable without
compiling against system GTK).

---

## Building

```bash
# Lint
ruff check src

# Full test suite (headless, no display/D-Bus required)
PYTHONPATH=src python -m pytest src/openvpn3_gui/tests -v

# Debian package
cp -r packaging/debian debian && dpkg-buildpackage -us -uc -b

# Flatpak
flatpak-builder --user --install --force-clean build-dir packaging/flatpak/org.openvpn3.Gui.json

# AppImage
./packaging/appimage/build-appimage.sh
```

Bump `__version__` in `src/openvpn3_gui/__init__.py`,
`pyproject.toml`, `packaging/debian/changelog`, and
`data/org.openvpn3.Gui.metainfo.xml` together when cutting a release.

---

## Running

```bash
openvpn3-gui                 # normal launch
openvpn3-gui --debug         # verbose logging (app + more detail on CLI calls)
openvpn3-gui --no-log-file   # don't write to ~/.local/state/openvpn3-gui/
openvpn3-gui --minimized     # start hidden in the tray
```

Keyboard shortcuts once running:

| Shortcut | Action |
|---|---|
| `Ctrl+F` | Global search |
| `Ctrl+1…5` | Dashboard / Profiles / Connections / Sessions / Logs |
| `Ctrl+,` | Settings |
| `Ctrl+Shift+D` | Developer Console |
| `Ctrl+Q` | Quit |

---

## Configuration

| What | Where |
|---|---|
| Settings (theme, notifications, automation, etc.) | `~/.config/openvpn3-gui/settings.json` |
| Profile metadata (tags, favorites, notes, groups) | `~/.local/share/openvpn3-gui/profile_metadata.json` |
| Traffic history | `~/.local/share/openvpn3-gui/traffic_history.json` |
| App log (rotating, NDJSON) | `~/.local/state/openvpn3-gui/openvpn3-gui.log` |
| Hook-script execution logs | `~/.local/state/openvpn3-gui/script-runs/*.jsonl` |
| Plugins | `~/.local/share/openvpn3-gui/plugins/<name>/plugin.py` |
| Credentials | GNOME Keyring only — never on disk |

All paths respect `$XDG_CONFIG_HOME` / `$XDG_DATA_HOME` /
`$XDG_STATE_HOME` if set.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "openvpn3 executable was not found" | Install openvpn3-linux, or set an explicit path in Settings → Advanced → CLI path |
| No tray icon | Install `gir1.2-ayatanaappindicator3-0.1` and enable the AppIndicator GNOME Shell extension |
| "Secret Service is not available" | Ensure `gnome-keyring` is running; credentials just won't be saved between sessions otherwise |
| Dashboard health panel shows services Unavailable | `systemctl status openvpn3-session@*.service`; reinstall openvpn3-linux |
| A field on Sessions/Network/Dashboard stays "—" | That field isn't printed by your installed openvpn3 version's CLI output, or requires a live tun interface the app couldn't read — see [Known limitations](#known-limitations) |
| Something looks wrong in a specific page | Open the **Developer Console** (`Ctrl+Shift+D`) — it shows the exact command, exit code, and raw stdout/stderr for everything the app has run, which is the fastest way to diagnose a CLI-output mismatch |

If you hit something the Developer Console doesn't explain, run from a
terminal with `openvpn3-gui --debug 2>&1 | tee ~/ovpn-debug.log` and
open an issue with the log attached.

---

## Security model

- Never runs as root; never calls `sudo`/`pkexec`. All privileged
  operations go through openvpn3-linux's own D-Bus services and their
  PolicyKit policy.
- Credentials live exclusively in the GNOME Keyring via the Secret
  Service API — never written to disk. Backup archives deliberately
  exclude them.
- All subprocess calls use argument vectors (`exec`), not a shell —
  there is no shell-injection surface, including in the Developer
  Console's manual-command box.
- Destructive UI actions (remove profile, disconnect, revoke ACL access)
  always require explicit confirmation.

---

## Architecture

```
ui/           GTK4/Libadwaita pages, widgets, dialogs — talks only to services/
tray/         AppIndicator/SNI quick-menu facade
services/     UI-agnostic domain logic (one class per concern)
openvpn/      THE ONLY place that spawns the openvpn3 process, plus output parsers
dbus/         Read-only D-Bus watchers (openvpn3 service presence, NetworkManager, logind)
storage/      GNOME Keyring credentials, JSON-backed settings/metadata stores
settings/     Observable settings controller
models/       Typed dataclasses shared across every layer
utils/        Logging, error types, asyncio↔GLib bridge, i18n
tests/        pytest suite + a fake openvpn3 binary for integration tests
```

See `docs/ARCHITECTURE.md` for the full design rationale (async model,
dependency injection, parsing strategy) and `docs/DEVELOPER.md` for a
contributor's guide.

---

## Testing

```bash
PYTHONPATH=src python -m pytest src/openvpn3_gui/tests -v
```

Runs headlessly — no display or D-Bus needed. Covers CLI-output parsing
(including several real-world `configs-list`/`sessions-list` formats
captured from live systems), the async subprocess wrapper (success,
failure, timeout, streaming, history) against a fake `openvpn3` binary,
the full service layer with an in-memory keyring, settings/metadata
persistence, and the automation cron matcher.

---

## Known limitations

- **openvpn3-linux's CLI output format is not standardized** across
  versions, and has been observed to differ even between installs of
  ostensibly similar versions (e.g. `configs-list` sometimes prints a
  D-Bus configuration path column, sometimes doesn't). The parsers are
  written defensively and degrade to partial data rather than crashing,
  but a field genuinely unsupported by your installed CLI will show as
  "—" rather than being invented.
- **Some session details (tunnel IPv4/IPv6, MTU, DNS) aren't printed by
  any confirmed openvpn3 subcommand** and are instead read from the
  local system for the session's `tun` interface
  (`/sys/class/net/<if>/mtu`, `ip -j addr`, `/etc/resolv.conf`). This
  requires the interface name to be known first (from `sessions-list`)
  and the local tools to be present; it degrades to "—" otherwise.
- **Gateway and protocol** are not currently populated on the
  Dashboard/Network pages — no confirmed CLI source for them has been
  found yet.
- The AppIndicator-based tray icon requires the GNOME Shell AppIndicator
  extension; without it, the app still runs fine, just without a tray
  icon (hide-to-tray silently has no visible effect if the tray isn't
  available).

If your openvpn3 CLI exposes any of the above through a flag not yet
wired up, the Developer Console will show you the exact command and
output — that's the fastest path to getting it added.

---

## License

GPL-3.0-or-later.
