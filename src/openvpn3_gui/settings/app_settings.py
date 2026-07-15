"""Observable settings controller sitting between the store and the UI/services."""

from __future__ import annotations

import logging
from collections.abc import Callable

from openvpn3_gui.models.settings import AppSettings
from openvpn3_gui.storage.settings_store import SettingsStore

logger = logging.getLogger(__name__)


class SettingsController:
    """Holds the live :class:`AppSettings` instance and notifies listeners on change."""

    def __init__(self, store: SettingsStore | None = None) -> None:
        self._store = store or SettingsStore()
        self._settings = self._store.load()
        self._listeners: list[Callable[[AppSettings], None]] = []

    @property
    def settings(self) -> AppSettings:
        return self._settings

    def subscribe(self, callback: Callable[[AppSettings], None]) -> None:
        self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[AppSettings], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def update(self, mutator: Callable[[AppSettings], None]) -> None:
        """Apply an in-place mutation to the settings, persist, and notify.

        Example::

            controller.update(lambda s: setattr(s, "theme", ThemePreference.DARK))
        """

        mutator(self._settings)
        self._store.save(self._settings)
        for cb in list(self._listeners):
            try:
                cb(self._settings)
            except Exception:  # pragma: no cover
                logger.exception("Settings listener failed")

    def reload(self) -> None:
        self._settings = self._store.load()

    def export_to(self, path: str) -> None:
        from pathlib import Path

        self._store.export_to(self._settings, Path(path))

    def import_from(self, path: str) -> None:
        from pathlib import Path

        self._settings = self._store.import_from(Path(path))
        self._store.save(self._settings)
        for cb in list(self._listeners):
            cb(self._settings)
