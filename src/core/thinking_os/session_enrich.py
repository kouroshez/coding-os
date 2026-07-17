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
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gate_marker import read_gate_file


def _has_session_signal(facts) -> bool:
    if facts is None or not getattr(facts, "has_signal", False):
        return False
    return bool((getattr(facts, "learned", "") or "").strip())


def apply_session_facts(conn, session_id, facts) -> bool:
    if not _has_session_signal(facts):
        return False
    cur = conn.execute(
        "UPDATE session_summaries SET "
        "investigated = COALESCE(investigated, ?), "
        "learned = COALESCE(learned, ?), "
        "next_steps = COALESCE(next_steps, ?) "
        "WHERE session_id = ?",
        (
            (facts.investigated or "").strip() or None,
            (facts.learned or "").strip() or None,
            (facts.next_steps or "").strip() or None,
            session_id,
        ),
    )
    conn.commit()
    return cur.rowcount > 0


def _maybe_spawn_observer(session_id: str, db_path: str, complexity: str) -> None:
    # Item A: hand the slow per-session LLM enrichment to a detached worker that
    # outlives this hook's 2s bound (Popen returns immediately; setsid keeps the
    # child alive past the kill). Default OFF; scoped to COMPLICATED/COMPLEX
    # sessions to bound token cost. The env fast-path mirrors distill.enrich_enabled
    # so the disabled default returns before paying distill's cold import.
    if os.environ.get("COS_ENRICH_LLM", "0") != "1":
        return
    if complexity not in ("COMPLICATED", "COMPLEX"):
        return
    try:
        worker = Path(__file__).resolve().parent / "session_observe_worker.py"
        if not worker.exists():
            return
        subprocess.Popen(
            [sys.executable, str(worker), session_id, db_path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:  # fire-and-forget (Rule 6)
        print(f"session_enrich.py: observer spawn skipped: {exc}", file=sys.stderr)


def main() -> None:
    if len(sys.argv) < 4:
        sys.exit(0)

    session_id, task_id, db_path = sys.argv[1], sys.argv[2], sys.argv[3]
    if not session_id or not os.path.exists(db_path):
        sys.exit(0)

    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")

    # The gate is per-panel (COS_PER_PANEL_FILES); reuse record_outcome's
    # canonical panel-first resolver rather than a second COS_STATE_DIR-only
    # path — the divergent path left complexity UNKNOWN on every session.
    complexity, dimensions = read_gate_file()

    # Spawn the detached enrichment worker first, so it is already setsid-detached
    # before any slow step below risks tripping this hook's 2s kill.
    _maybe_spawn_observer(session_id, db_path, complexity)

    # ── Step 1: Populate semantic fields in session_summaries ──
    try:
        request_parts: list[str] = []
        if complexity and complexity != "UNKNOWN":
            request_parts.append(f"{complexity} {dimensions}")
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
            f"{c} {d} files" for d, c in sorted(domain_counts.items(), key=lambda x: -x[1])
        )
        if not completed:
            completed = None

        conn.execute(
            "UPDATE session_summaries SET "
            "request = COALESCE(request, ?), "
            "completed = COALESCE(completed, ?) "
            "WHERE session_id = ?",
            (request_str, completed, session_id),
        )
        conn.commit()
    except Exception as exc:  # fail-open (Rule 6)
        print(f"session_enrich.py: enrichment step failed: {exc}", file=sys.stderr)

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

        # complexity resolved once at the top of main() via _read_gate_file()

        # Duration from the session's observation time-span (earliest→latest
        # edit). The previous source — session-id file mtime delta — collapsed
        # to 0 on every row. The span is a real wall-clock signal
        # already in the DB; falls back to 0 only when <2 observations exist.
        duration_ms = 0
        try:
            span = conn.execute(
                "SELECT (julianday(MAX(created_at)) - julianday(MIN(created_at))) * 86400000.0 "
                "FROM observations WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if span and span[0]:
                duration_ms = int(span[0])
        except sqlite3.Error as exc:  # fail-open (Rule 6)
            print(f"session_enrich.py: duration derive failed: {exc}", file=sys.stderr)

        # Real session model, not a hardcoded 'opus' — env first, then the
        # .model marker, then 'unknown'. Hardcoding made all 389 rows
        # identical; domain/complexity/duration
        # already vary per session.
        model = os.environ.get("COS_AGENT_MODEL") or os.environ.get("ANTHROPIC_MODEL")
        if not model:
            base = os.environ.get("COS_AGENT_DIR") or os.environ.get("COS_STATE_DIR", ".coding-os")
            marker = Path(base) / ".model"
            if marker.exists():
                model = marker.read_text().strip() or None
        model = model or "unknown"

        # No automated negative-signal source exists at session scope;
        # outcome variance is task-scoped via
        # record_outcome._derive_rework/_derive_blocked.
        outcome = "success"

        conn.execute(
            "INSERT INTO agent_metrics "
            "(task_id, agent_type, model, duration_ms, domain, complexity, outcome) "
            "VALUES (?, 'session', ?, ?, ?, ?, ?)",
            (task_id or None, model, duration_ms, domain, complexity, outcome),
        )
        conn.commit()
    except Exception as exc:  # fail-open (Rule 6)
        print(f"session_enrich.py: enrichment step failed: {exc}", file=sys.stderr)

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
    except Exception as exc:  # fail-open (Rule 6)
        print(f"session_enrich.py: enrichment step failed: {exc}", file=sys.stderr)

    # ── Step 6: Run decay if >7 days since last run ──
    # Delegate to the shared locked + throttled entry point so this Stop hook,
    # the nightly job, and auto-brain-decay all share ONE marker + exclusive lock
    # (no double-decay, no race). Marker lives next to the DB (project-shared).
    try:
        sys.path.insert(0, str(Path(db_path).resolve().parent))
        from decay import run_decay_locked

        run_decay_locked(db_path, throttle_days=7)
    except Exception as exc:  # fail-open (Rule 6)
        print(f"session_enrich.py: enrichment step failed: {exc}", file=sys.stderr)

    conn.close()


if __name__ == "__main__":
    main()
