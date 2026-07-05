#!/usr/bin/env python3
"""Thinking OS — detached per-session observer worker (item A, root fix).

Spawned by session_enrich.py at Stop via setsid Popen so the ONE budget-capped
LLM enrichment dispatch outlives the hook's 2s bound and never blocks it. The
worker collects this session's mechanical `changelog` observations, dispatches
once through distill.observe_session (P8-safe — the dispatch goes through the
adapter dispatcher, core never imports an adapter SDK), promotes each
signal-bearing row off `changelog` with a distilled narrative + concepts (all
text through redact_secrets/scrub_username; file bodies are never read), and
fills session_summaries via apply_session_facts. Fire-and-forget: exits 0 on
any failure. Idempotent by construction — an enriched row leaves `changelog`,
so a re-run finds nothing to do.

Usage: python3 session_observe_worker.py <session_id> <db_path>
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from distill import enrich_enabled, observe_session  # noqa: E402
from sanitizer import redact_secrets, scrub_username  # noqa: E402
from session_enrich import apply_session_facts  # noqa: E402

_TOP_N = 12  # cap changelog rows enriched per session — bounds cost and keeps focus


def _collect(conn: sqlite3.Connection, session_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, title, tool_name, files_modified FROM observations "
        "WHERE session_id = ? AND memory_type = 'changelog' "
        "ORDER BY COALESCE(impact_score, 0) DESC, id DESC LIMIT ?",
        (session_id, _TOP_N),
    ).fetchall()


def _build_evidence(session_id: str, rows: list[sqlite3.Row]) -> dict:
    return {
        "session_id": session_id,
        "observations": [
            {
                "id": r["id"],
                "title": r["title"] or "",
                "tool": r["tool_name"] or "",
                "files": scrub_username((r["files_modified"] or "")[:300]),
            }
            for r in rows
        ],
    }


def enrich_session(conn: sqlite3.Connection, session_id: str) -> int:
    """Enrich this session's changelog rows via one dispatch; return rows promoted."""
    rows = _collect(conn, session_id)
    if not rows:
        return 0

    enrichment = observe_session(_build_evidence(session_id, rows))
    if enrichment is None:
        return 0

    valid_ids = {r["id"] for r in rows}
    promoted = 0
    for obs in enrichment.observations:
        if not obs.has_signal or obs.observation_id not in valid_ids:
            continue
        narrative, _ = redact_secrets((obs.narrative or "").strip())
        narrative = scrub_username(narrative)[:400]
        if not narrative:
            continue
        concepts = json.dumps([str(c)[:40] for c in obs.concepts[:8]], ensure_ascii=False)
        cur = conn.execute(
            # Clear expires_at: an enriched discovery row is durable, not on the
            # changelog TTL, so decay must not GC it.
            "UPDATE observations SET narrative = ?, concepts = ?, memory_type = 'discovery', "
            "expires_at = NULL WHERE id = ? AND memory_type = 'changelog'",
            (narrative, concepts, obs.observation_id),
        )
        promoted += cur.rowcount
    conn.commit()

    apply_session_facts(conn, session_id, enrichment.summary)
    return promoted


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(0)
    session_id, db_path = sys.argv[1], sys.argv[2]
    if not session_id or not os.path.exists(db_path) or not enrich_enabled():
        sys.exit(0)
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        enrich_session(conn, session_id)
        conn.close()
    except Exception as exc:  # fire-and-forget (Rule 6)
        print(f"session_observe_worker.py: enrichment skipped: {exc}", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
