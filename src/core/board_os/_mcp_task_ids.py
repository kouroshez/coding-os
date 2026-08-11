"""Task-id allocation — the namespace derivation and the atomic counter behind it.

Minting an id is the one board operation that must serialize across concurrent
creators, and its scheme is a documented seam (ADR adr-task-id-allocator-seam);
neither concern belongs in the same file as card shaping or forge links. A leaf:
it imports no other board_os MCP module.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

logger = logging.getLogger("coding_os.board_os.mcp_tools")


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
