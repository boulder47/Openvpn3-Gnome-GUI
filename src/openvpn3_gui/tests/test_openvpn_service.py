"""Integration tests: OpenVpnService end-to-end against the fake CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from openvpn3_gui.models.session import SessionStatus
from openvpn3_gui.openvpn.cli_wrapper import OpenVpn3Cli
from openvpn3_gui.services.openvpn_service import OpenVpnService
from openvpn3_gui.storage.profile_store import ProfileMetadataStore

FAKE_CLI = str(Path(__file__).parent / "fake_openvpn3.py")


class FakeCredentialStore:
    """In-memory stand-in for the GNOME Keyring in tests."""

    def __init__(self) -> None:
        self.data: dict[tuple[str, str], str] = {}
        self.available = True

    async def store(self, profile_name: str, field: str, secret: str) -> None:
        self.data[(profile_name, field)] = secret

    async def retrieve(self, profile_name: str, field: str) -> str | None:
        return self.data.get((profile_name, field))

    async def delete(self, profile_name: str, field: str | None = None) -> None:
        if field:
            self.data.pop((profile_name, field), None)
        else:
            for key in [k for k in self.data if k[0] == profile_name]:
                del self.data[key]

    async def delete_all_for_profile(self, profile_name: str) -> None:
        await self.delete(profile_name)


@pytest.fixture()
def service(tmp_path) -> OpenVpnService:
    return OpenVpnService(
        cli=OpenVpn3Cli(binary_path=FAKE_CLI),
        credential_store=FakeCredentialStore(),
        metadata_store=ProfileMetadataStore(path=tmp_path / "meta.json"),
    )


class TestProfiles:
    async def test_list_profiles(self, service: OpenVpnService) -> None:
        profiles = await service.list_profiles()
        assert len(profiles) == 1
        assert profiles[0].name == "fake-profile"

    async def test_import_profile_uses_reported_path(self, service: OpenVpnService) -> None:
        """Regression test: import_profile must trust config-import's own
        confirmation output rather than round-tripping through the fragile
        configs-list table parse."""

        profile = await service.import_profile("/tmp/whatever.ovpn", name="new-profile")
        assert profile.config_path == "/net/openvpn/v3/configuration/test0002-imported"
        assert profile.name == "new-profile"

    async def test_import_profile_falls_back_when_path_not_reported(
        self, service: OpenVpnService
    ) -> None:
        # Monkeypatch the CLI's subcommand for this one call to simulate a
        # build that doesn't echo the configuration path.
        original_run = service._cli.run  # noqa: SLF001

        async def _patched_run(args, **kwargs):
            if args and args[0] == "config-import":
                args = ["config-import-noname", *args[1:]]
            return await original_run(args, **kwargs)

        service._cli.run = _patched_run  # noqa: SLF001
        profile = await service.import_profile("/tmp/whatever.ovpn", name="fake-profile")
        assert profile.name == "fake-profile"
        assert profile.config_path == "/net/openvpn/v3/configuration/test0001"

    async def test_metadata_applied(self, service: OpenVpnService, tmp_path) -> None:
        profiles = await service.list_profiles()
        service.set_favorite(profiles[0], True)
        service.set_tags(profiles[0], ["work", "eu"])
        profiles = await service.list_profiles()
        assert profiles[0].favorite is True
        assert profiles[0].tags == ["work", "eu"]

    async def test_profile_detail(self, service: OpenVpnService) -> None:
        profiles = await service.list_profiles()
        detail = await service.get_profile_detail(profiles[0])
        assert detail.remote_host == "fake.example.com"


class TestSessions:
    async def test_list_sessions(self, service: OpenVpnService) -> None:
        sessions = await service.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].status == SessionStatus.CONNECTED

    async def test_session_detail_includes_stats(self, service: OpenVpnService) -> None:
        sessions = await service.list_sessions()
        detail = await service.get_session_detail(sessions[0])
        assert detail.stats.bytes_in == 4096
        assert detail.stats.bytes_out == 1024

    async def test_session_detail_populates_without_invalid_flags(
        self, service: OpenVpnService
    ) -> None:
        """Regression test: 'session-manage --query' doesn't exist (exit 8,
        'unrecognized option' on a live install), and 'sessions-list
        --verbose' was never confirmed either. Detail must come from plain
        'sessions-list' (PID, device, owner, server host) plus
        'session-stats', with IP/MTU/DNS read best-effort from the local
        system — and the unconfirmed flags must never be sent."""

        sessions = await service.list_sessions()
        detail = await service.get_session_detail(sessions[0])
        assert detail.pid == 1234
        assert detail.interface == "tun0"
        assert detail.owner == "tester"
        assert detail.server_host == "vpn.example.com"
        assert detail.stats.bytes_in == 4096
        # tun0 won't exist in the test environment; local enrichment must
        # degrade to None/[] silently rather than raising.
        # And the invalid/unconfirmed flags were never sent:
        for execution in service._cli.history.snapshot():  # noqa: SLF001
            assert "--query" not in execution.command
            assert "--verbose" not in execution.command

    async def test_sessions_list_populates_pid_and_interface(
        self, service: OpenVpnService
    ) -> None:
        """Regression test for 'sessions doesn't show pid or interface'."""

        sessions = await service.list_sessions()
        assert sessions[0].pid == 1234
        assert sessions[0].interface == "tun0"

    async def test_disconnect_runs(self, service: OpenVpnService) -> None:
        sessions = await service.list_sessions()
        await service.disconnect(sessions[0])  # should not raise


class TestConnect:
    async def test_connect_streams_lines(self, service: OpenVpnService) -> None:
        profiles = await service.list_profiles()
        lines = [line async for line in service.connect(profiles[0])]
        assert any("Connected" in line for line in lines)


class TestStatus:
    async def test_status_snapshot(self, service: OpenVpnService) -> None:
        status = await service.status()
        assert status["cli_available"] is True
        assert status["connected_count"] == 1


class TestLogs:
    async def test_tail_logs_uses_log_level_flag(self, service: OpenVpnService) -> None:
        lines = [line async for line in service.tail_logs(verbosity=4)]
        assert any("tunnel up" in line for line in lines)

    async def test_tail_logs_falls_back_on_rejected_flag(self, service: OpenVpnService) -> None:
        """Regression test for the '--level' vs '--log-level' bug: if a CLI
        build rejects the verbosity flag entirely, tail_logs must recover
        instead of silently yielding just the CLI's error line."""

        original_log_args = service._log_args  # noqa: SLF001

        def _patched_log_args(session, verbosity):
            args = original_log_args(session, verbosity)
            return ["--level" if a == "--log-level" else a for a in args]

        service._log_args = _patched_log_args  # noqa: SLF001
        lines = [line async for line in service.tail_logs(verbosity=4)]
        assert any("session established" in line for line in lines)
        assert not any("unrecognized option" in line for line in lines[1:])
