"""Unit tests for the storage layer (settings, metadata, traffic history)."""

from __future__ import annotations

from openvpn3_gui.models.profile import Profile, ProfileGroup
from openvpn3_gui.models.settings import AppSettings, ThemePreference
from openvpn3_gui.storage.profile_store import ProfileMetadataStore
from openvpn3_gui.storage.settings_store import SettingsStore


class TestSettingsStore:
    def test_defaults_when_missing(self, tmp_path) -> None:
        store = SettingsStore(path=tmp_path / "settings.json")
        settings = store.load()
        assert settings.theme == ThemePreference.SYSTEM
        assert settings.notifications.on_connect is True

    def test_roundtrip(self, tmp_path) -> None:
        path = tmp_path / "settings.json"
        store = SettingsStore(path=path)
        settings = AppSettings(theme=ThemePreference.DARK, cli_path="/opt/openvpn3")
        settings.notifications.on_error = False
        settings.automation.scheduled_reconnect_cron = "30 2 * * *"
        store.save(settings)

        loaded = SettingsStore(path=path).load()
        assert loaded.theme == ThemePreference.DARK
        assert loaded.cli_path == "/opt/openvpn3"
        assert loaded.notifications.on_error is False
        assert loaded.automation.scheduled_reconnect_cron == "30 2 * * *"

    def test_corrupt_file_falls_back_to_defaults(self, tmp_path) -> None:
        path = tmp_path / "settings.json"
        path.write_text("{not json")
        settings = SettingsStore(path=path).load()
        assert settings.theme == ThemePreference.SYSTEM

    def test_export_import(self, tmp_path) -> None:
        store = SettingsStore(path=tmp_path / "settings.json")
        settings = AppSettings(theme=ThemePreference.LIGHT)
        export_path = tmp_path / "export.json"
        store.export_to(settings, export_path)
        imported = store.import_from(export_path)
        assert imported.theme == ThemePreference.LIGHT


class TestProfileMetadataStore:
    def test_defaults(self, tmp_path) -> None:
        store = ProfileMetadataStore(path=tmp_path / "meta.json")
        meta = store.get_metadata("unknown")
        assert meta.favorite is False
        assert meta.tags == []

    def test_set_and_apply(self, tmp_path) -> None:
        store = ProfileMetadataStore(path=tmp_path / "meta.json")
        meta = store.get_metadata("p1")
        meta.favorite = True
        meta.tags = ["home"]
        meta.notes = "primary"
        store.set_metadata("p1", meta)

        profile = Profile(config_path="/x", name="p1")
        store.apply_metadata(profile)
        assert profile.favorite is True
        assert profile.tags == ["home"]
        assert profile.notes == "primary"

    def test_rename(self, tmp_path) -> None:
        store = ProfileMetadataStore(path=tmp_path / "meta.json")
        meta = store.get_metadata("old")
        meta.favorite = True
        store.set_metadata("old", meta)
        store.rename_profile("old", "new")
        assert store.get_metadata("new").favorite is True
        assert store.get_metadata("old").favorite is False

    def test_groups(self, tmp_path) -> None:
        store = ProfileMetadataStore(path=tmp_path / "meta.json")
        store.save_group(ProfileGroup(name="Work", profile_names=["a", "b"], color="#3584e4"))
        groups = store.list_groups()
        assert len(groups) == 1
        assert groups[0].profile_names == ["a", "b"]
        store.delete_group("Work")
        assert store.list_groups() == []


class TestTrafficHistory:
    def test_record_and_read(self, tmp_path) -> None:
        from openvpn3_gui.services.backup_service import TrafficHistoryStore

        store = TrafficHistoryStore(path=tmp_path / "traffic.json")
        store.record("p1", bytes_in=100, bytes_out=50)
        store.record("p1", bytes_in=200, bytes_out=80)  # monotonic max per day
        history = store.history_for("p1")
        assert len(history) == 1
        day = next(iter(history.values()))
        assert day["bytes_in"] == 200
        assert day["bytes_out"] == 80
