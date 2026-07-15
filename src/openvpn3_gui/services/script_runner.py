"""Pre/post connect/disconnect script execution with environment injection.

Advanced feature: users can attach hook scripts to the connect/disconnect
lifecycle. Scripts run as the *unprivileged* user (never via sudo/pkexec —
elevation for the tunnel itself is openvpn3-linux's job through its own
D-Bus/PolicyKit machinery), with a controlled environment and a captured,
persisted execution log.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
import shlex
import time
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

EXECUTION_LOG_DIR = Path(
    os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))
) / "openvpn3-gui" / "script-runs"

SCRIPT_TIMEOUT_SECONDS = 60


@dataclasses.dataclass
class ScriptExecution:
    hook: str  # pre_connect | post_connect | pre_disconnect | post_disconnect
    script: str
    profile_name: str
    returncode: int
    stdout: str
    stderr: str
    duration_ms: float
    started_at: datetime

    def to_dict(self) -> dict:
        return dataclasses.asdict(self) | {"started_at": self.started_at.isoformat()}


class ScriptRunner:
    """Runs lifecycle hook scripts and records every execution to disk."""

    def __init__(self, log_dir: Path = EXECUTION_LOG_DIR) -> None:
        self._log_dir = log_dir

    async def run_hook(
        self,
        hook: str,
        script: str | None,
        profile_name: str,
        extra_env: dict[str, str] | None = None,
    ) -> ScriptExecution | None:
        """Execute a hook script if configured; returns None when no script is set.

        The script line is tokenized with :func:`shlex.split` and executed
        directly (no shell), the same injection-safety posture as the CLI
        wrapper. Standard variables exposed to the script:

        * ``OVPN3_GUI_HOOK`` — which lifecycle hook fired
        * ``OVPN3_GUI_PROFILE`` — the profile name involved
        plus any user-defined variables from Settings → Automation.
        """

        if not script or not script.strip():
            return None

        env = dict(os.environ)
        env.update(extra_env or {})
        env["OVPN3_GUI_HOOK"] = hook
        env["OVPN3_GUI_PROFILE"] = profile_name

        argv = shlex.split(script)
        started_at = datetime.now(UTC)
        start = time.monotonic()
        logger.info("Running %s hook for %s: %s", hook, profile_name, script)

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=SCRIPT_TIMEOUT_SECONDS
            )
            returncode = proc.returncode or 0
        except FileNotFoundError:
            logger.error("Hook script not found: %s", argv[0])
            return None
        except TimeoutError:
            proc.kill()
            await proc.wait()
            stdout_b, stderr_b, returncode = b"", b"Script timed out", 124

        execution = ScriptExecution(
            hook=hook,
            script=script,
            profile_name=profile_name,
            returncode=returncode,
            stdout=stdout_b.decode(errors="replace"),
            stderr=stderr_b.decode(errors="replace"),
            duration_ms=(time.monotonic() - start) * 1000,
            started_at=started_at,
        )
        self._persist(execution)
        return execution

    def _persist(self, execution: ScriptExecution) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        log_file = self._log_dir / f"{execution.started_at:%Y%m%d}.jsonl"
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(execution.to_dict()) + "\n")

    def recent_executions(self, limit: int = 100) -> list[dict]:
        entries: list[dict] = []
        if not self._log_dir.exists():
            return entries
        for log_file in sorted(self._log_dir.glob("*.jsonl"), reverse=True):
            for line in log_file.read_text().splitlines():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            if len(entries) >= limit:
                break
        return entries[:limit]
