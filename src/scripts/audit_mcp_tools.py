"""Comprehensive audit of every cos_* MCP tool via the real FastMCP layer.

INPUT:        none (reads the live coding-os.db; COS_DB_PATH override honored).
OUTPUT:       per-tool PASS/WARN/FAIL report to stdout; exit 0 all-pass else 1.
DEPENDENCIES: a populated coding-os.db, thinking_os.server (FastMCP).
"""

from __future__ import annotations

import asyncio
import sys

from _audit_cognition import test_cognition
from _audit_graph import test_graph
from _audit_harness import MCP, PAT_ID, TASK_ID, Results, T, _d, _ok, _rec

# ── tests ────────────────────────────────────────────────────────────────────


async def test_health():
    print("\n═══ Health ═══════════════════════════════════════════════════════")
    env, ms = await T("cos_health")
    _rec("health", "cos_health", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        tables = d.get("tables", {})
        _ok(
            "health",
            "cos_health",
            tables.get("graph_nodes", 0) > 0,
            f"graph_nodes={tables.get('graph_nodes')}",
        )
        _ok("health", "cos_health", tables.get("tasks", 0) > 0, f"tasks={tables.get('tasks')}")
        print(
            f"    db_size={d.get('db_size_bytes', 0) // 1024 // 1024}MB "
            f"schema_v={d.get('schema_version')} fts5={d.get('fts5_available')}"
        )


async def test_memory():
    print("\n═══ Memory ═══════════════════════════════════════════════════════")

    env, ms = await T("cos_search", query="graph_os uid resolver", limit=5)
    _rec("memory", "cos_search(graph_os)", env, ms=ms)
    if env.get("ok"):
        r = _d(env).get("results", [])
        _ok("memory", "cos_search results", isinstance(r, list), f"{len(r)} results")
        for x in r[:2]:
            print(f"    → [{x.get('memory_type', '?')}] {x.get('title', '?')[:70]}")

    env, ms = await T("cos_search", query="hook enforcement gate block", memory_type="pattern")
    _rec("memory", "cos_search(type=pattern)", env, ms=ms)

    env, ms = await T("cos_timeline", days=7, limit=10)
    _rec("memory", "cos_timeline(7d)", env, ms=ms)
    if env.get("ok"):
        _ok("memory", "cos_timeline", bool(_d(env)), f"keys={list(_d(env).keys())[:4]}")

    env, ms = await T("cos_details", pattern_id=PAT_ID, source="learned_patterns")
    _rec("memory", "cos_details(pattern)", env, ms=ms)

    env, ms = await T("cos_promote", pattern_id=PAT_ID, target="feedback")
    _rec("memory", "cos_promote", env, ms=ms)

    env, ms = await T(
        "cos_observation_record", file_path="src/core/graph_os/tools/graph.py", tool_name="Edit"
    )
    _rec("memory", "cos_observation_record", env, ms=ms)


async def test_metrics():
    print("\n═══ Metrics ══════════════════════════════════════════════════════")

    env, ms = await T(
        "cos_metric_record",
        agent_type="claude",
        outcome="success",
        task_id=TASK_ID,
        domain="graph_os",
        metric_name="audit_smoke",
        value=1.0,
    )
    _rec("metrics", "cos_metric_record", env, ms=ms)

    env, ms = await T("cos_metric_query", domain="", model="", outcome="", window_days=7)
    _rec("metrics", "cos_metric_query(all)", env, ms=ms)
    if env.get("ok"):
        _ok("metrics", "cos_metric_query", bool(_d(env)), f"keys={list(_d(env).keys())[:5]}")

    env, ms = await T("cos_metric_query", domain="graph_os", outcome="success", window_days=30)
    _rec("metrics", "cos_metric_query(domain=graph_os)", env, ms=ms)

    env, ms = await T("cos_metric_trend", metric="success_rate", window_days=30, group_by="domain")
    _rec("metrics", "cos_metric_trend", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        print(f"    trend_preview={str(d)[:120]}")


async def test_learning():
    print("\n═══ Learning ═════════════════════════════════════════════════════")

    env, ms = await T("cos_learn_extract", min_occurrences=2)
    _rec("learning", "cos_learn_extract", env, ms=ms)
    if env.get("ok"):
        _ok("learning", "cos_learn_extract", bool(_d(env)), f"result={str(_d(env))[:80]}")

    env, ms = await T("cos_learn_suggest", domain="graph_os", complexity="COMPLICATED", limit=3)
    _rec("learning", "cos_learn_suggest", env, ms=ms)
    if env.get("ok"):
        s = _d(env).get("suggestions", _d(env).get("results", []))
        _ok("learning", "cos_learn_suggest", isinstance(s, list), f"{len(s)} suggestions")
        for x in s[:2]:
            print(f"    → {str(x)[:100]}")

    env, ms = await T("cos_learn_validate", pattern_id=PAT_ID, was_helpful=True)
    _rec("learning", "cos_learn_validate", env, ms=ms)

    env, ms = await T(
        "cos_learn_narrative",
        task_id=TASK_ID,
        what_failed="raw paths passed to cos_graph_impact returned not_found",
        what_worked="auto-resolve prefix fallback in _resolve_uid",
        key_insight="uid scheme never documented in tool description",
    )
    _rec("learning", "cos_learn_narrative", env, ms=ms)


async def test_routing():
    print("\n═══ Routing ══════════════════════════════════════════════════════")

    env, ms = await T("cos_route_model", complexity="COMPLICATED", dimensions=3, domain="graph_os")
    _rec("routing", "cos_route_model", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok("routing", "cos_route_model", bool(d), f"rec={str(d)[:120]}")

    env, ms = await T(
        "cos_route_skill", domain="python", task_type="implementation", complexity="CLEAR"
    )
    _rec("routing", "cos_route_skill", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok("routing", "cos_route_skill", bool(d), f"rec={str(d)[:120]}")


async def test_docs():
    print("\n═══ Docs RAG ═════════════════════════════════════════════════════")

    env, ms = await T("cos_doc_search", query="graph uid format scheme code:file", limit=5)
    _rec("docs", "cos_doc_search(uid scheme)", env, ms=ms)
    if env.get("ok"):
        hits = _d(env).get("results", [])
        _ok("docs", "cos_doc_search results", isinstance(hits, list), f"{len(hits)} hits")
        for h in hits[:3]:
            sc = h.get("score", 0)
            fp = h.get("file_path", h.get("source", "?"))
            print(f"    [{sc:.3f}] {fp} — {h.get('title', '?')[:50]}")

    env, ms = await T(
        "cos_doc_search", query="hook enforcement pre-tool-use blocking gate rule", limit=5
    )
    _rec("docs", "cos_doc_search(hook enforcement)", env, ms=ms)
    if env.get("ok"):
        hits = _d(env).get("results", [])
        relevant = [
            h for h in hits if any(kw in str(h).lower() for kw in ("hook", "enforce", "gate"))
        ]
        _ok(
            "docs",
            "cos_doc_search relevance",
            len(hits) == 0 or len(relevant) > 0,
            f"{len(relevant)}/{len(hits)} hook-related",
        )

    env, ms = await T(
        "cos_doc_search",
        query="meta-project DNA mRNA phenotype coding-os architecture",
        limit=3,
        mode="semantic",
    )
    _rec("docs", "cos_doc_search(AGENTS semantic)", env, ms=ms)


async def test_retrieval():
    print("\n═══ Retrieval ════════════════════════════════════════════════════")

    env, ms = await T("cos_retrieval_cite", retrieval_ids="1,2,3")
    _rec("retrieval", "cos_retrieval_cite", env, ms=ms)

    env, ms = await T("cos_retrieval_learn", lookback_days=7, dry_run=True)
    _rec("retrieval", "cos_retrieval_learn(dry_run)", env, ms=ms)
    if env.get("ok"):
        print(f"    learn_preview={str(_d(env))[:120]}")

    env, ms = await T("cos_retrieval_quality", lookback_days=14, layer="")
    _rec("retrieval", "cos_retrieval_quality(14d)", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok("retrieval", "cos_retrieval_quality", bool(d), f"keys={list(d.keys())[:4]}")
        print(f"    quality={str(d)[:160]}")

    env, ms = await T("cos_retrieval_enrichment_check", lookback_days=14)
    _rec("retrieval", "cos_retrieval_enrichment_check", env, ms=ms)
    if env.get("ok"):
        print(f"    enrichment={str(_d(env))[:160]}")


async def test_tasks():
    print("\n═══ Tasks / Board ════════════════════════════════════════════════")

    env, ms = await T("cos_task_board")
    _rec("tasks", "cos_task_board", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok("tasks", "cos_task_board", bool(d), f"keys={list(d.keys())[:5]}")

    env, ms = await T("cos_task_search", query="graph", status="", limit=5)
    _rec("tasks", "cos_task_search('graph')", env, ms=ms)
    if env.get("ok"):
        hits = _d(env).get("results", [])
        _ok("tasks", "cos_task_search", isinstance(hits, list), f"{len(hits)} tasks")
        for h in hits[:3]:
            print(f"    {h.get('task_id', '?')} — {h.get('title', '?')[:60]}")

    env, ms = await T("cos_task_by_filter", status="in_progress", limit=10)
    _rec("tasks", "cos_task_by_filter(in_progress)", env, ms=ms)
    if env.get("ok"):
        t = _d(env).get("tasks", [])
        print(f"    in_progress={len(t)}")

    env, ms = await T("cos_task_by_filter", status="complete", limit=5)
    _rec("tasks", "cos_task_by_filter(complete)", env, ms=ms)

    env, ms = await T("cos_task_dependencies", task_id=TASK_ID)
    _rec("tasks", "cos_task_dependencies", env, ms=ms)

    env, ms = await T("cos_task_dependents", task_id=TASK_ID)
    _rec("tasks", "cos_task_dependents", env, ms=ms)

    env, ms = await T("cos_task_pick", swimlane="", priority_min="P3")
    _rec("tasks", "cos_task_pick", env, ms=ms)

    env, ms = await T("cos_task_wip_check")
    _rec("tasks", "cos_task_wip_check", env, ms=ms)
    if env.get("ok"):
        print(f"    wip={str(_d(env))[:120]}")

    env, ms = await T("cos_task_daily", since="24h")
    _rec("tasks", "cos_task_daily", env, ms=ms)

    env, ms = await T("cos_task_retro", since="7d")
    _rec("tasks", "cos_task_retro(7d)", env, ms=ms)

    env, ms = await T(
        "cos_work_log_append",
        task_id=TASK_ID,
        summary="audit smoke — all MCP tools exercised",
        source="audit",
    )
    _rec("tasks", "cos_work_log_append", env, ms=ms)

    env, ms = await T("cos_digest_regenerate", project_root="")
    _rec("tasks", "cos_digest_regenerate", env, ms=ms)


# ── main ──────────────────────────────────────────────────────────────────────


async def main():
    tools = await MCP.list_tools()
    cos_tools = [t for t in tools if t.name.startswith("cos_")]
    print(f"Registered: {len(tools)} total, {len(cos_tools)} cos_*")
    tool_names = {t.name for t in cos_tools}
    print(f"Names: {sorted(tool_names)}\n")

    await test_health()
    await test_memory()
    await test_metrics()
    await test_learning()
    await test_routing()
    await test_docs()
    await test_retrieval()
    await test_tasks()
    await test_graph()
    await test_cognition()

    # ── summary ───────────────────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("SUMMARY")
    print("═" * 60)

    groups: dict[str, dict[str, int]] = {}
    for group, _name, result in Results:
        s = groups.setdefault(group, {"PASS": 0, "WARN": 0, "FAIL": 0})
        for k in ("PASS", "WARN", "FAIL"):
            if result.startswith(k):
                s[k] += 1
                break

    tp = sum(v["PASS"] for v in groups.values())
    tw = sum(v["WARN"] for v in groups.values())
    tf = sum(v["FAIL"] for v in groups.values())
    total = tp + tw + tf

    for g, s in groups.items():
        flag = "✗" if s["FAIL"] else ("⚠" if s["WARN"] else "✓")
        print(f"  {flag} {g:20s}  PASS={s['PASS']:2d}  WARN={s['WARN']}  FAIL={s['FAIL']}")

    print(f"\nTOTAL  {tp}/{total} PASS  |  {tw} WARN  |  {tf} FAIL")

    if tf:
        print("\n── FAILURES ──────────────────────────────────────────────────")
        for group, name, result in Results:
            if result.startswith("FAIL"):
                print(f"  [{group}] {name.strip()}: {result[5:200]}")

    return 0 if tf == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
