"""
GC stale presence files.

Reaps a file when ANY of:
  * `ended_at` is set + age >1h (clean shutdown, normal aging)
  * `ended_at` is null, PID is dead, mtime >1h (crashed/killed session
    — Codex lacks Stop/SessionEnd matchers today, so otherwise
    these accumulate forever and slow every /api/board/list scan)
  * file is unparseable + mtime >1h (corrupt write, never recoverable)

USAGE
    python3 presence_gc.py <presence_dir> <now_epoch>
"""

from __future__ import annotations

import contextlib
import json
import os
import sys

_STALE_AGE_SECS = 3600


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but is owned by another user — still alive.
        return True
    except OSError:
        return False
    return True


def _drop(path: str) -> None:
    """Best-effort unlink; race with another GC tick is the only realistic
    failure and is harmless."""
    with contextlib.suppress(OSError):
        os.unlink(path)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        return 0
    d, now_s = argv[1], argv[2]
    try:
        now = int(now_s)
    except ValueError:
        return 0
    if not os.path.isdir(d):
        return 0
    for name in os.listdir(d):
        if not name.endswith(".json"):
            continue
        p = os.path.join(d, name)
        try:
            mtime = os.path.getmtime(p)
        except OSError:
            continue
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            if now - mtime > _STALE_AGE_SECS:
                _drop(p)
            continue

        ended = data.get("ended_at")
        if isinstance(ended, int) and now - ended > _STALE_AGE_SECS:
            _drop(p)
            continue

        # Crashed-session sweep: ended_at never set + PID dead + old.
        if ended is None and now - mtime > _STALE_AGE_SECS:
            pid_raw = data.get("pid") or 0
            try:
                pid = int(pid_raw)
            except (TypeError, ValueError):
                pid = 0
            if not _pid_alive(pid):
                _drop(p)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
