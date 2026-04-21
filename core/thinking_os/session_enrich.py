#!/usr/bin/env python3
"""
Thinking OS — Session enrichment.

Called by session-end.sh to populate semantic fields in session_summaries,
record agent metrics, build concept_link edges, and trigger periodic decay.
Runs as fire-and-forget (never errors visibly).

Usage:
    python3 core/thinking_os/session_enrich.py <session_id> <active_task> <db_path>
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 4:
        sys.exit(0)

    session_id, task_id, db_path = sys.argv[1], sys.argv[2], sys.argv[3]
    if not session_id or not os.path.exists(db_path):
        sys.exit(0)

    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")

    gate_path = Path(os.environ.get("COS_STATE_DIR", ".coding-os") + "/.thinking-os-gate")

    # ── Step 1: Populate semantic fields in session_summaries ──
    try:
        request_parts: list[str] = []
        if gate_path.exists():
            content = gate_path.read_text().strip().split()
            if len(content) >= 3:
                request_parts.append(f"{content[1]} {content[2]}")
        if task_id:
            request_parts.append(f"Task: {task_id}")
        request_str = " | ".join(request_parts) if request_parts else None

        obs_rows = conn.execute(
            "SELECT files_modified, narrative FROM observations "
            "WHERE session_id = ? AND files_modified IS NOT NULL",
            (session_id,),
        ).fetchall()

        domain_counts: dict[str, int] = {}
        for r in obs_rows:
            f = r["files_modified"] or ""
            if "backend/" in f:
                domain_counts["backend"] = domain_counts.get("backend", 0) + 1
            elif "frontend/" in f:
                domain_counts["frontend"] = domain_counts.get("frontend", 0) + 1
            elif "docs/" in f:
                domain_counts["docs"] = domain_counts.get("docs", 0) + 1
            else:
                domain_counts["other"] = domain_counts.get("other", 0) + 1

        completed = ", ".join(
            f"{c} {d} files"
            for d, c in sorted(domain_counts.items(), key=lambda x: -x[1])
        )
        if not completed:
            completed = None

        learned = None
        try:
            edge_rows = conn.execute(
                "SELECT source, target, weight FROM concept_graph "
                "WHERE evidence = ? AND edge_type = 'co_edit' "
                "ORDER BY weight DESC LIMIT 3",
                (session_id,),
            ).fetchall()
            if edge_rows:
                pairs = [
                    f"{Path(r['source']).name} <-> {Path(r['target']).name}"
                    for r in edge_rows
                ]
                learned = "Co-edited: " + "; ".join(pairs)
        except Exception:
            pass

        conn.execute(
            "UPDATE session_summaries SET "
            "request = COALESCE(request, ?), "
            "completed = COALESCE(completed, ?), "
            "learned = COALESCE(learned, ?) "
            "WHERE session_id = ? AND (request IS NULL OR completed IS NULL)",
            (request_str, completed, learned, session_id),
        )
        conn.commit()
    except Exception:
        pass

    # ── Step 2: Auto-record agent metric ──
    try:
        # Detect domain by majority vote across ALL observations (not just first)
        domain_counts: dict[str, int] = {}
        all_obs = conn.execute(
            "SELECT files_modified FROM observations "
            "WHERE session_id = ? AND files_modified IS NOT NULL",
            (session_id,),
        ).fetchall()
        for obs in all_obs:
            f = (obs["files_modified"] or "").lower()
            if "backend/" in f:
                domain_counts["BACKEND"] = domain_counts.get("BACKEND", 0) + 1
            elif "frontend/" in f:
                domain_counts["FRONTEND"] = domain_counts.get("FRONTEND", 0) + 1
            elif "docs/" in f:
                domain_counts["DOCS"] = domain_counts.get("DOCS", 0) + 1
            else:
                domain_counts["INFRA"] = domain_counts.get("INFRA", 0) + 1
        domain = max(domain_counts, key=domain_counts.get) if domain_counts else "INFRA"

        complexity = "UNKNOWN"
        if gate_path.exists():
            parts = gate_path.read_text().strip().split()
            if len(parts) >= 2:
                complexity = (
                    parts[1]
                    if not parts[0].startswith("ses-")
                    else (parts[1] if len(parts) >= 2 else "UNKNOWN")
                )

        duration_ms = 0
        sid_path = Path(os.environ.get("COS_STATE_DIR", ".coding-os") + "/session-id")
        if sid_path.exists():
            age_sec = (
                datetime.now(tz=timezone.utc).timestamp() - sid_path.stat().st_mtime
            )
            duration_ms = int(age_sec * 1000)

        conn.execute(
            "INSERT INTO agent_metrics "
            "(task_id, agent_type, model, duration_ms, domain, complexity, outcome) "
            "VALUES (?, 'session', 'opus', ?, ?, ?, 'success')",
            (task_id or None, duration_ms, domain, complexity),
        )
        conn.commit()
    except Exception:
        pass

    # ── Step 4: Build concept_link edges from observations ──
    try:
        concept_rows = conn.execute(
            "SELECT concepts FROM observations "
            "WHERE session_id = ? AND concepts IS NOT NULL AND concepts != '[]'",
            (session_id,),
        ).fetchall()

        pair_counts: dict[tuple[str, str], int] = {}
        for row in concept_rows:
            try:
                concepts = json.loads(row["concepts"])
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(concepts, list) or len(concepts) < 2:
                continue
            for i, c1 in enumerate(concepts):
                for c2 in concepts[i + 1 :]:
                    pair = tuple(sorted([str(c1).lower(), str(c2).lower()]))
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1

        for (c1, c2), count in pair_counts.items():
            if count < 2:
                continue
            weight = min(5.0, count * 0.3)
            conn.execute(
                "INSERT INTO concept_graph (source, target, edge_type, weight, evidence) "
                "VALUES (?, ?, 'concept_link', ?, ?) "
                "ON CONFLICT(source, target, edge_type) DO UPDATE SET "
                "weight = MIN(5.0, weight + 0.1), updated_at = CURRENT_TIMESTAMP",
                (c1, c2, weight, session_id),
            )
        conn.commit()
    except Exception:
        pass

    # ── Step 6: Run decay if >7 days since last run ──
    try:
        decay_marker = Path(os.environ.get("COS_STATE_DIR", ".coding-os") + "/.last-decay")
        run_decay = False
        if not decay_marker.exists():
            run_decay = True
        else:
            age_days = (
                datetime.now(tz=timezone.utc).timestamp()
                - decay_marker.stat().st_mtime
            ) / 86400
            if age_days > 7:
                run_decay = True

        if run_decay:
            sys.path.insert(0, str(Path(db_path).resolve().parent))
            from decay import run_decay as do_decay

            do_decay(db_path)
            decay_marker.write_text(datetime.now(tz=timezone.utc).isoformat())
    except Exception:
        pass

    conn.close()


if __name__ == "__main__":
    main()
