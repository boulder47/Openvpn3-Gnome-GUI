"""High-level, dependency-injected service exposing every OpenVPN3 capability.

This is the *only* class the UI layer is allowed to talk to for anything
openvpn3-related. It composes :class:`OpenVpn3Cli` (subprocess wrapper),
the parsers, the keyring, and the profile metadata store, and returns rich
dataclasses instead of raw text.

Every public method is ``async def`` and safe to call from a GLib-driven
event loop via :func:`openvpn3_gui.utils.async_utils.run_async`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from dataclasses import replace

from openvpn3_gui.models.profile import Profile
from openvpn3_gui.models.session import Session, SessionStatus
from openvpn3_gui.openvpn.cli_wrapper import OpenVpn3Cli
from openvpn3_gui.openvpn.parser import (
    parse_config_acl,
    parse_config_show,
    parse_configs_list,
    parse_session_stats,
    parse_sessions_list,
)
from openvpn3_gui.storage.keyring import CredentialStore
from openvpn3_gui.storage.profile_store import ProfileMetadataStore
from openvpn3_gui.utils.errors import (
    AuthenticationRequired,
    CliExecutionError,
    ProfileNotFoundError,
)

logger = logging.getLogger(__name__)


class OpenVpnService:
    """Facade over the openvpn3 CLI. Inject fakes for this class in tests."""

    def __init__(
        self,
        cli: OpenVpn3Cli | None = None,
        credential_store: CredentialStore | None = None,
        metadata_store: ProfileMetadataStore | None = None,
    ) -> None:
        self._cli = cli or OpenVpn3Cli()
        self._credentials = credential_store or CredentialStore()
        self._metadata = metadata_store or ProfileMetadataStore()

    # -- Introspection / capability discovery -----------------------------

    async def check_service_available(self) -> bool:
        """Verify the openvpn3-linux D-Bus service and CLI are reachable."""

        try:
            await self._cli.version()
            return True
        except Exception:  # noqa: BLE001
            logger.exception("openvpn3 service unavailable")
            return False

    async def discover_capabilities(self) -> list[str]:
        """List every subcommand this installed openvpn3 CLI supports."""

        return await self._cli.discover_subcommands()

    async def cli_version(self) -> str:
        return await self._cli.version()

    # -- Profile management -------------------------------------------------

    async def list_profiles(self) -> list[Profile]:
        result = await self._cli.run(["configs-list"])
        profiles = parse_configs_list(result.stdout)
        return [self._metadata.apply_metadata(p) for p in profiles]

    async def get_profile_detail(self, profile: Profile) -> Profile:
        show = await self._cli.run(["config-show", "--config", profile.name])
        detailed = parse_config_show(show.stdout, profile.config_path, profile.name)
        try:
            acl_result = await self._cli.run(["config-acl", "--config", profile.name])
            detailed.acl = parse_config_acl(acl_result.stdout)
        except CliExecutionError:
            logger.debug("config-acl not available for %s", profile.name)
        return self._metadata.apply_metadata(detailed)

    async def import_profile(
        self,
        file_path: str,
        name: str | None = None,
        persistent: bool = True,
    ) -> Profile:
        args = ["config-import", "--config", file_path]
        if name:
            args += ["--name", name]
        if persistent:
            args.append("--persistent")
        result = await self._cli.run(args)
        display_name = name or file_path.rsplit("/", 1)[-1]

        # Prefer the config path the CLI just reported for this exact
        # import, rather than round-tripping through `configs-list` (whose
        # table layout varies across openvpn3-linux releases and is a
        # fragile way to confirm something we already know succeeded).
        path_match = re.search(r"(/net/openvpn/v3/configuration/\S+)", result.stdout)
        if path_match:
            profile = Profile(config_path=path_match.group(1), name=display_name, persistent=persistent)
            return self._metadata.apply_metadata(profile)

        logger.warning(
            "config-import for '%s' did not report a configuration path; "
            "falling back to configs-list lookup by name",
            display_name,
        )
        profiles = await self.list_profiles()
        for profile in profiles:
            if profile.name == display_name:
                return profile
        raise ProfileNotFoundError(
            f"Imported profile '{display_name}' not found after import. "
            f"Raw config-import output: {result.stdout!r}"
        )

    async def import_profile_from_url(self, url: str, name: str) -> Profile:
        """Bonus feature: download an .ovpn from a URL, then import it.

        Uses ``asyncio``-based HTTP fetch (kept out of the CLI wrapper since
        it isn't an openvpn3 subcommand) and writes to a temp file before
        delegating to :meth:`import_profile`.
        """

        import tempfile
        import urllib.request

        with tempfile.NamedTemporaryFile(suffix=".ovpn", delete=False) as tmp:
            with urllib.request.urlopen(url, timeout=15) as response:  # noqa: S310
                tmp.write(response.read())
            tmp_path = tmp.name
        return await self.import_profile(tmp_path, name=name)

    async def export_profile(self, profile: Profile, destination_path: str) -> None:
        result = await self._cli.run(["config-show", "--config", profile.name])
        with open(destination_path, "w", encoding="utf-8") as fh:
            fh.write(result.stdout)

    async def remove_profile(self, profile: Profile) -> None:
        await self._cli.run(["config-remove", "--config", profile.name, "--force"])
        self._metadata.remove_profile(profile.name)
        await self._credentials.delete_all_for_profile(profile.name)

    async def rename_profile(self, profile: Profile, new_name: str) -> Profile:
        await self._cli.run(
            ["config-manage", "--config", profile.name, "--rename", new_name]
        )
        self._metadata.rename_profile(profile.name, new_name)
        return replace(profile, name=new_name)

    async def duplicate_profile(self, profile: Profile, new_name: str) -> Profile:
        export_result = await self._cli.run(["config-show", "--config", profile.name])
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ovpn", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(export_result.stdout)
            tmp_path = tmp.name
        return await self.import_profile(tmp_path, name=new_name)

    async def set_profile_acl(
        self,
        profile: Profile,
        public: bool | None = None,
        grant_user: str | None = None,
        revoke_user: str | None = None,
        lock_down: bool | None = None,
    ) -> None:
        args = ["config-acl", "--config", profile.name]
        if public is True:
            args.append("--public-access")
        elif public is False:
            args.append("--no-public-access")
        if grant_user:
            args += ["--grant", grant_user]
        if revoke_user:
            args += ["--revoke", revoke_user]
        if lock_down is True:
            args.append("--lock-down")
        await self._cli.run(args)

    def set_favorite(self, profile: Profile, favorite: bool) -> None:
        meta = self._metadata.get_metadata(profile.name)
        meta.favorite = favorite
        self._metadata.set_metadata(profile.name, meta)

    def set_tags(self, profile: Profile, tags: list[str]) -> None:
        meta = self._metadata.get_metadata(profile.name)
        meta.tags = tags
        self._metadata.set_metadata(profile.name, meta)

    def set_notes(self, profile: Profile, notes: str) -> None:
        meta = self._metadata.get_metadata(profile.name)
        meta.notes = notes
        self._metadata.set_metadata(profile.name, meta)

    # -- Session / connection management ------------------------------------

    async def list_sessions(self) -> list[Session]:
        result = await self._cli.run(["sessions-list"])
        return parse_sessions_list(result.stdout)

    async def get_session_detail(self, session: Session) -> Session:
        """Enrich a session with everything obtainable for it.

        The openvpn3 CLI has no ``session-manage --query`` (confirmed on a
        live install: exit 8, "unrecognized option") — the per-session
        facts it *does* expose live in plain ``sessions-list`` (PID,
        device, owner, status, created, session name) and
        ``session-stats`` (byte/packet counters). Anything beyond that
        (tunnel IP addresses, MTU, DNS) is not printed by any confirmed
        openvpn3 subcommand, so it is read from the local system for the
        session's tun device. Each step is independent: one source
        failing must not blank the others.
        """

        try:
            for refreshed in await self.list_sessions():
                if refreshed.session_path == session.session_path:
                    session = refreshed
                    break
        except CliExecutionError:
            logger.debug("sessions-list refresh failed for %s", session.session_path)

        try:
            stats_result = await self._cli.run(
                ["session-stats", "--session-path", session.session_path]
            )
            session.stats = parse_session_stats(stats_result.stdout)
        except CliExecutionError:
            logger.debug("session-stats unavailable for %s", session.session_path)

        if session.interface:
            try:
                await self._enrich_from_interface(session)
            except Exception:  # noqa: BLE001 - best-effort local enrichment
                logger.debug("Interface enrichment failed for %s", session.interface)
        return session

    @staticmethod
    async def _enrich_from_interface(session: Session) -> None:
        """Fill IP/MTU/DNS from the local tun device (openvpn3 doesn't print them)."""

        import asyncio
        import json
        from pathlib import Path

        iface = session.interface
        mtu_path = Path(f"/sys/class/net/{iface}/mtu")
        if session.mtu is None and mtu_path.exists():
            try:
                session.mtu = int(mtu_path.read_text().strip())
            except (OSError, ValueError):
                pass

        if session.vpn_ipv4 is None or session.vpn_ipv6 is None:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ip",
                    "-j",
                    "addr",
                    "show",
                    "dev",
                    iface,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                stdout_b, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                if proc.returncode == 0:
                    for entry in json.loads(stdout_b.decode() or "[]"):
                        for addr in entry.get("addr_info", []):
                            if addr.get("family") == "inet" and session.vpn_ipv4 is None:
                                session.vpn_ipv4 = addr.get("local")
                            elif addr.get("family") == "inet6" and session.vpn_ipv6 is None:
                                local = addr.get("local", "")
                                if not local.startswith("fe80"):
                                    session.vpn_ipv6 = local
            except (OSError, TimeoutError, json.JSONDecodeError, FileNotFoundError):
                pass

        if not session.dns_servers:
            try:
                with open("/etc/resolv.conf", encoding="utf-8") as fh:
                    session.dns_servers = [
                        line.split()[1]
                        for line in fh
                        if line.startswith("nameserver") and len(line.split()) >= 2
                    ]
            except OSError:
                pass

    async def connect(
        self,
        profile: Profile,
        credential_callback=None,
    ) -> AsyncIterator[str]:
        """Start a session and yield raw CLI lines, handling auth prompts.

        ``credential_callback(prompt: str) -> awaitable[str]`` is invoked
        whenever the CLI asks for interactive input (username, password,
        OTP, private key passphrase, PKCS#11 PIN). If a saved credential
        exists in the keyring, it is supplied automatically instead of
        calling back into the UI.
        """

        args = ["session-start", "--config", profile.name]
        async for line in self._cli.run_streaming(args):
            lowered = line.lower()
            if any(p in lowered for p in ("username:", "password:", "otp", "pin:", "challenge")):
                answer = await self._resolve_credential(profile, line, credential_callback)
                if answer is not None:
                    await self._cli.send_stdin(answer)
            yield line

    async def _resolve_credential(
        self, profile: Profile, prompt: str, credential_callback
    ) -> str | None:
        field = self._guess_credential_field(prompt)
        if self._credentials.available:
            saved = await self._credentials.retrieve(profile.name, field)
            if saved:
                return saved
        if credential_callback is None:
            raise AuthenticationRequired(profile.config_path, challenge=prompt)
        result = credential_callback(prompt)
        if hasattr(result, "__await__"):
            return await result
        return result

    @staticmethod
    def _guess_credential_field(prompt: str) -> str:
        lowered = prompt.lower()
        if "password" in lowered:
            return "password"
        if "username" in lowered:
            return "username"
        if "otp" in lowered or "challenge" in lowered:
            return "otp"
        if "pin" in lowered:
            return "pkcs11_pin"
        return "misc"

    async def save_credential(self, profile: Profile, field: str, value: str) -> None:
        await self._credentials.store(profile.name, field, value)

    async def disconnect(self, session: Session) -> None:
        await self._cli.run(
            ["session-manage", "--session-path", session.session_path, "--disconnect"]
        )

    async def reconnect(self, session: Session) -> None:
        await self._cli.run(
            ["session-manage", "--session-path", session.session_path, "--restart"]
        )

    async def pause(self, session: Session) -> None:
        await self._cli.run(
            ["session-manage", "--session-path", session.session_path, "--pause"]
        )

    async def resume(self, session: Session) -> None:
        await self._cli.run(
            ["session-manage", "--session-path", session.session_path, "--resume"]
        )

    async def set_auto_reconnect(self, session: Session, enabled: bool) -> None:
        """Toggle automatic session restart.

        NOTE: ``--auto-restart``/``--no-auto-restart`` are not confirmed to
        exist on all (or any) openvpn3-linux releases — the same risk class
        as the ``--query`` flag that turned out not to exist. Until
        verified against a live install (``openvpn3 session-manage
        --help``), an unrecognized-option failure here is logged and
        swallowed rather than surfaced as an error, and the in-app
        reconnect watchers (network/resume/monitor) provide the actual
        auto-reconnect behavior regardless.
        """

        flag = "--auto-restart" if enabled else "--no-auto-restart"
        try:
            await self._cli.run(
                ["session-manage", "--session-path", session.session_path, flag]
            )
        except CliExecutionError as exc:
            if "unrecognized option" in (exc.stderr or ""):
                logger.warning(
                    "This openvpn3 build does not support %s; relying on the "
                    "app-level reconnect watchers instead",
                    flag,
                )
            else:
                raise

    # -- Logs -----------------------------------------------------------------

    async def tail_logs(
        self, session: Session | None = None, verbosity: int = 4
    ) -> AsyncIterator[str]:
        """Stream live log lines for a session, or the global service log.

        Uses ``--log-level`` (the correct openvpn3-linux flag; earlier
        drafts of this wrapper incorrectly used ``--level``). If an
        installed CLI version still rejects it, automatically retries
        without a verbosity flag rather than surfacing a broken log tail.
        """

        args = self._log_args(session, verbosity)
        first = True
        async for line in self._cli.run_streaming(args):
            if first and "unrecognized option" in line.lower():
                logger.warning(
                    "openvpn3 log rejected --log-level on this CLI version; "
                    "retrying without a verbosity flag"
                )
                async for fallback_line in self._cli.run_streaming(self._log_args(session, None)):
                    yield fallback_line
                return
            first = False
            yield line

    @staticmethod
    def _log_args(session: Session | None, verbosity: int | None) -> list[str]:
        args = ["log"]
        if verbosity is not None:
            args += ["--log-level", str(verbosity)]
        if session is not None:
            args += ["--session-path", session.session_path]
        return args

    # -- Status / dashboard aggregation ---------------------------------------

    async def status(self) -> dict:
        """A compact snapshot used to populate the Dashboard on first load."""

        sessions = await self.list_sessions()
        connected = [s for s in sessions if s.status == SessionStatus.CONNECTED]
        return {
            "cli_available": await self.check_service_available(),
            "session_count": len(sessions),
            "connected_count": len(connected),
            "sessions": sessions,
        }
