#!/usr/bin/env python3
"""
Thinking OS — Session startup display.

Called by session-context.sh on startup to show memory stats and
previous session context. Runs as fire-and-forget (never errors visibly).

Usage:
    python3 core/thinking_os/session_startup.py <db_path>
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(0)

    db_path = sys.argv[1]
    if not Path(db_path).exists():
        sys.exit(0)

    try:
        conn = sqlite3.connect(db_path, timeout=2)
        conn.row_factory = sqlite3.Row

        obs = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        pats = conn.execute("SELECT COUNT(*) FROM learned_patterns").fetchone()[0]
        trusted = conn.execute(
            "SELECT COUNT(*) FROM learned_patterns "
            "WHERE confidence >= 0.7 AND times_validated >= 3 "
            "AND COALESCE(memory_type, '') != 'stat' "
            "AND COALESCE(promoted_to, '') != 'archived'"
        ).fetchone()[0]

        digest_path = Path(db_path).parent / "digest.md"
        digest_tokens = 0
        if digest_path.exists():
            digest_tokens = len(digest_path.read_text(encoding="utf-8", errors="ignore")) // 4

        print(
            f"[Memory] {obs} obs, {pats} patterns ({trusted} trusted) | "
            f"digest ~{digest_tokens} tok injected at start"
        )

        # Episode chaining: show previous session context
        try:
            prev = conn.execute(
                "SELECT learned, next_steps, task_id FROM session_summaries "
                "WHERE learned IS NOT NULL OR next_steps IS NOT NULL "
                "ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if prev and (prev["learned"] or prev["next_steps"]):
                print("[Previous Session]")
                if prev["task_id"]:
                    print(f"  Task: {prev['task_id']}")
                if prev["learned"]:
                    print(f"  Learned: {prev['learned'][:150]}")
                if prev["next_steps"]:
                    print(f"  Next steps: {prev['next_steps'][:150]}")
        except Exception:
            pass  # pre-v4 columns may not exist

        conn.close()
    except Exception:
        pass  # fire-and-forget


if __name__ == "__main__":
    main()
