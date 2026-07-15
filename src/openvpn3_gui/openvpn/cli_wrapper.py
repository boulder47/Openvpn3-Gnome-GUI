"""Low-level async wrapper around the ``openvpn3`` command-line tool.

This is the *only* module in the whole application allowed to spawn the
``openvpn3`` process. Every other layer (services, UI, tray, automation)
must go through :class:`OpenVpn3Cli` or, preferably, through
:class:`openvpn3_gui.services.openvpn_service.OpenVpnService`.

Design goals
------------
* Never calls a shell (``shell=False`` semantics via
  ``asyncio.create_subprocess_exec``) — arguments are passed as a list, so
  there is no shell-injection surface.
* Every invocation is timed, logged, and recorded into a ring buffer that
  powers the Developer Console (command, args, exit code, stdout, stderr,
  duration).
* Supports "auto discovery" of the CLI's own subcommands/options by parsing
  ``openvpn3 help`` / ``openvpn3 <cmd> --help`` at runtime, so the wrapper
  degrades gracefully across CLI versions instead of hard-coding a fixed
  command set.
* Long-running commands (``session-start``, ``log --session-path ...``)
  are exposed as async generators that yield lines as they arrive, so the
  UI can stream live output (auth prompts, log tailing) without blocking.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import shutil
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from openvpn3_gui.utils.errors import CliExecutionError, CliNotFoundError, CliTimeoutError

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclasses.dataclass
class CommandExecution:
    """A record of one CLI invocation, used by the Developer Console."""

    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_ms: float
    started_at: datetime
    timed_out: bool = False

    def to_dict(self) -> dict:
        return {
            "command": " ".join(self.command),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": round(self.duration_ms, 1),
            "started_at": self.started_at.isoformat(),
            "timed_out": self.timed_out,
        }


class CommandHistory:
    """Bounded, observable history of executed commands (Developer Console)."""

    def __init__(self, maxlen: int = 500) -> None:
        self._items: list[CommandExecution] = []
        self._maxlen = maxlen
        self._listeners: list = []

    def add(self, execution: CommandExecution) -> None:
        self._items.append(execution)
        if len(self._items) > self._maxlen:
            self._items.pop(0)
        for cb in list(self._listeners):
            try:
                cb(execution)
            except Exception:  # pragma: no cover
                logger.exception("Command history listener failed")

    def subscribe(self, callback) -> None:
        self._listeners.append(callback)

    def unsubscribe(self, callback) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def snapshot(self) -> list[CommandExecution]:
        return list(self._items)


class OpenVpn3Cli:
    """Async, injectable wrapper around the ``openvpn3`` executable."""

    def __init__(
        self,
        binary_path: str | None = None,
        history: CommandHistory | None = None,
        default_timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._binary_path = binary_path
        self._history = history or CommandHistory()
        self._default_timeout = default_timeout
        self._help_cache: dict[str, str] = {}

    @property
    def history(self) -> CommandHistory:
        return self._history

    def resolve_binary(self) -> str:
        if self._binary_path:
            return self._binary_path
        found = shutil.which("openvpn3")
        if not found:
            raise CliNotFoundError(
                "The 'openvpn3' executable was not found on PATH. Install "
                "openvpn3-linux (https://openvpn.net/openvpn3-linux/) or set "
                "a custom path in Settings → Advanced → CLI path."
            )
        self._binary_path = found
        return found

    def set_binary_path(self, path: str | None) -> None:
        self._binary_path = path

    async def version(self) -> str:
        result = await self.run(["version"])
        return result.stdout.strip()

    async def run(
        self,
        args: list[str],
        timeout: float | None = None,
        input_text: str | None = None,
    ) -> CommandExecution:
        """Run ``openvpn3 <args>`` to completion and return captured output."""

        binary = self.resolve_binary()
        command = [binary, *args]
        started_at = datetime.now(UTC)
        start = time.monotonic()
        timed_out = False

        logger.debug("Executing: %s", " ".join(command))
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE if input_text is not None else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise CliNotFoundError(str(exc)) from exc

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(input_text.encode() if input_text else None),
                timeout=timeout or self._default_timeout,
            )
        except TimeoutError:
            timed_out = True
            proc.kill()
            await proc.wait()
            stdout_b, stderr_b = b"", b"Command timed out"

        duration_ms = (time.monotonic() - start) * 1000
        execution = CommandExecution(
            command=command,
            returncode=proc.returncode if proc.returncode is not None else -1,
            stdout=stdout_b.decode(errors="replace"),
            stderr=stderr_b.decode(errors="replace"),
            duration_ms=duration_ms,
            started_at=started_at,
            timed_out=timed_out,
        )
        self._history.add(execution)

        if timed_out:
            raise CliTimeoutError(f"Command timed out: {' '.join(command)}")
        if execution.returncode != 0:
            raise CliExecutionError(
                command, execution.returncode, execution.stdout, execution.stderr
            )
        return execution

    async def run_streaming(
        self, args: list[str]
    ) -> AsyncIterator[str]:
        """Run a long-lived ``openvpn3`` command, yielding stdout lines as they arrive.

        Used for ``session-start`` (interactive auth prompts) and
        ``log --session-path ... `` (live tailing).
        """

        binary = self.resolve_binary()
        command = [binary, *args]
        logger.debug("Streaming: %s", " ".join(command))
        started_at = datetime.now(UTC)
        start = time.monotonic()

        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self._streaming_proc = proc
        collected: list[str] = []
        try:
            assert proc.stdout is not None  # noqa: S101 - invariant: PIPE was requested
            async for raw_line in proc.stdout:
                line = raw_line.decode(errors="replace").rstrip("\n")
                collected.append(line)
                yield line
        finally:
            returncode = await proc.wait()
            duration_ms = (time.monotonic() - start) * 1000
            self._history.add(
                CommandExecution(
                    command=command,
                    returncode=returncode,
                    stdout="\n".join(collected),
                    stderr="",
                    duration_ms=duration_ms,
                    started_at=started_at,
                )
            )

    async def send_stdin(self, text: str) -> None:
        """Send a line of input to the currently running streaming process.

        Used to answer interactive prompts (username/password/OTP) emitted
        by ``openvpn3 session-start``.
        """

        proc = getattr(self, "_streaming_proc", None)
        if proc is None or proc.stdin is None:
            raise RuntimeError("No streaming process is currently active")
        proc.stdin.write((text + "\n").encode())
        await proc.stdin.drain()

    async def help_text(self, subcommand: str | None = None) -> str:
        """Return ``openvpn3 help`` or ``openvpn3 <subcommand> --help`` output.

        Cached per-process. This is the mechanism the UI/service layer use to
        auto-discover every option a given openvpn3 build supports, so the
        GUI does not need to hard-code a specific CLI version's flag set.
        """

        cache_key = subcommand or "__root__"
        if cache_key in self._help_cache:
            return self._help_cache[cache_key]
        args = [subcommand, "--help"] if subcommand else ["help"]
        try:
            result = await self.run(args, timeout=10)
            text = result.stdout
        except CliExecutionError as exc:
            # Some subcommands print --help output to stdout AND exit 1.
            text = exc.stdout or exc.stderr
        self._help_cache[cache_key] = text
        return text

    async def discover_subcommands(self) -> list[str]:
        """Parse top-level ``openvpn3 help`` output into a list of subcommand names."""

        text = await self.help_text()
        commands: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.endswith(":"):
                continue
            first_token = stripped.split()[0]
            if first_token.replace("-", "").isalpha() and first_token.islower():
                commands.append(first_token)
        return sorted(set(commands))
