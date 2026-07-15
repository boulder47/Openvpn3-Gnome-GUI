# Architecture

## Overview

OpenVPN3 GUI follows an **MVVM-flavored layered architecture** with strict
downward-only dependencies:

```
┌──────────────────────────────────────────────────────────────┐
│  ui/  (View)          GTK4/Libadwaita pages, widgets, dialogs │
│  tray/                StatusNotifierItem quick menu           │
├──────────────────────────────────────────────────────────────┤
│  services/ (ViewModel/Domain)                                 │
│    openvpn_service   network_service   notification_service   │
│    monitor_service   automation_service script_runner          │
│    certificate_service backup_service  plugin_service          │
├───────────────┬───────────────┬──────────────┬───────────────┤
│  openvpn/     │  dbus/        │  storage/    │  settings/     │
│  cli_wrapper  │  signal       │  keyring     │  observable     │
│  parser       │  watchers     │  json stores │  controller     │
├───────────────┴───────────────┴──────────────┴───────────────┤
│  models/   typed dataclasses shared by every layer            │
│  utils/    logging, errors, asyncio↔GLib bridge, i18n          │
└──────────────────────────────────────────────────────────────┘
```

**The golden rule:** the UI talks *only* to `services/`. Only
`openvpn/cli_wrapper.py` may spawn the `openvpn3` process (the
`script_runner` spawns *user hook scripts*, a separate concern). This is
enforced by convention and checked in code review; grep for
`create_subprocess` to audit.

## Composition root & dependency injection

`application.py` (`OpenVpnGuiApplication`) is the single composition root.
It constructs every service exactly once and passes them down explicitly
through constructors — no globals, no service locator. Tests construct
services with fakes (`FakeCredentialStore`, the `fake_openvpn3.py` binary)
via the same constructor parameters.

## Async model

GTK4 owns the process's main loop (`GLib.MainLoop`). Instead of running a
competing thread for asyncio, `utils/async_utils.py` drives one shared
asyncio loop *from* GLib via a 15 ms pump (`loop.call_soon(loop.stop);
loop.run_forever()`), keeping everything **single-threaded**:

- Services are plain `async def` and use
  `asyncio.create_subprocess_exec` for the CLI.
- UI signal handlers call `run_async(coro, on_done, on_error)`; callbacks
  are marshalled back with `GLib.idle_add`, so they may safely touch
  widgets.
- The only threads in the app are short-lived executor threads for
  blocking libsecret and socket calls.

## CLI wrapper design

`openvpn/cli_wrapper.py`:

- **No shell, ever** — argv lists via `create_subprocess_exec`.
- Two execution modes: `run()` (bounded, timed, raises typed
  `CliExecutionError`/`CliTimeoutError`) and `run_streaming()` (async
  generator yielding lines; used for `session-start` auth prompts and
  `log` tailing; supports `send_stdin()` for answering prompts).
- **Command history** — every invocation (command, exit code, stdout,
  stderr, duration) enters an observable ring buffer that powers the
  Developer Console.
- **Capability discovery** — `help_text()`/`discover_subcommands()` parse
  the installed CLI's own help output at runtime, so the wrapper adapts to
  the openvpn3 version present rather than hard-coding one release's flags.

## Parsing strategy

openvpn3-linux emits human-oriented text whose exact layout varies between
releases. `openvpn/parser.py` therefore:

- splits tables on runs of ≥2 spaces instead of fixed columns,
- accepts both `Key: Value` and dot-padded `KEY.....value` styles,
- returns partial dataclasses and logs (never raises) when a field is
  missing,
- is pinned by unit tests on captured sample output so regressions against
  new CLI versions are caught by adding one sample.

D-Bus is used *read-only* as a complement (`dbus/`): service presence
checks and `StatusChange` signal subscriptions give real-time updates
without polling; NetworkManager `StateChanged` and logind
`PrepareForSleep` drive the automation features. All mutating operations
still flow through the CLI, which carries openvpn3-linux's own
PolicyKit-enforced authorization.

## State & persistence

| Data | Where | Format |
|---|---|---|
| Settings | `$XDG_CONFIG_HOME/openvpn3-gui/settings.json` | JSON (mirrored GSettings schema shipped) |
| Profile tags/favorites/notes/groups | `$XDG_DATA_HOME/openvpn3-gui/profile_metadata.json` | JSON sidecar keyed by profile name |
| Traffic history | `$XDG_DATA_HOME/openvpn3-gui/traffic_history.json` | Daily per-profile max counters |
| Script execution logs | `$XDG_STATE_HOME/openvpn3-gui/script-runs/*.jsonl` | NDJSON |
| App logs | `$XDG_STATE_HOME/openvpn3-gui/openvpn3-gui.log` | NDJSON, rotating |
| **Credentials** | **GNOME Keyring only** | Secret Service schema `org.openvpn3.Gui.Credential` |
| Imported configs | owned by openvpn3-linux itself | — |

Profiles themselves (the `.ovpn` payloads) are owned by openvpn3-linux's
configuration manager; the GUI never keeps a second copy except in
explicit user-requested exports/backups.

## Error handling

`utils/errors.py` defines a typed hierarchy (`CliNotFoundError`,
`CliExecutionError`, `CliTimeoutError`, `AuthenticationRequired`,
`KeyringUnavailableError`, …). Services translate raw failures into these;
UI pages catch them at the `run_async(on_error=…)` boundary and surface
toasts/dialogs. Background loops (monitor, scheduler, plugins, listeners)
are wrapped so a single failure never kills the loop or the app.

## Extensibility

- **Plugins** (`services/plugin_service.py`): user modules in
  `$XDG_DATA_HOME/openvpn3-gui/plugins/<name>/plugin.py` implementing the
  `PluginBase` protocol, activated with a restricted `PluginContext`.
  Only loaded when Developer mode is enabled.
- **New pages**: subclass `Gtk.Box`, accept services in the constructor,
  register in `window._build_pages()` and `_NAV_ITEMS`.
- **New CLI operations**: add a method to `OpenVpnService` plus a parser +
  parser test; the UI never grows CLI knowledge.

## Testing strategy

- **Unit tests** (gi-free): parsers, models, storage, cron matcher,
  script runner — run headlessly anywhere.
- **Integration tests**: the full
  `OpenVpnService → OpenVpn3Cli → subprocess` stack against
  `tests/fake_openvpn3.py`, a fake binary emitting realistic output,
  including streaming/auth and failure/timeout paths.
- GTK widget code is kept intentionally thin (declarative layout +
  delegation to services) to minimize the untested surface; a GTK-based
  smoke test can be run on a developer machine with
  `python -m openvpn3_gui.main --debug`.
