# Developer Documentation

## Environment setup

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-secret-1 \
                 python3-cryptography openvpn3
git clone https://github.com/example/openvpn3-gui && cd openvpn3-gui
python3 -m venv --system-site-packages .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Run the app: `openvpn3-gui --debug` (or `python -m openvpn3_gui.main --debug`).
`--no-log-file` disables the on-disk log; `--minimized` starts in the tray.

## Project layout

```
src/openvpn3_gui/
├── application.py        # Adw.Application — composition root (DI)
├── main.py               # argparse + logging bootstrap
├── models/               # dataclasses: Profile, Session, LogEntry, AppSettings
├── openvpn/              # THE ONLY place that spawns `openvpn3`
│   ├── cli_wrapper.py    #   async exec + streaming + history + discovery
│   └── parser.py         #   text → dataclasses
├── services/             # UI-agnostic domain logic (one class per concern)
├── dbus/                 # read-only bus watchers (openvpn3, NM, logind)
├── storage/              # keyring (Secret Service), JSON stores
├── settings/             # observable SettingsController
├── ui/
│   ├── window.py         # NavigationSplitView shell + shortcuts
│   ├── pages/            # one module per sidebar page
│   ├── widgets/          # BandwidthGraph, StatusBadge, ProfileRow
│   └── dialogs/          # auth, import, ACL, metadata, confirm, search
├── tray/                 # AppIndicator/SNI facade (optional at runtime)
├── utils/                # logging, errors, asyncio↔GLib bridge, i18n
└── tests/                # pytest suite + fake_openvpn3.py
```

## Coding standards

- **Python 3.12+, PEP 8**, enforced by `ruff` (`ruff check src`).
- **Type hints everywhere**; `mypy src` should stay clean.
- **Dataclasses** for all data crossing layer boundaries.
- **Structured logging**: `logger = logging.getLogger(__name__)` at module
  top; never `print`. App logs are NDJSON on disk and feed the Live Logs
  page automatically.
- **Dependency injection**: services receive collaborators via
  constructors. Never import `application.py` from a service.
- **Async**: services are `async def`; UI calls them with
  `run_async(coro, on_done=…, on_error=…)`. Never block the main loop;
  wrap unavoidable blocking calls in `run_in_executor`.
- **No subprocess outside `openvpn/cli_wrapper.py`** (hook scripts in
  `script_runner.py` are the sole, documented exception).
- **Every destructive UI action** goes through
  `ui/dialogs/confirm_dialog.confirm()`.

## Running tests

```bash
PYTHONPATH=src python -m pytest src/openvpn3_gui/tests -v
```

The suite runs headlessly (no GTK/display/D-Bus needed):

- `test_parser.py` — CLI-output parsers against captured samples.
- `test_cli_wrapper.py` — wrapper vs. `fake_openvpn3.py`: success, failure,
  timeout, streaming, history, discovery.
- `test_openvpn_service.py` — full service stack with an in-memory keyring.
- `test_storage.py` — settings/metadata/traffic persistence and corruption
  fallback.
- `test_models_and_automation.py` — model logic, cron matcher, script
  runner (env injection + execution logs).

### Adding CLI-version coverage

Found an openvpn3 release whose output the parser mishandles? Capture the
real output, add it as a sample constant in `test_parser.py`, write the
failing assertion, then loosen the regex in `openvpn/parser.py`. Parsers
must degrade to partial data, never raise.

## Adding a feature (checklist)

1. Model change? Extend the dataclass in `models/`.
2. New CLI interaction? Add a method to `OpenVpnService` (+ parser +
   parser test). The UI must not learn CLI flags.
3. UI: new page in `ui/pages/` registered in `window.py`, or extend an
   existing page. Use Adw widgets (`PreferencesGroup`, `ActionRow`,
   `SwitchRow`, toasts) — follow the GNOME HIG.
4. Persisted state? Add to the relevant `storage/` store with a
   round-trip test.
5. Update `docs/USER_GUIDE.md`.

## Writing a plugin

`~/.local/share/openvpn3-gui/plugins/hello/plugin.py`:

```python
class Plugin:
    name = "hello"
    version = "1.0"

    def activate(self, context):
        self.ctx = context
        context.show_toast("Hello plugin active")

    def deactivate(self):
        pass

    def on_session_connected(self, config_name):
        self.ctx.show_toast(f"{config_name} is up!")

    def on_session_disconnected(self, config_name):
        pass
```

Enable **Developer mode** in Settings to load plugins.

## Localization

Wrap user-visible strings with `_()` from `openvpn3_gui.utils.i18n`.
Extract and compile:

```bash
xgettext -o po/openvpn3-gui.pot --from-code=UTF-8 $(find src -name '*.py')
msginit -l de -i po/openvpn3-gui.pot -o po/de.po
msgfmt po/de.po -o po/build/de/LC_MESSAGES/openvpn3-gui.mo
```

## Release checklist

1. Bump `__version__` in `src/openvpn3_gui/__init__.py`, `pyproject.toml`,
   `packaging/debian/changelog`, `data/org.openvpn3.Gui.metainfo.xml`.
2. `ruff check src && mypy src && pytest`.
3. Build all three packages (see `packaging/*/README.md` and
   `build-appimage.sh`).
4. Smoke-test on a clean Ubuntu 24.04 VM with real openvpn3-linux.
