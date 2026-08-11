"""graph_os probes for the cos_* MCP audit. Driven by audit_mcp_tools.py."""

from __future__ import annotations

from _audit_harness import FUNC_UID, GRAPH_FILE, GRAPH_UID, T, _d, _ok, _rec


async def test_graph():
    print("\n═══ Graph ════════════════════════════════════════════════════════")

    env, ms = await T("cos_graph_query", q="graph_os", limit=8)
    _rec("graph", "cos_graph_query('graph_os')", env, ms=ms)
    if env.get("ok"):
        r = _d(env).get("results", [])
        _ok("graph", "cos_graph_query", len(r) > 0, f"{len(r)} results")
        for x in r[:3]:
            print(f"    [{x.get('kind')}] {x.get('uid', '?')[:70]}")

    env, ms = await T("cos_graph_query", q="", kinds="mcp_tool", limit=10)
    _rec("graph", "cos_graph_query(mcp_tool kind)", env, ms=ms)
    if env.get("ok"):
        r = _d(env).get("results", [])
        _ok(
            "graph", "cos_graph_query kinds filter", isinstance(r, list), f"{len(r)} mcp_tool nodes"
        )

    # cos_graph_context — raw path auto-resolve
    env, ms = await T("cos_graph_context", uid_or_name=GRAPH_FILE, depth=1)
    _rec("graph", "cos_graph_context(raw_path)", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        nb = d.get("neighbours", [])
        _ok(
            "graph",
            "cos_graph_context",
            True,
            f"node={d.get('node', {}).get('uid', '?')[:50]} neighbours={len(nb)}",
        )

    # cos_graph_impact — raw path auto-resolve (was broken before fix)
    env, ms = await T("cos_graph_impact", uid=GRAPH_FILE, direction="downstream", depth=2)
    _rec("graph", "cos_graph_impact(raw_path)", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        tiers = d.get("tiers", {})
        _ok(
            "graph",
            "cos_graph_impact 3 tiers",
            all(k in tiers for k in ("will_break", "should_review", "context")),
            "all 3 tiers present",
        )
        wb = len(tiers.get("will_break", []))
        sr = len(tiers.get("should_review", []))
        ct = len(tiers.get("context", []))
        print(
            f"    will_break={wb} should_review={sr} context={ct} impacted={d.get('impacted_count')}"
        )

    env, ms = await T("cos_graph_impact", uid=GRAPH_UID, direction="upstream", depth=2)
    _rec("graph", "cos_graph_impact(upstream)", env, ms=ms)

    env, ms = await T("cos_graph_references", uid=GRAPH_FILE)
    _rec("graph", "cos_graph_references(raw_path)", env, ms=ms)
    if env.get("ok"):
        _ok("graph", "cos_graph_references", True, f"count={_d(env).get('count')}")

    env, ms = await T("cos_graph_similar", uid=GRAPH_FILE, top_k=5)
    _rec("graph", "cos_graph_similar(raw_path)", env, ms=ms)
    if env.get("ok"):
        _ok("graph", "cos_graph_similar", True, f"{len(_d(env).get('similar', []))} candidates")

    env, ms = await T(
        "cos_graph_path",
        source_uid=GRAPH_FILE,
        target_uid="src/core/hooks/registry.yaml",
        max_hops=4,
    )
    _rec("graph", "cos_graph_path(raw→raw)", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok(
            "graph",
            "cos_graph_path",
            True,
            f"hops={d.get('hops')} path_len={len(d.get('path') or [])}",
        )

    env, ms = await T("cos_graph_trace", entry_uid=FUNC_UID, max_steps=10)
    _rec("graph", "cos_graph_trace(func_uid)", env, ms=ms)
    if env.get("ok"):
        _ok("graph", "cos_graph_trace", True, f"{len(_d(env).get('steps', []))} steps")

    env, ms = await T("cos_graph_entrypoints", top_k=8)
    _rec("graph", "cos_graph_entrypoints", env, ms=ms)
    if env.get("ok"):
        eps = _d(env).get("entrypoints", [])
        _ok("graph", "cos_graph_entrypoints", len(eps) > 0, f"{len(eps)} entrypoints")
        for ep in eps[:3]:
            print(f"    ep: {ep.get('uid', '?')[:60]}  score={ep.get('score', '?')}")

    env, ms = await T("cos_graph_communities", min_size=3, max_communities=5)
    _rec("graph", "cos_graph_communities", env, ms=ms)
    if env.get("ok"):
        comms = _d(env).get("communities", [])
        _ok("graph", "cos_graph_communities", True, f"{len(comms)} communities")

    env, ms = await T("cos_graph_export", format="json", root_uid=GRAPH_UID, max_nodes=30)
    _rec("graph", "cos_graph_export(json)", env, ms=ms)
    if env.get("ok"):
        nodes = _d(env).get("nodes", [])
        _ok("graph", "cos_graph_export json nodes>0", len(nodes) > 0, f"{len(nodes)} nodes")

    env, ms = await T("cos_graph_export", format="mermaid", root_uid=GRAPH_UID, max_nodes=20)
    _rec("graph", "cos_graph_export(mermaid)", env, ms=ms)
    if env.get("ok"):
        mm = _d(env).get("diagram", _d(env).get("mermaid", _d(env).get("output", ""))) or ""
        _ok("graph", "cos_graph_export mermaid", len(mm) > 10, f"len={len(mm)}")
        print(f"    mermaid_preview={mm[:80]}")

    env, ms = await T("cos_graph_contracts", kinds="function,class", root_uid=GRAPH_UID)
    _rec("graph", "cos_graph_contracts", env, ms=ms)
    if env.get("ok"):
        _ok("graph", "cos_graph_contracts", bool(_d(env)), f"keys={list(_d(env).keys())[:4]}")

    env, ms = await T(
        "cos_graph_detect_changes",
        files="src/core/graph_os/tools/graph.py",
        scope="working",
        analyze_downstream=True,
    )
    _rec("graph", "cos_graph_detect_changes", env, ms=ms)

    env, ms = await T("cos_graph_rename_plan", uid=GRAPH_FILE, new_name="graph_tools")
    _rec("graph", "cos_graph_rename_plan(raw_path)", env, ms=ms)
    if env.get("ok"):
        plan = _d(env).get("plan") or _d(env)
        cs = plan.get("call_sites", []) if isinstance(plan, dict) else []
        _ok("graph", "cos_graph_rename_plan", bool(plan), f"call_sites={len(cs)}")
