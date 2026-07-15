"""Integration tests for the CLI wrapper against the fake openvpn3 binary."""

from __future__ import annotations

from pathlib import Path

import pytest

from openvpn3_gui.openvpn.cli_wrapper import OpenVpn3Cli
from openvpn3_gui.utils.errors import CliExecutionError, CliNotFoundError, CliTimeoutError

FAKE_CLI = str(Path(__file__).parent / "fake_openvpn3.py")


def make_cli(**kwargs) -> OpenVpn3Cli:
    # Route through the current interpreter via a tiny wrapper approach:
    # OpenVpn3Cli execs the binary path directly, so point it at the script
    # (it has a shebang and is invoked through sys.executable in CI-safe way
    # by using the interpreter as the "binary" is not possible, so mark it
    # executable in conftest instead).
    return OpenVpn3Cli(binary_path=FAKE_CLI, **kwargs)


class TestRun:
    async def test_version(self) -> None:
        cli = make_cli()
        result = await cli.run(["version"])
        assert result.returncode == 0
        assert "fake" in result.stdout

    async def test_failure_raises_with_details(self) -> None:
        cli = make_cli()
        with pytest.raises(CliExecutionError) as exc_info:
            await cli.run(["fail"])
        assert exc_info.value.returncode == 3
        assert "boom" in exc_info.value.stderr

    async def test_timeout(self) -> None:
        cli = make_cli(default_timeout=0.3)
        with pytest.raises(CliTimeoutError):
            await cli.run(["hang"])

    async def test_missing_binary(self) -> None:
        cli = OpenVpn3Cli(binary_path="/nonexistent/openvpn3")
        with pytest.raises(CliNotFoundError):
            await cli.run(["version"])

    async def test_history_records_everything(self) -> None:
        cli = make_cli()
        await cli.run(["version"])
        try:
            await cli.run(["fail"])
        except CliExecutionError:
            pass
        history = cli.history.snapshot()
        assert len(history) == 2
        assert history[0].returncode == 0
        assert history[1].returncode == 3
        assert history[1].duration_ms >= 0


class TestStreaming:
    async def test_streaming_yields_lines(self) -> None:
        cli = make_cli()
        lines = [line async for line in cli.run_streaming(["session-start"])]
        assert any("Session path" in line for line in lines)
        assert any("Connected" in line for line in lines)

    async def test_streaming_recorded_in_history(self) -> None:
        cli = make_cli()
        async for _line in cli.run_streaming(["session-start"]):
            pass
        assert len(cli.history.snapshot()) == 1


class TestDiscovery:
    async def test_discover_subcommands(self) -> None:
        cli = make_cli()
        commands = await cli.discover_subcommands()
        assert "configs-list" in commands
        assert "sessions-list" in commands

    async def test_help_is_cached(self) -> None:
        cli = make_cli()
        await cli.help_text()
        await cli.help_text()
        assert len(cli.history.snapshot()) == 1
