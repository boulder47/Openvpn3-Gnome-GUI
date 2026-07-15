"""Shared pytest fixtures."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

FAKE_CLI = Path(__file__).parent / "fake_openvpn3.py"


def pytest_configure(config) -> None:
    """Ensure the fake openvpn3 script is executable so exec() works directly."""

    mode = FAKE_CLI.stat().st_mode
    FAKE_CLI.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture()
def isolated_xdg(tmp_path, monkeypatch):
    """Redirect all XDG dirs into a tmpdir so tests never touch real user data."""

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return tmp_path
