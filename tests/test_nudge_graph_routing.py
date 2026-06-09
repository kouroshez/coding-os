"""Routing-corpus guard for nudge-graph-os.sh (TASK-289, epic retrieval-routing-fix).

Regression guard for the "ask about graph -> agent goes to memory" bug. The
root cause was a structural/conceptual question that matched NO nudge pattern,
so the agent fell through to the most-primed layer (memory).

This test invokes the REAL hook (not a reimplementation) with a synthetic
prompt and asserts it recommends the expected cos_graph_* tool. Each corpus
entry is its own parametrized case, so pytest's progress column doubles as the
coverage progress bar and a regression pinpoints the exact query that broke.

Run: uv run pytest tests/test_nudge_graph_routing.py -q
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "src" / "core" / "hooks" / "nudge-graph-os.sh"

# (query, expected cos_graph_* tool the nudge must recommend). Covers the 6
# queries that USED to fall through silently (conceptual + dead_code/test_gap)
# plus one representative per remaining structural tool. Every query is >=15
# chars (the hook's minimum-length gate).
CORPUS: tuple[tuple[str, str], ...] = (
    # --- conceptual: the original bug class (used to be silent -> memory) ---
    ("how does graph querying actually work?", "cos_graph_search"),
    ("explain the board_os sync flow end to end", "cos_graph_search"),
    ("what is the graph_os backend?", "cos_graph_search"),
    ("give me an overview of the hooks system", "cos_graph_search"),
    ("walk me through how routing is implemented", "cos_graph_search"),
    # --- structural tools previously uncovered by the nudge ---
    ("find dead code in the board module", "cos_graph_dead_code"),
    ("show test coverage gaps in graph_os", "cos_graph_test_gap"),
    ("are there circular imports in graph_os", "cos_graph_cycles"),
    ("what are the most important files here", "cos_graph_ranking"),
    ("which nodes are the chokepoint hubs", "cos_graph_centrality"),
    ("where is safe_tool defined in the tree", "cos_graph_query"),
    ("diff between main and the feature branch", "cos_graph_diff"),
    ("resolve this label to a canonical uid", "cos_graph_resolve"),
    # --- structural tools already covered (regression anchors) ---
    ("who calls cos_task_move in the codebase", "cos_graph_references"),
    ("rename cos_search to cos_memory_search", "cos_graph_rename_plan"),
    ("blast radius of changing safe_tool now", "cos_graph_impact"),
    ("trace the request execution path here", "cos_graph_trace"),
    ("list the api surface of the board now", "cos_graph_contracts"),
    ("anything similar to the safe_tool fn", "cos_graph_similar"),
    ("what subsystems exist in this project", "cos_graph_communities"),
    ("context around safe_tool before edit", "cos_graph_context"),
    ("entry points of the cli application", "cos_graph_entrypoints"),
    ("make a diagram of the graph module", "cos_graph_export"),
    ("graph is empty why is it broken now", "cos_graph_doctor"),
    ("what did i change since last commit", "cos_graph_detect_changes"),
    ("shortest path from server to backend", "cos_graph_path"),
)

# The fix must keep coverage at/above this fraction of the corpus. Set to 1.0:
# the corpus is curated, so any miss is a real regression, not noise.
MIN_COVERAGE = 1.0


def _fire_nudge(query: str, panel_dir: Path) -> str | None:
    """Invoke the real hook with an isolated panel dir; return the recommended tool or None.

    Isolated COS_PANEL_DIR per call defeats the per-pattern debounce marker so
    cases never shadow each other.
    """
    env = os.environ.copy()
    env.update(
        {
            "COS_PANEL_DIR": str(panel_dir),
            "COS_AGENT_DIR": str(panel_dir),
            "COS_STATE_DIR": str(panel_dir),
        }
    )
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"prompt": query}),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    if proc.returncode != 0:
        raise AssertionError(f"hook exited {proc.returncode} for {query!r}: {proc.stderr}")
    out = proc.stdout.strip()
    if not out:
        return None
    payload = json.loads(out)
    ctx = payload.get("hookSpecificOutput", {}).get("additionalContext", "")
    for tok in ctx.replace(".", " ").split():
        if tok.startswith("cos_graph_"):
            return tok
    return None


@pytest.mark.parametrize("query,expected", CORPUS, ids=[q for q, _ in CORPUS])
def test_query_routes_to_expected_tool(query: str, expected: str, tmp_path: Path) -> None:
    fired = _fire_nudge(query, tmp_path)
    assert fired == expected, (
        f"nudge misroute: {query!r}\n  expected: {expected}\n  got:      {fired or '(no nudge — silent)'}"
    )


def test_corpus_coverage_meets_threshold(tmp_path: Path) -> None:
    """Aggregate guard: report the measured routing coverage % and gate on it."""
    misses: list[str] = []
    for i, (query, expected) in enumerate(CORPUS):
        panel = tmp_path / f"case{i}"
        panel.mkdir()
        fired = _fire_nudge(query, panel)
        if fired != expected:
            misses.append(f"  {query!r} -> got {fired or 'silent'}, want {expected}")

    hit = len(CORPUS) - len(misses)
    coverage = hit / len(CORPUS)
    distinct_tools = len({tool for _, tool in CORPUS})
    print(
        f"\n[routing-corpus] {hit}/{len(CORPUS)} queries routed correctly "
        f"({coverage:.0%}); {distinct_tools} distinct cos_graph_* tools exercised."
    )
    assert coverage >= MIN_COVERAGE, "nudge routing regressed:\n" + "\n".join(misses)
