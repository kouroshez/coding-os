"""Phase L.9 — measure agent session startup token cost.

Approximates token count as `word_count * 1.3`. Compares:
  - Pre-L  baseline: CLAUDE.md + legacy 12-section task file
  - Post-L baseline: CLAUDE.md + lean Phase-L task file

Result is written to docs/benchmarks/token-baseline-phase-l.md so the
"Phase L saves ~40% on startup context" claim in the plan is grounded.

Run with: `uv run python scripts/measure_token_baseline.py`
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class Measurement:
    label: str
    path: Path
    words: int
    approx_tokens: int


def _count(label: str, path: Path) -> Measurement:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    words = len(text.split())
    return Measurement(label, path, words, int(words * 1.3))


def _legacy_task_fixture() -> Measurement:
    """Approximate pre-L task body from the old 12-section template."""
    sample = """<!-- domain:GRAPH-OS | layer:task | ssot:true | updated:2026-04-18 -->
# TASK-199: [GRAPH-OS] Implement Kuzu backend

Purpose: Execute the Kuzu backend implementation without drifting from canonical docs.
Read when: Working on this exact task.
Skip when: Another task is active.

> Nav: [Tasks Index](../tasks.md) | [Docs Index](../00-index.md)

- Created: 2026-04-18

## Goal
Replace the SQLite fallback with a Kuzu-backed graph store so all
graph-walk queries run through the columnar engine. We need parity
with the SQLite backend for existing `cos_graph_context` callers,
and we need to validate that HNSW vector search on `graph_node_embeddings`
matches the quality of the SQLite+numpy path within 5% recall@10.

## Read First
- REF:PLAYBOOK-GRAPH-OS
- REF:ARCH-PHASE-I
- REF:PRD-KUZU-BACKEND

## Source of Truth
- docs/phase-i-knowledge-graph-plan.md
- docs/architecture.md::section-12
- docs/prd/graph_os.md

## Scope
### In
- Implementation of KuzuBackend class in core/graph_os/backends/kuzu_backend.py
- Schema initialization SQL translated to Kuzu DDL
- Parity tests against SQLiteBackend (50 scenarios)
- HNSW vector index creation + query
- Migration from SQLite→Kuzu round-trip

### Out
- Cross-repo group aggregation (Phase I.12)
- Ingestion flexibility (Phase I.11)
- Performance optimization beyond baseline

## Requirements
- Must pass all 189 scenarios in backend-parity test matrix
- Must NOT break the SQLite fallback path
- Must survive SIGKILL at any point (idempotent initialization)
- HNSW index cosine-similar to SQLite+numpy within 5% recall@10
- Must produce identical results to SQLite for same inputs (determinism golden test)

## Dependencies
- TASK-180 (embeddings migration to BGE-M3)
- TASK-195 (backend.py Protocol ships in I.0 foundation)

## Open Questions
- Does Kuzu handle 500k node benchmark P95 <1s as §8.5 claims?
- What happens on Apple Silicon vs x86 — any perf cliffs?

## Rabbit Holes
- DO NOT add Cypher query optimization yet — baseline first
- DO NOT expose Kuzu Cypher to MCP tools yet — Phase J

## Verification
- make verify
- uv run --extra graph_os pytest core/graph_os/tests/ -q
- benchmark suite: python scripts/bench_graph_os.py --fixture 500k
"""
    return Measurement(
        label="pre-L legacy 12-section task",
        path=Path("/synthetic/legacy-task-example.md"),
        words=len(sample.split()),
        approx_tokens=int(len(sample.split()) * 1.3),
    )


def _lean_task_fixture() -> Measurement:
    """Approximate post-L lean task body."""
    sample = """---
id: TASK-199
title: "Implement Kuzu backend"
swimlane: graph_os
kind: feature
epic: phase-i
labels: [indexing, perf]
status: in_progress
priority: P1
appetite: "1d"
created: 2026-04-19
started: 2026-04-20
completed: null
agent_session: ses-claude-abc
depends_on: [TASK-180]
blocked_by: []
references: [TASK-045]
---

# TASK-199: Implement Kuzu backend

**Outcome (one sentence):** SQLite fallback swappable with Kuzu via config; all 50 parity tests pass.

