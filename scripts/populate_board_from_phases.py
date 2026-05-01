"""One-shot script to populate the Scrumban board with remaining phase tasks.

Reads:
  docs/phase-i-knowledge-graph-plan.md   → I.1..I.14 pending slices
  docs/phase-j-meta-router-plan.md       → J.1..J.6 pending slices
  docs/phase-k-db-abstraction-plan.md    → K.1..K.4 pending slices

Creates one task per pending slice via the board_os.mcp_tools surface.
Known-broken pre-existing items go into the EMERGENCY column with
kind=bug + P1.

Idempotent: skips tasks whose title already exists on the board.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from core.board_os import mcp_tools
from core.board_os.workflow import transition


# ---------------------------------------------------------------------------
# Phase I — graph_os (14 remaining slices)
# ---------------------------------------------------------------------------

PHASE_I_TASKS = [
    ("I.1  BGE-M3 embedding migration (background role)",
     "graph_os", "refactor", "P2", "2d",
     ["docs/phase-i-knowledge-graph-plan.md#I.1",
      "core/thinking_os/embeddings.py"]),
    ("I.2  md_links extractor (links_to + cites_heading edges)",
     "graph_os", "feature", "P1", "1d",
     ["docs/phase-i-knowledge-graph-plan.md#I.2"]),
    ("I.3  task_deps extractor (depends_on + references_doc)",
     "graph_os", "feature", "P2", "1d",
     ["docs/phase-i-knowledge-graph-plan.md#I.3"]),
    ("I.4  Python tree-sitter extractor + 7-step symbol lookup",
     "graph_os", "feature", "P1", "3d",
     ["docs/phase-i-knowledge-graph-plan.md#I.4"]),
    ("I.5  pyright LSP overlay + warm-start role",
     "graph_os", "feature", "P2", "2d",
     ["docs/phase-i-knowledge-graph-plan.md#I.5"]),
    ("I.6  TS/TSX tree-sitter extractor + tsserver overlay",
     "graph_os", "feature", "P2", "3d",
     ["docs/phase-i-knowledge-graph-plan.md#I.6"]),
    ("I.7  shell + yaml + contracts extractors",
     "graph_os", "feature", "P2", "2d",
     ["docs/phase-i-knowledge-graph-plan.md#I.7"]),
    ("I.8  11 cos_graph_* MCP tools (query/context/impact/...)",
     "graph_os", "feature", "P1", "3d",
     ["docs/phase-i-knowledge-graph-plan.md#I.8"]),
    ("I.9  Orchestrator — registry/dispatcher/worker_pool/roles",
     "thinking_os", "feature", "P1", "3d",
     ["docs/phase-i-knowledge-graph-plan.md#I.9"]),
    ("I.10 Sigma.js WebGL viewer + cos graph-viz CLI",
     "graph_os", "feature", "P2", "3d",
     ["docs/phase-i-knowledge-graph-plan.md#I.10"]),
    ("I.11 Ingestion flexibility (local/github/zip + guards)",
     "cli", "feature", "P3", "2d",
     ["docs/phase-i-knowledge-graph-plan.md#I.11"]),
    ("I.12 Repo groups + cross-repo edge detection",
     "graph_os", "feature", "P2", "3d",
     ["docs/phase-i-knowledge-graph-plan.md#I.12"]),
    ("I.13 Scale benchmark suite + perf regression gate",
     "graph_os", "test", "P2", "2d",
     ["docs/phase-i-knowledge-graph-plan.md#I.13"]),
    ("I.14 Graph docs + graph-explorer skill + doctor C16-C22",
     "docs", "docs", "P3", "1d",
     ["docs/phase-i-knowledge-graph-plan.md#I.14"]),
]


# ---------------------------------------------------------------------------
# Phase J — cos_retrieve meta-router (6 slices)
# ---------------------------------------------------------------------------

PHASE_J_TASKS = [
    ("J.1  classify_query — regex + keyword classifier",
     "thinking_os", "feature", "P2", "1d",
     ["docs/phase-j-meta-router-plan.md#J.1"]),
    ("J.2  dispatch — layer selection + score normalization",
     "thinking_os", "feature", "P2", "1d",
     ["docs/phase-j-meta-router-plan.md#J.2"]),
    ("J.3  retrieval_router_log migration + append-only schema",
     "thinking_os", "feature", "P3", "2h",
     ["docs/phase-j-meta-router-plan.md#J.3"]),
    ("J.4  cos_retrieve MCP tool — register + envelope",
     "thinking_os", "feature", "P2", "2h",
     ["docs/phase-j-meta-router-plan.md#J.4"]),
    ("J.5  evaluate_router.py — precision/recall CSV evaluator",
     "thinking_os", "test", "P3", "1d",
     ["docs/phase-j-meta-router-plan.md#J.5"]),
    ("J.6  AGENTS.md / CLAUDE.md addendum for cos_retrieve",
     "docs", "docs", "P3", "30m",
     ["docs/phase-j-meta-router-plan.md#J.6"]),
]


# ---------------------------------------------------------------------------
# Phase K — DB abstraction (4 pending slices)
# ---------------------------------------------------------------------------

PHASE_K_TASKS = [
    ("K.1  DBAdapter Protocol — abstract similarity_search + fts + audit",
     "thinking_os", "refactor", "P3", "1d",
     ["docs/phase-k-db-abstraction-plan.md#K.1"]),
    ("K.2  Postgres pgvector adapter (gated, HNSW)",
     "thinking_os", "feature", "P3", "2d",
     ["docs/phase-k-db-abstraction-plan.md#K.2"]),
    ("K.3  sqlite → postgres migration script + round-trip",
     "thinking_os", "feature", "P3", "1d",
     ["docs/phase-k-db-abstraction-plan.md#K.3"]),
    ("K.4  Consumer docs: --db postgres:// opt-in",
     "docs", "docs", "P3", "30m",
     ["docs/phase-k-db-abstraction-plan.md#K.4"]),
]


# ---------------------------------------------------------------------------
# EMERGENCY — known-broken pre-existing bugs
# ---------------------------------------------------------------------------

EMERGENCY_TASKS = [
    ("Fix hardcoded 'codex' literal in cli/main.py (line ~1021)",
     "cli", "bug", "P1", "30m",
     ["cli/main.py", "tests/test_no_hardcoded_stacks.py"]),
    ("Fix hardcoded 'claude'/'codex' literals in cli/doctor.py",
     "cli", "bug", "P1", "1h",
     ["cli/doctor.py", "tests/test_no_hardcoded_stacks.py"]),
    ("Fix golden parity drift on codex_* fixtures (5 tests failing)",
     "adapters", "bug", "P2", "2h",
     ["tests/test_golden_parity.py", "adapters/codex/"]),
    ("Fix persona integration doctor FAILs (3 tests)",
     "cli", "bug", "P2", "2h",
     ["tests/test_persona_integration.py", "cli/doctor.py"]),
    ("Fix test_task_start_skips_template_placeholder_anchors timeout",
     "cli", "bug", "P2", "1h",
     ["tests/test_rag_pipeline.py", "core/scripts/task-create.sh"]),
]


def _open_conn() -> sqlite3.Connection:
    db_path = os.environ.get(
        "COS_DB_PATH", str(_REPO_ROOT / ".coding-os" / "coding-os.db"),
    )
    return sqlite3.connect(db_path)


def _existing_titles(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT title FROM tasks").fetchall()
    return {r[0] for r in rows}


def _create(
    conn: sqlite3.Connection,
    title: str,
    swimlane: str,
    kind: str,
    priority: str,
    appetite: str,
    read_first: list[str],
    *,
    epic: str,
    outcome: str,
) -> str | None:
    env_str = mcp_tools.cos_task_create(
        conn,
        title=title, swimlane=swimlane, kind=kind,
        priority=priority, appetite=appetite, epic=epic,
        outcome=outcome, read_first=read_first,
    )
    env = json.loads(env_str)
    if not env["ok"]:
        print(f"  ✗ {title[:60]}: {env['error']['message']}")
        return None
    return env["data"]["task_id"]


def _set_emergency(conn: sqlite3.Connection, task_id: str) -> bool:
    """icebox → emergency via workflow.transition."""
    result = transition(
        conn, task_id, "emergency", reason="known-broken pre-existing bug",
    )
    return result.ok


def main() -> int:
    os.environ.setdefault("COS_PROJECT_ROOT", str(_REPO_ROOT))
    conn = _open_conn()
    existing = _existing_titles(conn)
    created = 0
    skipped = 0
    emergencies = 0

    # Phase I
    for title, lane, kind, prio, app, refs in PHASE_I_TASKS:
        if title in existing:
            skipped += 1; continue
        tid = _create(
            conn, title, lane, kind, prio, app, refs,
            epic="phase-i",
            outcome=f"Phase I slice {title.split()[0]} shipped per plan.",
        )
        if tid:
            created += 1
            print(f"  ✓ {tid}  {title[:70]}  [{lane}/{kind}/{prio}]")

    # Phase J
    for title, lane, kind, prio, app, refs in PHASE_J_TASKS:
        if title in existing:
            skipped += 1; continue
        tid = _create(
            conn, title, lane, kind, prio, app, refs,
            epic="phase-j",
            outcome=f"Phase J slice {title.split()[0]} shipped per plan.",
        )
        if tid:
            created += 1
            print(f"  ✓ {tid}  {title[:70]}  [{lane}/{kind}/{prio}]")

    # Phase K
    for title, lane, kind, prio, app, refs in PHASE_K_TASKS:
        if title in existing:
            skipped += 1; continue
        tid = _create(
            conn, title, lane, kind, prio, app, refs,
            epic="phase-k",
            outcome=f"Phase K slice {title.split()[0]} shipped per plan.",
        )
        if tid:
            created += 1
            print(f"  ✓ {tid}  {title[:70]}  [{lane}/{kind}/{prio}]")

    # Emergency — create in icebox then transition to emergency.
    print("\n  === Emergency (known-broken pre-existing bugs) ===")
    for title, lane, kind, prio, app, refs in EMERGENCY_TASKS:
        if title in existing:
            skipped += 1; continue
        tid = _create(
            conn, title, lane, kind, prio, app, refs,
            epic="bugs-2026-q2",
            outcome=f"{title} resolved; failing test passes.",
        )
        if tid:
            if _set_emergency(conn, tid):
                emergencies += 1
                created += 1
                print(f"  🚨 {tid}  {title[:65]}  [{lane}/{kind}/{prio}]")
            else:
                print(f"  ? {tid}  created in icebox (transition failed)")

    conn.close()
    print(f"\n  Summary: created={created} skipped={skipped} "
          f"emergencies={emergencies}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
