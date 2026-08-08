"""Shared board_os helpers — leaf module: never import mcp_tools at module level."""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time

# The full original mcp_tools import surface is kept here (and re-exported by
# the facade) because tests and consumers address these names as module attrs.
from datetime import datetime  # noqa: F401
from pathlib import Path

from board_os._agent_runtime import SYSTEM_SESSION_PREFIX  # noqa: F401
from board_os.config import (  # noqa: F401
    APPETITE_RE,
    KIND_ENUM,
    PRIORITY_ENUM,
    READY_LABEL,
    STATUS_ENUM,
    TASK_ID_FORMAT_RE,
    load_config,
)
from board_os.parser import parse_task  # noqa: F401
from board_os.sync import sync_one  # noqa: F401
from board_os.workflow import (  # noqa: F401
    _format_yaml_scalar_token,
    _has_task_dependencies_table,
    check_wip,
    dependents_of,
    incomplete_dependencies,
    patch_task_frontmatter_scalars,
    transition,
    validate_dependencies_no_cycle,
)
from thinking_os.tools._shared import (  # noqa: F401
    TOKEN_BUDGET_CHARS,
    _budget_size,
    fail,
    ok,
    safe_tool,
)

logger = logging.getLogger("coding_os.board_os.mcp_tools")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


# ---------- Internal helpers ----------


def _project_root() -> Path:
    from thinking_os.database import project_root

    return project_root()


def _current_config():
    try:
        return load_config(_project_root())
    except FileNotFoundError:
        return None


def _slugify(title: str, *, max_len: int = 60) -> str:
    slug = _SLUG_RE.sub("-", title.lower()).strip("-")
    return slug[:max_len] or "untitled"


