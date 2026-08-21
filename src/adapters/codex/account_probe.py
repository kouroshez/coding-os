"""Codex account state — plan, auth mode and rate-limit windows.

The Codex CLI has no local usage command, but it records the server's
`rate_limits` block into every session rollout beside the token counts. The
freshest rollout is therefore the freshest quota reading available offline —
and because supervised dispatch runs `codex exec`, our own dispatches are what
keep it current.

`auth.json` is opened for one field, `auth_mode`. The OAuth tokens beside it are
never read and never returned.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from thinking_os.account_status import unavailable

SOURCE = "~/.codex/sessions :: token_count.rate_limits"

# A rollout grows for the life of a session and the block we want is written on
# every turn, so the last one is always near the end. Reading a bounded tail
# keeps the probe O(1) in session length instead of O(file), which matters
# because the Hub polls this route.
_TAIL_BYTES = 512 * 1024
# A resumed session appends to the file under its original date, so "newest
# directory" alone would miss it. A week of directories bounds the scan while
# covering any resume an operator would recognise as recent.
_DAYS_SCANNED = 7


def _codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def _auth_mode(home: Path) -> str:
    if os.environ.get("OPENAI_API_KEY", "").strip() or os.environ.get("CODEX_API_KEY", "").strip():
        return "api_key"
    try:
        raw = json.loads((home / "auth.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "unknown"
    mode = str(raw.get("auth_mode") or "").strip().lower() if isinstance(raw, dict) else ""
    if mode == "chatgpt":
        return "subscription"
    return "api_key" if mode in {"apikey", "api_key"} else "unknown"


def _recent_rollouts(home: Path) -> list[Path]:
    sessions = home / "sessions"
    if not sessions.is_dir():
        return []
    # Date-partitioned as sessions/YYYY/MM/DD, so lexicographic order is
    # chronological order and no stat call is needed to rank the directories.
    days: list[Path] = []
    for year in sorted((p for p in sessions.iterdir() if p.is_dir()), reverse=True):
        for month in sorted((p for p in year.iterdir() if p.is_dir()), reverse=True):
            days.extend(sorted((p for p in month.iterdir() if p.is_dir()), reverse=True))
            if len(days) >= _DAYS_SCANNED:
                break
        if len(days) >= _DAYS_SCANNED:
            break
    files = [f for day in days[:_DAYS_SCANNED] for f in day.glob("*.jsonl")]
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)


def _last_rate_limits(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - _TAIL_BYTES))
            # A mid-line seek yields one broken record; json.loads rejects it and
            # the loop moves on, which is cheaper than aligning the offset.
            tail = handle.read().decode("utf-8", errors="ignore")
    except OSError:
        return None, None
    for line in reversed(tail.splitlines()):
        if '"rate_limits"' not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        limits = (record.get("payload") or {}).get("rate_limits")
        if isinstance(limits, dict):
            return limits, record.get("timestamp")
    return None, None


def _window(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    resets_at = raw.get("resets_at")
    if isinstance(resets_at, (int, float)) and resets_at > 0:
        resets_at = datetime.fromtimestamp(float(resets_at), tz=UTC).isoformat()
    else:
        resets_at = None
    minutes = raw.get("window_minutes")
    return {
        "percent": raw.get("used_percent"),
        "resets_at": resets_at,
        "window_minutes": int(minutes) if isinstance(minutes, (int, float)) else None,
    }


def probe_account() -> dict[str, Any]:
    """Report Codex plan, auth mode and rate-limit windows from the newest rollout."""
    home = _codex_home()
    rollouts = _recent_rollouts(home)
    if not rollouts:
        return unavailable("codex", f"no session rollouts under {home / 'sessions'}", SOURCE)

    for path in rollouts:
        limits, observed_at = _last_rate_limits(path)
        if limits is None:
            continue
        windows = [w for w in (_window(limits.get(k)) for k in ("primary", "secondary")) if w]
        if not windows:
            continue
        return {
            "status": "ok",
            "auth_mode": _auth_mode(home),
            "plan": str(limits.get("plan_type") or ""),
            "source": SOURCE,
            "observed_at": observed_at,
            "windows": windows,
        }
    return unavailable(
        "codex",
        f"no rate_limits recorded in the {len(rollouts)} most recent rollouts",
        SOURCE,
    )
