"""Local metadata store for profile extras that openvpn3-linux itself does not track.

``openvpn3-linux`` has no concept of "favorite", "tags", "notes", or
"groups" — those are purely GUI conveniences layered on top, keyed by
profile name, and persisted as JSON under
``$XDG_DATA_HOME/openvpn3-gui/profile_metadata.json``.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
from pathlib import Path
from typing import Any

from openvpn3_gui.models.profile import Profile, ProfileGroup

logger = logging.getLogger(__name__)

DATA_DIR = Path(
    os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))
) / "openvpn3-gui"
METADATA_FILE = DATA_DIR / "profile_metadata.json"


@dataclasses.dataclass
class ProfileMetadata:
    tags: list[str] = dataclasses.field(default_factory=list)
    favorite: bool = False
    notes: str = ""


class ProfileMetadataStore:
    """Reads/writes the tags/favorites/notes/groups sidecar file."""

    def __init__(self, path: Path = METADATA_FILE) -> None:
        self._path = path
        self._data: dict[str, Any] = self._load_raw()

    def _load_raw(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"profiles": {}, "groups": {}}
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read profile metadata store: %s", exc)
            return {"profiles": {}, "groups": {}}

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2))

    def get_metadata(self, profile_name: str) -> ProfileMetadata:
        raw = self._data.get("profiles", {}).get(profile_name, {})
        return ProfileMetadata(
            tags=raw.get("tags", []),
            favorite=raw.get("favorite", False),
            notes=raw.get("notes", ""),
        )

    def set_metadata(self, profile_name: str, metadata: ProfileMetadata) -> None:
        self._data.setdefault("profiles", {})[profile_name] = dataclasses.asdict(metadata)
        self._persist()

    def apply_metadata(self, profile: Profile) -> Profile:
        meta = self.get_metadata(profile.name)
        profile.tags = meta.tags
        profile.favorite = meta.favorite
        profile.notes = meta.notes
        return profile

    def remove_profile(self, profile_name: str) -> None:
        self._data.get("profiles", {}).pop(profile_name, None)
        self._persist()

    def rename_profile(self, old_name: str, new_name: str) -> None:
        profiles = self._data.setdefault("profiles", {})
        if old_name in profiles:
            profiles[new_name] = profiles.pop(old_name)
            self._persist()

    # -- Profile groups (bonus feature) -----------------------------------

    def list_groups(self) -> list[ProfileGroup]:
        return [
            ProfileGroup(name=name, **fields)
            for name, fields in self._data.get("groups", {}).items()
        ]

    def save_group(self, group: ProfileGroup) -> None:
        self._data.setdefault("groups", {})[group.name] = {
            "profile_names": group.profile_names,
            "color": group.color,
        }
        self._persist()

    def delete_group(self, name: str) -> None:
        self._data.get("groups", {}).pop(name, None)
        self._persist()
