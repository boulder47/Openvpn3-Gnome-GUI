"""Unit tests for model logic, the cron matcher, and the script runner."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

import pytest

from openvpn3_gui.models.log_entry import LogSeverity
from openvpn3_gui.models.profile import CertificateInfo, Profile
from openvpn3_gui.models.session import Session, SessionStatus
from openvpn3_gui.services.automation_service import cron_matches
from openvpn3_gui.services.script_runner import ScriptRunner


class TestProfileModel:
    def test_matches_query_on_name_tags_notes(self) -> None:
        profile = Profile(
            config_path="/x", name="Office", tags=["work"], notes="backup gateway"
        )
        assert profile.matches_query("office")
        assert profile.matches_query("WORK")
        assert profile.matches_query("backup")
        assert not profile.matches_query("gaming")
        assert profile.matches_query("")  # empty query matches everything


class TestCertificateInfo:
    def test_expiry_flags(self) -> None:
        soon = CertificateInfo(not_after=datetime.now(UTC) + timedelta(days=10))
        far = CertificateInfo(not_after=datetime.now(UTC) + timedelta(days=200))
        past = CertificateInfo(not_after=datetime.now(UTC) - timedelta(days=1))
        assert soon.is_expiring_soon and not soon.is_expired
        assert not far.is_expiring_soon
        assert past.is_expired


class TestSessionModel:
    def test_duration_and_activity(self) -> None:
        session = Session(
            session_path="/s",
            config_name="c",
            status=SessionStatus.CONNECTED,
            connected_since=datetime.now(UTC) - timedelta(minutes=5),
        )
        assert session.is_active
        assert session.duration is not None
        assert session.duration.total_seconds() >= 290


class TestLogSeverity:
    def test_from_text(self) -> None:
        assert LogSeverity.from_text("ERROR") == LogSeverity.ERROR
        assert LogSeverity.from_text("warn") == LogSeverity.WARNING
        assert LogSeverity.from_text("garbage") == LogSeverity.INFO


class TestCronMatcher:
    def test_wildcards(self) -> None:
        assert cron_matches("* * * * *", datetime(2026, 7, 13, 4, 0))

    def test_exact(self) -> None:
        when = datetime(2026, 7, 13, 4, 0)  # a Monday
        assert cron_matches("0 4 * * *", when)
        assert not cron_matches("0 5 * * *", when)

    def test_steps_and_ranges(self) -> None:
        assert cron_matches("*/15 * * * *", datetime(2026, 7, 13, 4, 30))
        assert cron_matches("0 9-17 * * *", datetime(2026, 7, 13, 12, 0))
        assert not cron_matches("0 9-17 * * *", datetime(2026, 7, 13, 20, 0))

    def test_weekday(self) -> None:
        monday = datetime(2026, 7, 13, 4, 0)
        assert cron_matches("0 4 * * 1", monday)
        assert not cron_matches("0 4 * * 0", monday)

    def test_invalid_expression(self) -> None:
        assert not cron_matches("bogus", datetime.now())


class TestMarkupEscaping:
    """Regression tests for the crash: Adw widget title/subtitle/heading/body
    properties are parsed as Pango markup, so any profile name, CLI output,
    or exception text containing '&', '<', or '>' must be escaped before
    reaching them — an unescaped '&' previously crashed the app outright
    (AdwPreferencesGroup title 'Startup & tray')."""

    def test_ampersand_is_escaped(self) -> None:
        from openvpn3_gui.utils.text import escape_markup

        assert escape_markup("Startup & tray") == "Startup &amp; tray"

    def test_angle_brackets_are_escaped(self) -> None:
        from openvpn3_gui.utils.text import escape_markup

        assert escape_markup("<script>") == "&lt;script&gt;"

    def test_none_and_empty_are_safe(self) -> None:
        from openvpn3_gui.utils.text import escape_markup

        assert escape_markup(None) == ""
        assert escape_markup("") == ""

    def test_plain_text_is_unchanged(self) -> None:
        from openvpn3_gui.utils.text import escape_markup

        assert escape_markup("home-office") == "home-office"

    def test_result_is_valid_pango_markup(self) -> None:
        """The escaped output must itself be parseable as markup — i.e. the
        exact property that crashed the app in the field. Skipped in
        environments without the GTK/Pango typelib installed."""

        try:
            import gi

            gi.require_version("Pango", "1.0")
            from gi.repository import Pango
        except (ImportError, ValueError):
            pytest.skip("Pango typelib not available in this environment")

        from openvpn3_gui.utils.text import escape_markup

        dangerous = "Cor & Sons <admin@example.com>"
        escaped = escape_markup(dangerous)
        # Raises GLib.Error if invalid, exactly like the crash this pins.
        Pango.parse_markup(escaped, -1, "\x00")


class TestScriptRunner:
    async def test_runs_script_with_env(self, tmp_path) -> None:
        runner = ScriptRunner(log_dir=tmp_path / "runs")
        script = f'{sys.executable} -c "import os;print(os.environ[\'OVPN3_GUI_PROFILE\'])"'
        execution = await runner.run_hook("post_connect", script, "myprofile")
        assert execution is not None
        assert execution.returncode == 0
        assert "myprofile" in execution.stdout

    async def test_no_script_is_noop(self, tmp_path) -> None:
        runner = ScriptRunner(log_dir=tmp_path / "runs")
        assert await runner.run_hook("pre_connect", None, "p") is None
        assert await runner.run_hook("pre_connect", "   ", "p") is None

    async def test_execution_log_persisted(self, tmp_path) -> None:
        runner = ScriptRunner(log_dir=tmp_path / "runs")
        await runner.run_hook("pre_connect", f"{sys.executable} -c pass", "p")
        entries = runner.recent_executions()
        assert len(entries) == 1
        assert entries[0]["hook"] == "pre_connect"
