"""Backup/restore of the full application state, plus persisted traffic history.

Backup archive contents (a plain ``.tar.gz``):

* ``settings.json`` — everything in :class:`AppSettings`
* ``profile_metadata.json`` — tags/favorites/notes/groups
* ``profiles/*.ovpn`` — exported copies of every imported configuration
* ``traffic_history.json`` — per-profile daily traffic totals

Credentials are deliberately **excluded**: secrets never leave the GNOME
Keyring in any exportable form.
"""

from __future__ import annotations

import json
import logging
import os
import tarfile
import tempfile
from datetime import date
from pathlib import Path

from openvpn3_gui.services.openvpn_service import OpenVpnService
from openvpn3_gui.storage.profile_store import METADATA_FILE
from openvpn3_gui.storage.settings_store import SETTINGS_FILE

logger = logging.getLogger(__name__)

DATA_DIR = Path(
    os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))
) / "openvpn3-gui"
TRAFFIC_HISTORY_FILE = DATA_DIR / "traffic_history.json"


class TrafficHistoryStore:
    """Persists daily per-profile byte totals so history survives restarts."""

    def __init__(self, path: Path = TRAFFIC_HISTORY_FILE) -> None:
        self._path = path
        self._data: dict = self._load()

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def record(self, profile_name: str, bytes_in: int, bytes_out: int, day: date | None = None) -> None:
        day_key = (day or date.today()).isoformat()
        profile_days = self._data.setdefault(profile_name, {})
        entry = profile_days.setdefault(day_key, {"bytes_in": 0, "bytes_out": 0})
        entry["bytes_in"] = max(entry["bytes_in"], bytes_in)
        entry["bytes_out"] = max(entry["bytes_out"], bytes_out)
        self._persist()

    def history_for(self, profile_name: str) -> dict[str, dict]:
        return dict(self._data.get(profile_name, {}))

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2))


class BackupService:
    def __init__(self, openvpn_service: OpenVpnService) -> None:
        self._service = openvpn_service

    async def create_backup(self, destination: str) -> None:
        """Write a .tar.gz backup archive to ``destination``."""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            profiles_dir = tmp / "profiles"
            profiles_dir.mkdir()

            profiles = await self._service.list_profiles()
            for profile in profiles:
                safe_name = profile.name.replace("/", "_")
                try:
                    await self._service.export_profile(profile, str(profiles_dir / f"{safe_name}.ovpn"))
                except Exception:  # noqa: BLE001 - continue backing up other profiles
                    logger.exception("Could not export profile %s", profile.name)

            with tarfile.open(destination, "w:gz") as tar:
                if SETTINGS_FILE.exists():
                    tar.add(SETTINGS_FILE, arcname="settings.json")
                if METADATA_FILE.exists():
                    tar.add(METADATA_FILE, arcname="profile_metadata.json")
                if TRAFFIC_HISTORY_FILE.exists():
                    tar.add(TRAFFIC_HISTORY_FILE, arcname="traffic_history.json")
                tar.add(profiles_dir, arcname="profiles")
        logger.info("Backup written to %s", destination)

    async def restore_backup(self, archive_path: str) -> int:
        """Restore settings/metadata and re-import every profile. Returns count imported."""

        imported = 0
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(tmp, filter="data")

            settings_src = tmp / "settings.json"
            if settings_src.exists():
                SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
                SETTINGS_FILE.write_text(settings_src.read_text())

            metadata_src = tmp / "profile_metadata.json"
            if metadata_src.exists():
                METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
                METADATA_FILE.write_text(metadata_src.read_text())

            traffic_src = tmp / "traffic_history.json"
            if traffic_src.exists():
                TRAFFIC_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
                TRAFFIC_HISTORY_FILE.write_text(traffic_src.read_text())

            profiles_dir = tmp / "profiles"
            if profiles_dir.exists():
                existing = {p.name for p in await self._service.list_profiles()}
                for ovpn in sorted(profiles_dir.glob("*.ovpn")):
                    name = ovpn.stem
                    if name in existing:
                        logger.info("Skipping already-present profile %s", name)
                        continue
                    try:
                        await self._service.import_profile(str(ovpn), name=name)
                        imported += 1
                    except Exception:  # noqa: BLE001
                        logger.exception("Failed to restore profile %s", name)
        logger.info("Restore complete; %d profiles imported", imported)
        return imported
