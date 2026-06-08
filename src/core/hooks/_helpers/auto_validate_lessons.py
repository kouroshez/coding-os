#!/usr/bin/env python3
"""Auto-validate surfaced lessons at task-done — closes the learn->apply->confirm
loop without the agent volunteering cos_learn_validate (B1).

Called by remind-learn-validate.sh on `cos task-done`. Reads the per-panel
.learn-suggestions (surfaced pattern ids), checks whether each lesson's failure
RECURRED in this session's friction observations, and validates accordingly:
recurred -> was_helpful=False; no recurrence -> was_helpful=True. The existing
1h throttle in learn_validate makes a manual agent validation win over the auto
one. Fire-and-forget: any error exits 0 and leaves the reminder intact.

USAGE: python3 auto_validate_lessons.py <session_id> <db_path> <suggestions_file>
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_THINKING_OS = Path(__file__).resolve().parents[1] / "thinking_os"
if _THINKING_OS.is_dir() and str(_THINKING_OS) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS))

_NUM_RE = re.compile(r"\d+")
_NONWORD_RE = re.compile(r"[^a-z0-9<>_.-]+")


def _normalize_full(text: str) -> str:
    """Char-normalise (lowercase, digits->N, non-word->space) — same rules the
    friction cluster key uses, but keeping every word so a failure key can be
    substring-matched against a lesson's full text."""
    return " ".join(_NONWORD_RE.split(_NUM_RE.sub("N", (text or "").lower())))


def _load_surfaced(path: Path) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "\t" not in line:
            continue
        pid_s, text = line.split("\t", 1)
        try:
            out.append((int(pid_s), text))
        except ValueError:
            continue
    return out


def auto_validate(session_id: str, db_path: str, suggestions_file: str) -> dict:
    sf = Path(suggestions_file)
    if not session_id or not db_path or not sf.exists():
        return {"status": "skipped"}
    surfaced = _load_surfaced(sf)
    if not surfaced:
        return {"status": "no_suggestions"}

    from database import get_connection
    from tools.learning import _clean_failure_text, _failure_cluster_key, learn_validate

    # Only failures recorded AT/AFTER the recall (suggestions file mtime) count.
    recall_at = datetime.fromtimestamp(sf.stat().st_mtime, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT narrative, title FROM observations "
            "WHERE session_id = ? AND memory_type IN ('hook_block', 'error') "
            "  AND created_at >= ?",
            (session_id, recall_at),
        ).fetchall()
        failure_keys = []
        for r in rows:
            d = dict(r)
            key = _failure_cluster_key(_clean_failure_text(d["narrative"] or d["title"] or ""))
            if key:
                failure_keys.append(key)

        helpful = unhelpful = 0
        for pid, text in surfaced:
            lesson_norm = _normalize_full(text)
            recurred = any(key in lesson_norm for key in failure_keys)
            learn_validate(conn, pattern_id=pid, was_helpful=not recurred)
            if recurred:
                unhelpful += 1
            else:
                helpful += 1
        return {"status": "ok", "surfaced": len(surfaced), "helpful": helpful, "unhelpful": unhelpful}
    finally:
        conn.close()


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        return 0
    try:
        result = auto_validate(argv[1], argv[2], argv[3])
    except Exception:  # fire-and-forget — never break the task-done hook
        return 0
    if result.get("status") == "ok":
        print(
            f"auto-validated {result['surfaced']} surfaced lesson(s): "
            f"{result['helpful']} helpful, {result['unhelpful']} not"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
