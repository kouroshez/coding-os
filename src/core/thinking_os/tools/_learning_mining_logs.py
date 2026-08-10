"""Mine lessons from OUTSIDE the database: the hook log and git history.

Split from _learning_mining because the signal source is the axis that changes:
those lessons come from the backtrack table, these from files on disk whose
format is owned by the hook runner and by git.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger("thinking_os.learning")

try:  # package import
    from ._learning_mining import (
        _FRICTION_MIN_OCCURRENCES,
        _LESSON_WINDOW_DAYS,
        _LONGHEX_RE,
        _NONWORD_RE,
        _TASKID_RE,
        _clean_failure_text,
        _mint_friction_lesson,
    )
    from ._learning_store import _derive_project_root, _upsert_pattern
except ImportError:  # flat import
    from _learning_mining import (  # type: ignore[no-redef]
        _FRICTION_MIN_OCCURRENCES,
        _LESSON_WINDOW_DAYS,
        _LONGHEX_RE,
        _NONWORD_RE,
        _TASKID_RE,
        _clean_failure_text,
        _mint_friction_lesson,
    )
    from _learning_store import _derive_project_root, _upsert_pattern  # type: ignore[no-redef]


# A hook-log block line: "[<ts>] [<hook>] [block] … rule=<rule> …".
_BLOCK_LINE_RE = re.compile(
    r"^\[(?P<ts>[^\]]+)\]\s+\[(?P<hook>[^\]]+)\]\s+\[block\]\s*(?P<rest>.*)$"
)
_BLOCK_RULE_RE = re.compile(r"\brule=(\S+)")
# Recency window shared by both friction miners: a failure/block only counts as
# a recurring lesson if it recurs within this window. Old/resolved/renamed-rule
# failures age out (stop being re-confirmed) and decay instead of persisting.


def _hook_log_paths(conn: sqlite3.Connection) -> list[Path]:
    # Most-durable first: block-only log (survives the main log's cap) then the
    # main hook log. Env overrides win; otherwise derive from the project root.
    paths: list[Path] = []
    blk = os.environ.get("COS_HOOK_BLOCK_LOG")
    main = os.environ.get("COS_HOOK_LOG")
    if blk:
        paths.append(Path(blk))
    if main:
        paths.append(Path(main))
    if not paths:
        root = _derive_project_root(conn)
        if root:
            paths.append(root / ".coding-os" / ".hook-blocks.log")
            paths.append(root / ".coding-os" / ".hooks.log")
    return paths


def _mine_hook_block_lessons(
    conn: sqlite3.Connection,
    *,
    min_occurrences: int = 3,
    distill_state: dict | None = None,
) -> list[dict]:
    # Hook BLOCKs never reach the observations table on Claude (no PostToolUseFailure)
    # but are in the append-only hook log — mine them there. Fire-and-forget.
    floor = max(1, min(min_occurrences, _FRICTION_MIN_OCCURRENCES))
    # Single source, not a merge: every block is mirrored to both logs, so the
    # block-only log is a strict superset of the main log's surviving blocks.
    # Read the first existing, non-empty candidate (block log preferred) — this
    # avoids double-counting a mirrored block while preserving genuine repeats.
    log_path = None
    for lp in _hook_log_paths(conn):
        try:
            if lp.exists() and lp.stat().st_size > 0:
                log_path = lp
                break
        except OSError:
            continue
    if log_path is None:
        return []
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        logger.debug("hook-block mining skipped (read %s): %s", log_path, exc)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=_LESSON_WINDOW_DAYS)
    clusters: dict[str, dict] = {}
    for line in lines:
        match = _BLOCK_LINE_RE.match(line)
        if not match:
            continue
        try:
            ts = datetime.fromisoformat(match.group("ts").replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts < cutoff:
                continue
        except ValueError:
            continue  # unparseable timestamp — skip, don't guess
        hook = match.group("hook").strip()
        rest = match.group("rest") or ""
        rule_match = _BLOCK_RULE_RE.search(rest)
        rule = rule_match.group(1) if rule_match else ""
        key = f"{hook}:{rule}"
        cluster = clusters.setdefault(key, {"count": 0, "hook": hook, "rule": rule, "samples": []})
        cluster["count"] += 1
        if rest and len(cluster["samples"]) < 3:
            cluster["samples"].append(rest)

    lessons: list[dict] = []
    for key, cluster in clusters.items():
        if cluster["count"] < floor:
            continue
        subject = f"{cluster['hook']} — {cluster['rule']}" if cluster["rule"] else cluster["hook"]
        pattern_text = (
            f"Recurring block ({cluster['count']} occurrences): {subject} "
            f"→ satisfy the blocked rule before retrying the action"
        )
        lessons.append(
            _mint_friction_lesson(
                conn,
                kind="hook_block",
                cluster_key=key,
                count=cluster["count"],
                template_text=pattern_text,
                hook=cluster["hook"],
                rule=cluster["rule"],
                samples=cluster["samples"],
                distill_state=distill_state,
                concepts=json.dumps(["lesson", "hook_block", cluster["hook"]]),
            )
        )
    return lessons


# A Conventional-Commit subject whose type means "something was wrong → fixed":
# fix:/revert: (optional scope, optional !). The subject IS a recorded lesson.
_FIX_COMMIT_RE = re.compile(
    r"^(?P<type>fix|revert)(?:\([^)]*\))?!?:\s*(?P<subject>.+)$", re.IGNORECASE
)

# A one-off `fix:` subject is terse shorthand with no reusable rule — noise.
# Only a fix that RECURS this many times is a systemic-gap signal. Reverts are
# minted at any count (a revert is itself a recorded mistake). See §5 of the doc.
_COMMIT_FIX_MIN_RECURRENCE = 3


def _commit_subject_key(subject: str) -> str:
    s = _TASKID_RE.sub("TASK-N", subject)
    s = _LONGHEX_RE.sub("<hash>", s)
    s = re.sub(r"\d+", "N", s.lower())
    words = [w for w in _NONWORD_RE.split(s) if w]
    return " ".join(words[:8])


def _mine_commit_lessons(conn: sqlite3.Connection, *, min_occurrences: int = 3) -> list[dict]:
    # A fix:/revert: commit IS a recorded "something was wrong → correction".
    # Read-only git log, bounded, no-op outside a work-tree.
    # Contract: docs/engineering/learning-extraction.md §5.
    import subprocess

    root = _derive_project_root(conn)
    if root is None:
        return []
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "log",
                f"--since={_LESSON_WINDOW_DAYS} days ago",
                "--max-count=2000",
                "--no-merges",
                "--pretty=format:%s",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("commit mining skipped: %s", exc)
        return []
    if proc.returncode != 0:
        return []

    clusters: dict[str, dict] = {}
    for line in proc.stdout.splitlines():
        match = _FIX_COMMIT_RE.match(line.strip())
        if not match:
            continue
        subject = match.group("subject").strip()
        key = _commit_subject_key(subject)
        if not key:
            continue
        cluster = clusters.setdefault(key, {"count": 0, "subject": subject, "revert": False})
        cluster["count"] += 1
        if match.group("type").lower() == "revert":
            cluster["revert"] = True

    lessons: list[dict] = []
    for cluster in clusters.values():
        is_revert = cluster["revert"]
        subject = _clean_failure_text(cluster["subject"])
        if is_revert:
            # A revert is a recorded "we shipped this and undid it" — real signal.
            pattern_text = (
                f"Reverted before: {subject} → reconsider before re-introducing this change."
            )
        elif cluster["count"] >= _COMMIT_FIX_MIN_RECURRENCE:
            # The RECURRENCE is the signal (same thing keeps breaking), not the
            # subject itself. "(N occurrences)" so _pattern_identity dedups it.
            pattern_text = (
                f"Fixed repeatedly ({cluster['count']} occurrences): {subject} "
                f"→ address the root cause, not the symptom."
            )
        else:
            continue  # one-off / 2x fix subject — no reusable lesson, drop it
        lessons.append(
            _upsert_pattern(
                conn,
                pattern=pattern_text,
                memory_type="lesson",
                domain=None,
                source="commit",
                confidence=min(0.85, 0.4 + cluster["count"] / 10.0),
                concepts=json.dumps(["lesson", "commit", "revert" if is_revert else "fix"]),
            )
        )
    return lessons