def _derive_ns_from_git(project_root: Path) -> str:
    # Stable, low-collision uppercase NS from git user.email — the zero-config
    # fallback for the namespaced scheme. 4 base36 chars of a sha1: readable
    # enough as a namespace, collision-rare; docs recommend an explicit prefix.
    import hashlib
    import string
    import subprocess

    try:
        email = subprocess.run(
            ["git", "-C", str(project_root), "config", "user.email"],
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        email = ""
    if not email:
        return ""
    alphabet = string.ascii_uppercase + string.digits
    n = int(hashlib.sha1(email.encode()).hexdigest()[:12], 16)
    out = ""
    for _ in range(4):
        out += alphabet[n % len(alphabet)]
        n //= len(alphabet)
    return ("T" + out[1:]) if not out[0].isalpha() else out


def _namespace_segment(project_root: Path) -> str:
    # '' when no valid namespace → caller degrades to plain TASK-NNN. The scheme
    # gate lives in the dispatcher, not here.
    try:
        from board_os.config import load_config

        cfg = load_config(project_root)
    except Exception as exc:
        logger.debug("namespace segment resolve failed: %s", exc)
        return ""
    ns = (getattr(cfg, "task_id_prefix", "") or "").strip().upper()
    if not ns:
        ns = _derive_ns_from_git(project_root)
    if not re.match(r"^[A-Z][A-Z0-9]{1,7}$", ns):
        return ""
    return f"{ns}-"


def _allocate_with_prefix(conn: sqlite3.Connection, project_root: Path, id_prefix: str) -> str:
    # Atomic per-prefix counter: one INSERT…SELECT computes max(db, fs)+1 for
    # THIS id_prefix AND reserves the row, so SQLite's write lock serializes
    # concurrent local creators. The per-prefix max keeps each namespace an
    # independent sequence (un-synced contributors never collide). id_prefix is
    # validated safe chars (TASK- + uppercase NS + dash) → safe to interpolate.
    substr_start = len(id_prefix) + 1  # 1-indexed SQL SUBSTR past the prefix
    like_pat = id_prefix + "%"

    tasks_dir = project_root / "docs" / "tasks"
    num_re = re.compile(re.escape(id_prefix) + r"(\d+)")
    fs_max = 0
    if tasks_dir.exists():
        for p in tasks_dir.glob(f"{id_prefix}*.md"):
            m = num_re.match(p.name)
            if m:
                fs_max = max(fs_max, int(m.group(1)))

    import time as _t

    sql = f"""
        INSERT INTO tasks (task_id, title, status, file_path, content_hash, mtime)
        SELECT printf('{id_prefix}%03d', MAX(n) + 1),
               '(reserving)', 'icebox',
               printf('docs/tasks/.reserve-{id_prefix}%d.tmp', MAX(n) + 1), '', 0
        FROM (
            SELECT COALESCE(MAX(CAST(SUBSTR(task_id, {substr_start}) AS INTEGER)), 0) AS n
            FROM tasks
            WHERE task_id LIKE ? AND SUBSTR(task_id, {substr_start}) GLOB '[0-9]*'
            UNION ALL SELECT ? AS n
        )
    """

    last_exc: Exception | None = None
    for attempt in range(8):
        try:
            cur = conn.execute(sql, (like_pat, fs_max))
            conn.commit()
            row = conn.execute(
                "SELECT task_id FROM tasks WHERE rowid = ?", (cur.lastrowid,)
            ).fetchone()
            if row and row[0]:
                return str(row[0])
            raise sqlite3.OperationalError("reservation row not found after insert")
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if "locked" in str(exc).lower() and attempt < 7:
                _t.sleep(0.05 * (attempt + 1))
                continue
            raise
    raise last_exc or sqlite3.OperationalError("task id allocation failed")


# Task-id allocator seam (ADR adr-task-id-allocator-seam). Each allocator mints
# the next id behind one interface; the id format stays TASK-<token>, so a future
# `forge` / `service` allocator drops in via the registry with zero migration and
# zero caller change. local + namespaced are offline; both reuse the atomic
# per-prefix counter, differing only in the prefix.
class _LocalAllocator:
    def allocate(self, conn: sqlite3.Connection, project_root: Path) -> str:
        return _allocate_with_prefix(conn, project_root, "TASK-")


class _NamespacedAllocator:
    def allocate(self, conn: sqlite3.Connection, project_root: Path) -> str:
        return _allocate_with_prefix(conn, project_root, "TASK-" + _namespace_segment(project_root))


_TASK_ID_ALLOCATORS: dict[str, object] = {
    "sequential": _LocalAllocator(),
    "local": _LocalAllocator(),
    "namespaced": _NamespacedAllocator(),
}


def _resolve_task_id_allocator(project_root: Path):
    try:
        from board_os.config import load_config

        scheme = getattr(load_config(project_root), "task_id_scheme", "sequential")
    except Exception as exc:
        logger.debug("allocator resolve fell back to local: %s", exc)
        scheme = "sequential"
    return _TASK_ID_ALLOCATORS.get(scheme, _TASK_ID_ALLOCATORS["sequential"])


def _next_task_id(conn: sqlite3.Connection, project_root: Path) -> str:
    return _resolve_task_id_allocator(project_root).allocate(conn, project_root)


# external_ref — optional bidirectional link to a forge issue/PR. Metadata only;
# never the task's canonical id (ADR adr-task-id-allocator-seam). Host is detected
# from the origin remote, so the kernel hardcodes no forge (P2).
def _detect_forge(project_root: Path) -> str:
    import subprocess

    try:
        url = (
            subprocess.run(
                ["git", "-C", str(project_root), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            .stdout.strip()
            .lower()
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if "github.com" in url:
        return "github"
    if "gitlab" in url:
        return "gitlab"
    if "bitbucket" in url:
        return "bitbucket"
    return ""


def _normalize_external_ref(raw: str, project_root: Path) -> str | None:
    # Accepts a bare number, '#42', 'github#42', or a full issue/PR URL → returns
    # '<forge>#<n>' ('!' for a merge/pull request). Forge is taken from the ref
    # when explicit, else detected from origin; None when unparseable.
    import re as _re

    raw = (raw or "").strip()
    if not raw:
        return None
    m = _re.search(
        r"(github|gitlab|bitbucket)\.[^/]+/.+?/(?:issues|pull|-/issues|-/merge_requests|merge_requests)/(\d+)",
        raw,
    )
    if m:
        sep = "!" if "merge_request" in raw or "/pull/" in raw else "#"
        return f"{m.group(1)}{sep}{m.group(2)}"
    m = _re.match(r"^(github|gitlab|bitbucket)\s*([#!])\s*(\d+)$", raw, _re.IGNORECASE)
    if m:
        return f"{m.group(1).lower()}{m.group(2)}{m.group(3)}"
    m = _re.match(r"^([#!]?)(\d+)$", raw)
    if m:
        from . import mcp_tools as _kernel

        forge = _kernel._detect_forge(project_root)
        if not forge:
            return None
        sep = "!" if m.group(1) == "!" else "#"
        return f"{forge}{sep}{m.group(2)}"
    return None


def cos_task_link(conn: sqlite3.Connection, task_id: str, ref: str) -> dict:
    """Link a task to a forge issue/PR via the optional external_ref field."""
    row = conn.execute("SELECT file_path FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if not row:
        return fail("not_found", f"task {task_id} not found")
    project_root = _project_root()
    file_path = project_root / row[0]
    if not file_path.exists():
        return fail("not_found", f"file missing: {file_path}")
    normalized = _normalize_external_ref(ref, project_root)
    if not normalized:
        return fail(
            "validation",
            f"could not parse a forge ref from {ref!r} — use e.g. 42, github#42, or an issue URL",
        )
    patch_task_frontmatter_scalars(file_path, {"external_ref": normalized})
    return ok({"task_id": task_id, "external_ref": normalized, "meta": {"layer": "tasks"}})


def _status_dwell_seconds(now: float, started_at, last_transition_at) -> int | None:
    # Reuse the reclaim derivation (max of started_at and last transition) so
    # dwell, reclaim idle, and SLA staleness share one "last activity" definition.
    last = max(int(started_at or 0), int(last_transition_at or 0))
    if last <= 0:
        return None
    return max(0, int(now - last))


def _humanize_duration(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def _task_card(row: sqlite3.Row | tuple) -> dict:
    started_at = row[11] if len(row) > 11 else None
    completed_at = row[12] if len(row) > 12 else None
    last_transition_at = row[13] if len(row) > 13 else None
    dwell = _status_dwell_seconds(time.time(), started_at, last_transition_at)
    return {
        "id": row[0],
        "title": row[1],
        "swimlane": row[2] or "",
        "kind": row[3] or "",
        "epic": row[4],
        "labels": json.loads(row[5] or "[]"),
        "status": row[6],
        "priority": row[7] or "P2",
        "appetite": row[8] or "1d",
        "agent_session": row[9],
        "last_log_line": _last_log_line(row[10]),
        "completion_evidence": _completion_evidence(row[10]),
        "started_at": started_at,
        "completed_at": completed_at,
        "last_transition_at": last_transition_at,
        "status_dwell_seconds": dwell,
        "status_dwell_human": _humanize_duration(dwell),
    }


def _sla_threshold_seconds(status: str, config) -> int | None:
    if config is None:
        return None
    policy = config.workflow_policy
    hours = {
        "in_progress": policy.in_progress_sla_hours,
        "testing": policy.testing_sla_hours,
        "blocked": policy.blocked_sla_hours,
    }.get(status)
    if hours is not None:
        return hours * 3600 if hours > 0 else None
    if status == "icebox":
        return policy.icebox_stale_days * 86400 if policy.icebox_stale_days > 0 else None
    return None


def _flag_stale(card: dict, config) -> dict:
    # Observability only — never mutates board state. Mutates the card dict in
    # place and returns it so callers can map over a list.
    if card.get("status") == "icebox" and card.get("completion_evidence"):
        # Zombie: the work log claims finished work but the card never left
        # icebox — surface it on every board render, independent of any SLA.
        card["stale"] = True
        card["stale_reason"] = (
            "icebox card carries completion evidence (zombie) — "
            "run cos_task_reconcile, then lifecycle it through complete"
        )
        return card
    threshold = _sla_threshold_seconds(card.get("status", ""), config)
    dwell = card.get("status_dwell_seconds")
    if threshold is not None and dwell is not None and dwell > threshold:
        card["stale"] = True
        card["stale_reason"] = (
            f"{card['status']} {card.get('status_dwell_human')} > SLA "
            f"{_humanize_duration(threshold)}"
        )
    else:
        card["stale"] = False
        card["stale_reason"] = None
    return card


_COMPLETION_EVIDENCE_RE = re.compile(
    r"commit(?:ted)?\s+[0-9a-f]{7,40}"
    r"|implemented\b.{0,40}\bverified"
    r"|verified\b.{0,40}\bimplemented",
    re.IGNORECASE,
)


def _completion_evidence(work_log_json: str | None) -> bool:
    # Heuristic over the cached work-log lines: a linked commit sha or an
    # "implemented … verified" claim is evidence of finished work. Used only
    # for observability (zombie flag + reconcile triage), never for gating.
    if not work_log_json:
        return False
    return bool(_COMPLETION_EVIDENCE_RE.search(str(work_log_json)))


def _last_log_line(work_log_json: str | None) -> str | None:
    if not work_log_json:
        return None
    try:
        lines = json.loads(work_log_json)
    except json.JSONDecodeError:
        return None
    return lines[-1] if lines else None


def _agent_label(agent_session: str | None) -> str:
    # Detection lives in _agent_runtime.detect_agent so cli/board_commands.py and
    # this module share one code path; shell counterpart is core/hooks/cos-env.sh.
    from ._agent_runtime import detect_agent

    return detect_agent(agent_session)


def _resolve_attribution(agent_session: str | None) -> str | None:
    # Without this, task_status_history.agent_session is NULL and the board UI
    # renders the human "H" glyph for agent-driven creates. Reads $COS_SESSION_FILE
    # (set by every adapter via session-context.sh), so the fix is adapter-agnostic.
    from ._agent_runtime import resolve_agent_session

    return resolve_agent_session(agent_session)


def _assign_guard(
    file_path: Path | None,
    agent_session: str | None,
    force: bool,
) -> str | None:
    # Opt-in + backward-compatible: no `assignee:` field → movable by anyone.
    # When set, only that session (or any session of the same agent) may move it;
    # force=True or COS_ASSIGN_OVERRIDE=1 bypasses. Returns an error msg or None.
    if force or os.environ.get("COS_ASSIGN_OVERRIDE") == "1":
        return None
    if file_path is None or not file_path.exists():
        return None
    try:
        head = file_path.read_text(encoding="utf-8")[:2000]
    except OSError:
        return None
    match = re.search(r"^assignee:[ \t]*(.+?)[ \t]*$", head, re.MULTILINE)
    if not match:
        return None
    assignee = match.group(1).strip().strip('"').strip("'")
    if assignee.lower() in ("", "any", "anyone", "unassigned", "null", "~"):
        return None

    from ._agent_runtime import detect_agent

    mover = (agent_session or "").strip()
    if assignee == mover:
        return None
    mover_agent = detect_agent(mover)
    if mover_agent != "agent" and detect_agent(assignee) == mover_agent:
        return None
    return (
        f"task is assigned to {assignee!r} — current mover is "
        f"{mover or 'unattributed'!r}. Re-assign the task (edit its "
        "`assignee:` frontmatter) or override with force=True / "
        "COS_ASSIGN_OVERRIDE=1."
    )


_BOARD_SELECT = (
    "SELECT task_id, title, swimlane, kind, epic, labels_json, "
    "       status, priority, appetite, agent_session, work_log_last_5, "
    "       started_at, completed_at, "
    # last_transition_at (row[13]): the most recent status-change time from
    # history. Correlated subquery keeps the column appended LAST so existing
    # positional readers (retro r[11]/r[12]) are unaffected. Powers the board
    # time dimension (status_dwell_seconds) — RC5 of the 2026-06-05
    # task-lifecycle review (TASK-210).
    "       (SELECT MAX(h.transitioned_at) FROM task_status_history h "
    "        WHERE h.task_id = tasks.task_id) AS last_transition_at "
    "FROM tasks"
)


# ---------- cos_task_create ----------


def _commits_referencing(task_id: str, project_root: Path) -> int | None:
    # None = unverifiable (no git / error) so callers fail SAFE — treat as "has
    # evidence", never auto-reclaim on a signal we couldn't check. Trailing
    # non-digit boundary stops TASK-215 also matching TASK-2155.
    import subprocess

    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(project_root),
                "log",
                "--all",
                "-E",
                f"--max-count={_COMMIT_SCAN_CAP}",
                "--grep",
                f"{task_id}([^0-9]|$)",
                "--oneline",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return sum(1 for line in out.stdout.splitlines() if line.strip())


# Cap on how many matching commits git enumerates per scan — bounds the history
# walk at 1M+ commits. Reconciliation only needs "0 vs >0" evidence, so a count
# capped at this value is sufficient (and reported as "at least N"). TASK-227.
_COMMIT_SCAN_CAP = 500
# Cap on a single reclaim/reconcile sweep — the rest drains on the next run.
_STRANDED_SCAN_LIMIT = 1000


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        is not None
    )


def _actor_view(agent_session: str | None) -> dict:
    from ._agent_runtime import detect_agent

    if not agent_session:
        return {"type": "human", "id": "human", "label": "human"}
    label = detect_agent(agent_session)
    if label in ("human", "system"):
        actor_type = label
    else:
        actor_type = "agent"
    return {
        "type": actor_type,
        "id": agent_session,
        "label": label,
    }


def _parse_since(since: str) -> float:
    m = re.match(r"^(\d+)([mhdw])$", since)
    if not m:
        return 24.0
    n, unit = int(m.group(1)), m.group(2)
    return {"m": n / 60.0, "h": float(n), "d": n * 24.0, "w": n * 24.0 * 7.0}[unit]


# ---------- Cycle validation tool (exposed for hooks) ----------


def check_cycle(conn: sqlite3.Connection, task_id: str, new_deps: list[str]) -> list[str]:
    """Thin passthrough to workflow.validate_dependencies_no_cycle."""
    return validate_dependencies_no_cycle(conn, task_id, new_deps)
