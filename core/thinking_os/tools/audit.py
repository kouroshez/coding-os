"""
Coding OS — MCP audit-log tools (Phase O).

PURPOSE:      Append-only doc edit + decision-history log. Every doc
              change records: who, when, what changed, why, and (when
              reverting) which prior decision is being superseded.
INPUT:        See per-tool docstrings.
OUTPUT:       JSON envelope via ok()/fail() (see _shared.safe_tool).
DEPENDENCIES: sqlite3 only. Triggers on doc_audit_trail enforce
              append-only at the DB layer.
NOTES:        Backed by migration v21 (db.py::_migrate_v21_doc_audit_trail).
              Reverts are modeled as a NEW row with action='reverted' +
              supersedes_id pointing at the decision being undone — never
              as a row rewrite. The hub UI reads this table via
              cos_audit_log_query for human review.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from typing import Optional

logger = logging.getLogger("thinking_os.audit")

VALID_ACTIONS = {"created", "updated", "deleted", "reverted", "moved", "renamed"}
MAX_LIMIT = 200
DEFAULT_LIMIT = 25


def _content_hash(text: Optional[str]) -> Optional[str]:
    """SHA-256 truncated to 16 hex chars — enough to detect drift,
    short enough to not bloat the row."""
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------------------

def audit_log_record(
    conn: sqlite3.Connection,
    *,
    doc_path: str,
    action: str,
    session_id: Optional[str] = None,
    agent: Optional[str] = None,
    old_frontmatter: Optional[str] = None,
    new_frontmatter: Optional[str] = None,
    old_content: Optional[str] = None,
    new_content: Optional[str] = None,
    reason: Optional[str] = None,
    supersedes_id: Optional[int] = None,
) -> dict:
    """Append a doc audit row.

    Args:
        doc_path: Repo-relative path under docs/ (e.g.
            "docs/architecture/adr/ADR-014-storage.md").
        action: One of: created, updated, deleted, reverted, moved, renamed.
        session_id: Agent session id (file: $COS_AGENT_DIR/session-id).
        agent: claude / codex / cursor / human.
        old_frontmatter: JSON dump (or raw HTML comment) of pre-edit header.
        new_frontmatter: JSON dump of post-edit header.
        old_content: Pre-edit body (used only for hashing; not stored verbatim).
        new_content: Post-edit body (likewise).
        reason: Free-text rationale. Strongly encouraged for
            updated/reverted/deleted actions.
        supersedes_id: When action='reverted', the doc_audit_trail.id of the
            decision being undone. Optional otherwise.

    Returns:
        Dict with `id` of the inserted row.
    """
    if action not in VALID_ACTIONS:
        raise ValueError(
            f"Invalid action '{action}'. Must be one of: {sorted(VALID_ACTIONS)}"
        )
    if not doc_path or not doc_path.strip():
        raise ValueError("doc_path is required")

    cursor = conn.execute(
        "INSERT INTO doc_audit_trail "
        "(doc_path, session_id, agent, action, old_frontmatter, new_frontmatter, "
        " old_content_hash, new_content_hash, reason, supersedes_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            doc_path,
            session_id,
            agent,
            action,
            old_frontmatter,
            new_frontmatter,
            _content_hash(old_content),
            _content_hash(new_content),
            reason,
            supersedes_id,
        ),
    )

    # Stage-1 RAG: deleting / reverting a doc must remove its chunks
    # from default retrieval. We don't drop rows (audit needs the
    # historical hashes); instead flip is_active=0 on document_chunks
    # for the same source_path. cos_doc_search hides inactive by default.
    chunks_deactivated = 0
    if action in ("deleted", "reverted"):
        try:
            cur2 = conn.execute(
                "UPDATE document_chunks SET is_active = 0 WHERE source_path = ?",
                (doc_path,),
            )
            chunks_deactivated = cur2.rowcount or 0
        except sqlite3.OperationalError as exc:
            # Pre-v22 DBs lack the is_active column; tolerate gracefully.
            logger.debug("is_active flip skipped (pre-v22 schema?): %s", exc)

    conn.commit()
    return {
        "id": cursor.lastrowid,
        "doc_path": doc_path,
        "action": action,
        "chunks_deactivated": chunks_deactivated,
    }


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

def audit_log_query(
    conn: sqlite3.Connection,
    *,
    doc_path: Optional[str] = None,
    session_id: Optional[str] = None,
    agent: Optional[str] = None,
    action: Optional[str] = None,
    only_reverted: bool = False,
    since_iso: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """Query the doc audit trail.

    Args:
        doc_path: Filter to a single document (exact match).
        session_id: Filter to one agent session.
        agent: Filter by agent (claude/codex/cursor/human).
        action: Filter by action.
        only_reverted: Show only rows that were superseded by a later revert,
            i.e. rows whose `id` appears as `supersedes_id` somewhere.
        since_iso: ISO date/time inclusive lower bound.
        limit: Max rows (1..200, default 25). Most-recent first.

    Returns:
        Dict with `total`, `rows` (oldest→newest within page).
    """
    if action is not None and action not in VALID_ACTIONS:
        raise ValueError(
            f"Invalid action '{action}'. Must be one of: {sorted(VALID_ACTIONS)}"
        )
    limit = max(1, min(MAX_LIMIT, int(limit)))

    where: list[str] = []
    params: list = []

    if doc_path is not None:
        where.append("doc_path = ?")
        params.append(doc_path)
    if session_id is not None:
        where.append("session_id = ?")
        params.append(session_id)
    if agent is not None:
        where.append("agent = ?")
        params.append(agent)
    if action is not None:
        where.append("action = ?")
        params.append(action)
    if since_iso is not None:
        where.append("created_at >= ?")
        params.append(since_iso)
    if only_reverted:
        where.append(
            "id IN (SELECT supersedes_id FROM doc_audit_trail "
            "WHERE supersedes_id IS NOT NULL)"
        )

    where_sql = " AND ".join(where) if where else "1=1"

    total = conn.execute(
        f"SELECT COUNT(*) FROM doc_audit_trail WHERE {where_sql}",  # noqa: S608
        params,
    ).fetchone()[0]

    rows = conn.execute(
        f"SELECT id, doc_path, session_id, agent, action, "  # noqa: S608
        f"       old_frontmatter, new_frontmatter, "
        f"       old_content_hash, new_content_hash, "
        f"       reason, supersedes_id, created_at "
        f"FROM doc_audit_trail WHERE {where_sql} "
        f"ORDER BY created_at DESC, id DESC LIMIT ?",
        params + [limit],
    ).fetchall()

    return {
        "total": total,
        "count": len(rows),
        "rows": [dict(r) for r in rows],
    }


# ---------------------------------------------------------------------------
# Per-doc timeline (convenience)
# ---------------------------------------------------------------------------

def audit_log_timeline(
    conn: sqlite3.Connection,
    *,
    doc_path: str,
    limit: int = 50,
) -> dict:
    """Return the chronological history of a single doc, oldest→newest.

    Used by hub UI to render a "decision history" panel beside the doc.
    """
    if not doc_path or not doc_path.strip():
        raise ValueError("doc_path is required")
    limit = max(1, min(MAX_LIMIT, int(limit)))

    rows = conn.execute(
        "SELECT id, action, agent, session_id, reason, supersedes_id, "
        "       old_content_hash, new_content_hash, created_at "
        "FROM doc_audit_trail WHERE doc_path = ? "
        "ORDER BY created_at ASC, id ASC LIMIT ?",
        (doc_path, limit),
    ).fetchall()

    return {
        "doc_path": doc_path,
        "count": len(rows),
        "rows": [dict(r) for r in rows],
    }
