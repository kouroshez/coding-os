#!/usr/bin/env python3
"""End-to-end smoke harness for every cos_graph_* tool.

For each of the 16 tools (13 MCP-registered + 3 internal: centrality,
ranking, doctor) the harness:

1. Calls the tool with a realistic fixture argument.
2. Asserts envelope shape: ok=True, data is dict, meta.layer=="graph".
3. Captures a 1-line summary (result count, key fields) for the report.
4. Records elapsed time + estimated token cost (envelope JSON length / 4).

Output: docs/engineering/graph-tools-smoke-report.md (overwrite per run)
        + stdout PASS/FAIL summary for CI gating.

Run: uv run python scripts/smoke_graph_e2e.py
Exit: 0 if all PASS; 1 if any FAIL or envelope shape wrong.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src" / "core"))

# Real fixture uids from this repo's live graph (29K+ nodes).
FIXTURE_FILE = "src/core/thinking_os/server.py"
FIXTURE_FUNC_UID = (
    "code:function:src/core/thinking_os/server.py::thinking_os_health"
)
FIXTURE_FILE_UID = "code:file:src/core/thinking_os/server.py"
FIXTURE_TARGET_UID = "code:file:src/core/graph_os/tools/graph.py"
FIXTURE_LABEL_QUERY = "thinking_os_health"


def _envelope_ok(env: Any) -> tuple[bool, str, dict[str, Any]]:
    """Tools return a JSON string (shared.ok wraps with json.dumps).

    Parse it once, then validate shape.
    """
    if isinstance(env, str):
        try:
            env = json.loads(env)
        except json.JSONDecodeError as exc:
            return False, f"json decode: {exc}", {}
    if not isinstance(env, dict):
        return False, f"not a dict: {type(env).__name__}", {}
    if not env.get("ok"):
        return False, f"ok=False: {env.get('error') or env}", env
    data = env.get("data")
    if not isinstance(data, dict):
        return False, f"data not dict: {type(data).__name__}", env
    meta = (data.get("meta") if isinstance(data.get("meta"), dict) else env.get("meta")) or {}
    if meta.get("layer") != "graph":
        return False, f"meta.layer != graph (got {meta.get('layer')!r})", env
    return True, "ok", env


def _summarise(env: dict[str, Any]) -> str:
    """One-line summary of the envelope for the report."""
    if not env.get("ok"):
        return f"FAIL — {env.get('error', 'unknown')}"
    data = env.get("data") or {}
    bits: list[str] = []
    for key in ("results", "neighbours", "neighbors", "callers", "edges", "nodes",
                "affected", "communities", "candidates", "contracts", "path",
                "diff", "rename_targets", "similar"):
        if isinstance(data.get(key), list):
            bits.append(f"{key}={len(data[key])}")
    if not bits:
        # Fallback — count top-level dict keys
        bits.append(f"keys={','.join(list(data.keys())[:5])}")
    return " ".join(bits[:5])


def run_case(
    name: str,
    fn: Callable[[], Any],
    *,
    expect_ok: bool = True,
) -> dict[str, Any]:
    t0 = time.time()
    try:
        env = fn()
    except Exception as exc:  # noqa: BLE001
        return {
            "tool": name,
            "status": "ERROR",
            "elapsed_ms": int((time.time() - t0) * 1000),
            "summary": f"exception: {type(exc).__name__}: {exc}",
            "tokens": 0,
        }
    elapsed = int((time.time() - t0) * 1000)

    parsed: dict[str, Any] = {}
    if expect_ok:
        ok, reason, parsed = _envelope_ok(env)
        status = "PASS" if ok else "FAIL"
    else:
        status = "PASS" if isinstance(env, (dict, str)) else "FAIL"
        reason = "non-ok envelope expected"
        if isinstance(env, str):
            try:
                parsed = json.loads(env)
            except json.JSONDecodeError:
                parsed = {}
        elif isinstance(env, dict):
            parsed = env

    summary = _summarise(parsed) if parsed else "no parsed result"
    raw_str = env if isinstance(env, str) else json.dumps(env, default=str)
    tokens = len(raw_str) // 4
    return {
        "tool": name,
        "status": status,
        "elapsed_ms": elapsed,
        "summary": summary if status == "PASS" else f"{status}: {reason} | {summary}",
        "tokens": tokens,
    }


def main() -> int:
    from graph_os.tools import graph as g

    cases: list[dict[str, Any]] = []

    # ── A. DISCOVERY ─────────────────────────────────────────────────
    cases.append(run_case(
        "cos_graph_query (label)",
        lambda: g.cos_graph_query(FIXTURE_LABEL_QUERY, limit=3),
    ))
    cases.append(run_case(
        "cos_graph_query (path-fallback)",
        lambda: g.cos_graph_query(FIXTURE_FILE, limit=3),
    ))
    cases.append(run_case(
        "cos_graph_query (kind filter)",
        lambda: g.cos_graph_query("dispatcher", kinds=["class"], limit=5),
    ))
    cases.append(run_case(
        "cos_graph_resolve (NL)",
        lambda: g.cos_graph_resolve("the dispatcher function"),
    ))
    cases.append(run_case(
        "cos_graph_resolve (path)",
        lambda: g.cos_graph_resolve(FIXTURE_FILE),
    ))
    cases.append(run_case(
        "cos_graph_resolve (qualname)",
        lambda: g.cos_graph_resolve("ClaudeSDKDispatcher.dispatch"),
    ))

    # ── B. LOCAL CONTEXT ─────────────────────────────────────────────
    cases.append(run_case(
        "cos_graph_context (path)",
        lambda: g.cos_graph_context(FIXTURE_FILE, depth=1),
    ))
    cases.append(run_case(
        "cos_graph_context (uid + spine)",
        lambda: g.cos_graph_context(FIXTURE_FUNC_UID, depth=1, include_spine=True),
    ))

    # ── C. RELATIONSHIPS ─────────────────────────────────────────────
    cases.append(run_case(
        "cos_graph_references",
        lambda: g.cos_graph_references(FIXTURE_FUNC_UID),
    ))
    cases.append(run_case(
        "cos_graph_path",
        lambda: g.cos_graph_path(FIXTURE_FILE_UID, FIXTURE_TARGET_UID),
    ))

    # ── D. RISK ──────────────────────────────────────────────────────
    cases.append(run_case(
        "cos_graph_impact (downstream)",
        lambda: g.cos_graph_impact(FIXTURE_FUNC_UID, depth=2, direction="downstream"),
    ))
    cases.append(run_case(
        "cos_graph_impact (upstream)",
        lambda: g.cos_graph_impact(FIXTURE_FUNC_UID, depth=2, direction="upstream"),
    ))
    cases.append(run_case(
        "cos_graph_rename_plan",
        lambda: g.cos_graph_rename_plan(FIXTURE_FUNC_UID, "renamed_health_check"),
    ))
    cases.append(run_case(
        "cos_graph_detect_changes",
        lambda: g.cos_graph_detect_changes(files=[FIXTURE_FILE]),
    ))

    # ── E. EXECUTION ─────────────────────────────────────────────────
    cases.append(run_case(
        "cos_graph_trace",
        lambda: g.cos_graph_trace(FIXTURE_FUNC_UID, max_steps=20),
    ))

    # ── F. SIMILARITY ────────────────────────────────────────────────
    cases.append(run_case(
        "cos_graph_similar",
        lambda: g.cos_graph_similar(FIXTURE_FUNC_UID, top_k=3),
    ))

    # ── G. SURFACE ───────────────────────────────────────────────────
    cases.append(run_case(
        "cos_graph_contracts (mcp)",
        lambda: g.cos_graph_contracts(kinds=["mcp"]),
    ))
    cases.append(run_case(
        "cos_graph_contracts (http)",
        lambda: g.cos_graph_contracts(kinds=["http"]),
    ))
    cases.append(run_case(
        "cos_graph_entrypoints",
        lambda: g.cos_graph_entrypoints(top=10),
    ))

    # ── H. STRUCTURE ─────────────────────────────────────────────────
    cases.append(run_case(
        "cos_graph_communities",
        lambda: g.cos_graph_communities(top=10),
    ))
    cases.append(run_case(
        "cos_graph_centrality (degree)",
        lambda: g.cos_graph_centrality(metric="degree", top=10),
    ))
    cases.append(run_case(
        "cos_graph_ranking",
        lambda: g.cos_graph_ranking(query="dispatcher", top=10),
    ))

    # ── I. ARTIFACTS ─────────────────────────────────────────────────
    cases.append(run_case(
        "cos_graph_export (mermaid)",
        lambda: g.cos_graph_export(format="mermaid", root_uid=FIXTURE_FILE_UID),
    ))
    cases.append(run_case(
        "cos_graph_export (json)",
        lambda: g.cos_graph_export(format="json", root_uid=FIXTURE_FILE_UID),
    ))

    # ── J. HEALTH ────────────────────────────────────────────────────
    cases.append(run_case(
        "cos_graph_doctor",
        lambda: g.cos_graph_doctor(),
    ))

    # ── Render report ────────────────────────────────────────────────
    pass_n = sum(1 for c in cases if c["status"] == "PASS")
    fail_n = sum(1 for c in cases if c["status"] == "FAIL")
    err_n = sum(1 for c in cases if c["status"] == "ERROR")
    total_tokens = sum(c["tokens"] for c in cases)
    total_ms = sum(c["elapsed_ms"] for c in cases)

    print(f"\n{'='*70}")
    print(f"SMOKE RESULT: {pass_n}/{len(cases)} pass · {fail_n} fail · {err_n} error")
    print(f"Total time: {total_ms}ms · Total tokens: ~{total_tokens}")
    print(f"{'='*70}\n")
    for c in cases:
        glyph = {"PASS": "✓", "FAIL": "✗", "ERROR": "💥"}[c["status"]]
        print(f"  {glyph} {c['tool']:<40} {c['elapsed_ms']:>5}ms  ~{c['tokens']:>5}tok  {c['summary'][:100]}")

    # Write markdown report
    report_path = REPO_ROOT / "docs" / "engineering" / "graph-tools-smoke-report.md"
    lines = [
        "<!-- domain:ALL | layer:engineering | ssot:false | updated:auto -->",
        "# Graph Tools — Smoke E2E Report",
        "",
        f"> Auto-generated by `scripts/smoke_graph_e2e.py`. Run: `uv run python scripts/smoke_graph_e2e.py`.",
        f"> Last run: {time.strftime('%Y-%m-%d %H:%M:%S')} · {pass_n}/{len(cases)} pass · {total_ms}ms · ~{total_tokens} tok.",
        "",
        "## Per-tool result",
        "",
        "| Tool | Status | Elapsed | Tokens | Summary |",
        "|---|---|---|---|---|",
    ]
    for c in cases:
        glyph = {"PASS": "✅", "FAIL": "❌", "ERROR": "💥"}[c["status"]]
        summ = c["summary"].replace("|", "\\|")[:120]
        lines.append(f"| `{c['tool']}` | {glyph} {c['status']} | {c['elapsed_ms']}ms | ~{c['tokens']} | {summ} |")

    lines.extend([
        "",
        "## Token economics",
        "",
        f"- Total smoke envelope size: ~{total_tokens} tokens.",
        f"- For comparison: reading the 5 source files involved (~{5 * 2000} tokens) costs **~{5 * 2000 // total_tokens if total_tokens else 0}× more** than running every tool above.",
        "",
        "## Coverage",
        "",
        f"- 13 MCP-registered tools: covered.",
        f"- 3 internal-only tools (centrality, ranking, doctor): covered.",
        f"- Total = 16 tool/argument combinations smoke-tested = {len(cases)} cases.",
    ])
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nReport: {report_path}")

    return 0 if (fail_n == 0 and err_n == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