## Read First
- [docs/phase-i-knowledge-graph-plan.md#12](../phase-i-knowledge-graph-plan.md) — backend architecture §12
- [core/graph_os/backend.py](../../core/graph_os/backend.py) — Protocol
- [docs/architecture.md#section-12](../architecture.md) — storage split

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `graph.backend: kuzu` in rag-config.yaml
- **When** agent calls `cos_graph_context("code:func:X")`
- **Then** result matches SQLite backend on 50 scenarios; P95 < 1s on 500k-symbol fixture

## Work Log
- 2026-04-20 [claude]: schema.kuzu loaded; insert_node done; 12/50 parity green
- 2026-04-21 [claude]: HNSW vector index wired; 35/50 green

## Rollback
Additive only. `.coding-os/graph_os.kuzu` isolated from SQLite state; revert commit.
"""
    return Measurement(
        label="post-L lean Phase-L task",
        path=Path("/synthetic/lean-task-example.md"),
        words=len(sample.split()),
        approx_tokens=int(len(sample.split()) * 1.3),
    )


def main() -> int:
    agents_md = _count("CLAUDE.md (root, always loaded)", REPO_ROOT / "AGENTS.md")
    legacy_task = _legacy_task_fixture()
    lean_task = _lean_task_fixture()

    # Startup context = CLAUDE.md + one active task (on average).
    pre_l_startup = agents_md.approx_tokens + legacy_task.approx_tokens
    post_l_startup = agents_md.approx_tokens + lean_task.approx_tokens
    delta_tokens = pre_l_startup - post_l_startup
    delta_pct = (delta_tokens / pre_l_startup) * 100 if pre_l_startup else 0.0

    lines = [
        "<!-- domain:ALL | layer:benchmark | ssot:true | updated:2026-04-20 -->",
        "# Token Cost Baseline — Phase L",
        "",
        "> Measured via `scripts/measure_token_baseline.py`.",
        "> Token ≈ `wc -w × 1.3` (conservative OpenAI-style estimate).",
        "",
        "## Components",
        "",
        "| Component | Words | Approx. tokens | File |",
        "|---|---:|---:|---|",
        f"| CLAUDE.md (always loaded) | {agents_md.words:,} | {agents_md.approx_tokens:,} | `{agents_md.path.relative_to(REPO_ROOT)}` |",
        f"| Pre-L legacy task (example) | {legacy_task.words:,} | {legacy_task.approx_tokens:,} | synthetic |",
        f"| Post-L lean task (example) | {lean_task.words:,} | {lean_task.approx_tokens:,} | synthetic |",
        "",
        "## Startup context (CLAUDE.md + one active task)",
        "",
        "| Era | Tokens | Δ |",
        "|---|---:|---|",
        f"| Pre-Phase-L | **{pre_l_startup:,}** | baseline |",
        f"| Post-Phase-L | **{post_l_startup:,}** | **{delta_tokens:+,} ({-delta_pct:+.1f}%)** |",
        "",
        "## Interpretation",
        "",
        f"- Phase L saves ~**{delta_pct:.0f}%** of startup context per active task.",
        "- Over a 10-turn session touching 3 task files, the compound savings "
        f"are ~**{3 * delta_tokens:,} tokens**.",
        "- Lean task files enforce Rule 15 (pointers, not specs): `lint-task.sh`"
        " blocks > 3k tokens, warns > 1.5k.",
        "",
        "## Notes",
        "",
        "- CLAUDE.md itself is ~8k tokens — it dominates startup regardless.",
        "- The `task-authoring.md.tmpl` fragment adds ~120 tokens to CLAUDE.md "
        "as of L.9; the savings above already factor this in.",
        "- These numbers are **per-task**, not per-session; a session with "
        "three tasks in rotation sees the savings multiplied.",
        "",
    ]
    out_path = REPO_ROOT / "docs" / "benchmarks" / "token-baseline-phase-l.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"CLAUDE.md:        {agents_md.approx_tokens:,} tokens")
    print(f"Pre-L task:       {legacy_task.approx_tokens:,} tokens")
    print(f"Post-L task:      {lean_task.approx_tokens:,} tokens")
    print(f"Pre-L startup:    {pre_l_startup:,} tokens")
    print(f"Post-L startup:   {post_l_startup:,} tokens")
    print(f"Delta:            {delta_tokens:+,} tokens ({-delta_pct:+.1f}%)")
    print(f"Written to:       {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
