"""Plugin system: user-provided Python modules extending the application.

Plugins live in ``$XDG_DATA_HOME/openvpn3-gui/plugins/<name>/plugin.py`` and
must expose a ``Plugin`` class implementing :class:`PluginBase`. Plugins get
a restricted context object (services, settings, a toast callback) rather
than the raw application, keeping the surface intentional and testable.

Plugins are only loaded when the user has explicitly enabled the plugin
system in Settings (Developer mode), since loading third-party code is a
deliberate trust decision.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

PLUGIN_DIR = Path(
    os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))
) / "openvpn3-gui" / "plugins"


@dataclasses.dataclass
class PluginContext:
    """The capabilities handed to each plugin instead of raw app internals."""

    openvpn_service: object
    network_service: object
    settings: object
    show_toast: Callable[[str], None]


class PluginBase(Protocol):
    """Interface every plugin's ``Plugin`` class must satisfy."""

    name: str
    version: str

    def activate(self, context: PluginContext) -> None: ...

    def deactivate(self) -> None: ...

    def on_session_connected(self, config_name: str) -> None: ...

    def on_session_disconnected(self, config_name: str) -> None: ...


@dataclasses.dataclass
class LoadedPlugin:
    name: str
    path: Path
    instance: object
    error: str | None = None


class PluginService:
    def __init__(self, plugin_dir: Path = PLUGIN_DIR) -> None:
        self._plugin_dir = plugin_dir
        self._loaded: list[LoadedPlugin] = []

    @property
    def loaded_plugins(self) -> list[LoadedPlugin]:
        return list(self._loaded)

    def discover(self) -> list[Path]:
        if not self._plugin_dir.exists():
            return []
        return sorted(self._plugin_dir.glob("*/plugin.py"))

    def load_all(self, context: PluginContext) -> None:
        for plugin_file in self.discover():
            self._load_one(plugin_file, context)

    def _load_one(self, plugin_file: Path, context: PluginContext) -> None:
        plugin_name = plugin_file.parent.name
        try:
            spec = importlib.util.spec_from_file_location(
                f"openvpn3_gui_plugin_{plugin_name}", plugin_file
            )
            assert spec and spec.loader  # noqa: S101 - importlib invariant
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            plugin_class = getattr(module, "Plugin", None)
            if plugin_class is None:
                raise AttributeError("plugin.py does not define a 'Plugin' class")
            instance = plugin_class()
            instance.activate(context)
            self._loaded.append(LoadedPlugin(name=plugin_name, path=plugin_file, instance=instance))
            logger.info("Loaded plugin: %s", plugin_name)
        except Exception as exc:  # noqa: BLE001 - plugin faults must not crash the app
            logger.exception("Failed to load plugin %s", plugin_name)
            self._loaded.append(
                LoadedPlugin(name=plugin_name, path=plugin_file, instance=None, error=str(exc))
            )

    def broadcast_connected(self, config_name: str) -> None:
        for plugin in self._loaded:
            if plugin.instance is None:
                continue
            try:
                plugin.instance.on_session_connected(config_name)
            except Exception:  # noqa: BLE001
                logger.exception("Plugin %s failed in on_session_connected", plugin.name)

    def broadcast_disconnected(self, config_name: str) -> None:
        for plugin in self._loaded:
            if plugin.instance is None:
                continue
            try:
                plugin.instance.on_session_disconnected(config_name)
            except Exception:  # noqa: BLE001
                logger.exception("Plugin %s failed in on_session_disconnected", plugin.name)

    def unload_all(self) -> None:
        for plugin in self._loaded:
            if plugin.instance is not None:
                try:
                    plugin.instance.deactivate()
                except Exception:  # noqa: BLE001
                    logger.exception("Plugin %s failed to deactivate", plugin.name)
        self._loaded.clear()
