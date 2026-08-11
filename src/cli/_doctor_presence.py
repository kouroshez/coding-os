"""doctor check: presence zombies — session files the lazy GC could not reap.

Private sibling of cli.doctor; the check is re-exported by
`cli.doctor_checks_runtime`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ._doctor_shared import (
    SEV_PASS,
    SEV_WARN,
    CheckResult,
    DoctorReport,
)


def _check_presence_zombies(project: Path, report: DoctorReport) -> None:
    """presence.no_zombies — flag presence files where ended_at is null AND PID is dead AND
    age >1h.  These are crashed sessions that the lazy GC could not reap
    on its own (Codex+Cursor lack Stop/SessionEnd matchers as of 2026-04).
    Warns at >20 zombies so the live-agents board can't accumulate noise.
    """
    import time as _time

    sessions_root = project / ".coding-os"
    if not sessions_root.is_dir():
        report.checks.append(
            CheckResult(
                "presence.no_zombies",
                SEV_PASS,
                "no .coding-os/ (skip)",
            )
        )
        return

    threshold = 3600
    now = int(_time.time())
    zombies: dict[str, int] = {}
    total_files = 0
    for agent_dir in sessions_root.iterdir():
        if not agent_dir.is_dir():
            continue
        sess_dir = agent_dir / "sessions"
        if not sess_dir.is_dir():
            continue
        count = 0
        for path in sess_dir.glob("*.json"):
            total_files += 1
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if now - mtime <= threshold:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                count += 1
                continue
            if data.get("ended_at") is not None:
                continue
            pid_raw = data.get("pid") or 0
            try:
                pid = int(pid_raw)
            except (TypeError, ValueError):
                pid = 0
            alive = False
            if pid > 0:
                try:
                    os.kill(pid, 0)
                    alive = True
                except ProcessLookupError:
                    alive = False
                except PermissionError:
                    alive = True
                except OSError:
                    alive = False
            if not alive:
                count += 1
        if count:
            zombies[agent_dir.name] = count

    detail = {
        "total_files": total_files,
        "zombies_per_agent": zombies,
        "threshold_secs": threshold,
    }
    total_zombies = sum(zombies.values())
    if total_zombies == 0:
        report.checks.append(
            CheckResult(
                "presence.no_zombies",
                SEV_PASS,
                f"0 zombies across {total_files} session file(s)",
                detail,
            )
        )
        return
    if total_zombies > 20:
        report.checks.append(
            CheckResult(
                "presence.no_zombies",
                SEV_WARN,
                f"{total_zombies} zombie session file(s) — run `cos hooks-list` "
                "or trigger any agent tool call to fire presence_gc.py",
                detail,
            )
        )
        return
    report.checks.append(
        CheckResult(
            "presence.no_zombies",
            SEV_PASS,
            f"{total_zombies} zombie file(s) (<20 threshold) — GC will reap on next tick",
            detail,
        )
    )
