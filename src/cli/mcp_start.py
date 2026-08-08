"""
Coding OS — fast-path entrypoint for the MCP server.

PURPOSE
    `cos server-start` (src/cli/main.py) drags in 380ms of CLI subcommand
    imports — irrelevant for MCP boot but charged on every Claude /
    Codex spawn. When an MCP client opens a SECOND subprocess for
    auxiliary work (session-title generation, config-cache loading), the
    duplicated startup cost stacks under contention and pushes init past
    Anthropic VSCode extension's 60s budget.

    This entry point ships ONLY the env-setup + orphan-sweep + execvpe
    logic, with imports trimmed to what those steps need (~5 stdlib
    modules). Cold start drops from ~790ms to ~250ms.

    Wired into pyproject.toml as `cos-mcp-start`. Adapters reference it
    through the .mcp.json renderer so existing `cos server-start`
    invocations keep working.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

_STALE_SERVER_AGE_S = int(os.environ.get("COS_STALE_SERVER_AGE_S", "43200"))


def _parse_etime(s: str) -> int | None:
    """Parse `ps -o etime` output `[[DD-]HH:]MM:SS` → seconds."""
    days = 0
    if "-" in s:
        d, _, s = s.partition("-")
        try:
            days = int(d)
        except ValueError:
            return None
    parts = s.split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 2:
        h, m, sec = 0, nums[0], nums[1]
    elif len(nums) == 3:
        h, m, sec = nums
    else:
        return None
    return days * 86400 + h * 3600 + m * 60 + sec


def _sweep_stale_servers(db_path: str) -> None:
    """Kill prior `src/core/thinking_os/server.py` instances bound to this DB.

    Mirrors cli.main:_sweep_stale_servers so both entrypoints behave
    identically. Fail-open: any error swallowed silently.
    """
    try:
        target_db = str(Path(db_path).resolve())
    except OSError:
        return

    try:
        out = subprocess.run(
            ["ps", "-eo", "pid=,ppid=,etime=,command="],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return
    if out.returncode != 0:
        return

    own_pid = os.getpid()
    server_marker = "src/core/thinking_os/server.py"

    for line in out.stdout.splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
            etimes = _parse_etime(parts[2])
        except ValueError:
            continue
        if etimes is None:
            continue
        cmd = parts[3]
        if pid == own_pid or server_marker not in cmd:
            continue

        try:
            env_out = subprocess.run(
                ["ps", "eww", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=1,
            )
            env_text = env_out.stdout if env_out.returncode == 0 else ""
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            env_text = ""
        if env_text and f"COS_DB_PATH={target_db}" not in env_text:
            continue

        parent_alive = True
        try:
            os.kill(ppid, 0)
        except (OSError, ProcessLookupError):
            parent_alive = False

        if parent_alive and etimes < _STALE_SERVER_AGE_S:
            continue

        try:
            os.kill(pid, 15)  # SIGTERM
        except (OSError, ProcessLookupError) as kill_exception:
            logging.getLogger("coding_os.mcp_start").debug(
                "orphan kill skipped pid=%s: %s",
                pid,
                kill_exception,
            )


def main() -> None:
    """Resolve coding-os layout, sweep orphans, exec server.py."""
    # src/cli/mcp_start.py → coding-os/cli/ → coding-os/
    cos_root = Path(__file__).resolve().parent.parent.parent
    server_py = cos_root / "src" / "core" / "thinking_os" / "server.py"
    if not server_py.exists():
        sys.stderr.write(f"ERROR: MCP server not found at {server_py}\n")
        sys.exit(1)

    caller_cwd = Path.cwd().resolve()
    state_dir = ".coding-os"

    env = os.environ.copy()
    env.setdefault("COS_DB_PATH", str(caller_cwd / state_dir / "thinking_os.db"))
    env.setdefault("COS_STATE_DIR", str(caller_cwd / state_dir))

    _sweep_stale_servers(env["COS_DB_PATH"])

    python = sys.executable
    os.execvpe(python, [python, str(server_py)], env)


if __name__ == "__main__":
    main()
