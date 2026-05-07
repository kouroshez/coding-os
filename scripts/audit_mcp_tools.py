"""Comprehensive audit of all 63 cos_* MCP tools via the real FastMCP layer."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "core" / "thinking_os"))

os.environ.setdefault("COS_DB_PATH", str(ROOT / ".coding-os/coding-os.db"))

print("Loading server…")
import thinking_os.server as srv_mod  # noqa: E402
MCP = srv_mod.mcp
print("Done.\n")

# ── helpers ──────────────────────────────────────────────────────────────────

Results: list[tuple[str, str, str]] = []


async def _call(tool: str, **kwargs) -> dict:
    """Call tool via FastMCP. call_tool returns (list[TextContent], meta_dict)."""
    try:
        result_list, _meta = await MCP.call_tool(tool, kwargs)
        if result_list:
            text = getattr(result_list[0], "text", None) or str(result_list[0])
        else:
            return {"ok": False, "_exc": "empty result list"}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"ok": False, "_raw": text[:400]}
    except Exception as exc:
        return {"ok": False, "_exc": f"{type(exc).__name__}: {exc}"}


def _rec(group: str, name: str, env: dict, *, ms: float = 0.0) -> dict:
    ok = env.get("ok")
    if ok is True:
        status, detail = "PASS", f"{ms:.0f}ms"
    elif ok is False:
        err = env.get("error") or {}
        cat = err.get("category") or env.get("_exc", "?")
        msg = (err.get("message") or env.get("_raw") or env.get("_exc", ""))[:160]
        status, detail = "FAIL", f"cat={cat} | {msg}"
    else:
        status, detail = "WARN", f"missing 'ok': {str(env)[:100]}"
    sym = "✓" if status == "PASS" else ("⚠" if status == "WARN" else "✗")
    print(f"  {sym} {name}: {detail}")
    Results.append((group, name, f"{status}: {detail}"))
    return env


def _ok(group: str, label: str, cond: bool, note: str) -> None:
    sym = "✓" if cond else "✗"
    print(f"    {sym} [{note}]")
    Results.append((group, f"  {label}", f"{'PASS' if cond else 'FAIL'}: {note}"))


def _d(env: dict) -> dict:
    return env.get("data") or {}


async def T(tool: str, **kwargs) -> dict:
    t0 = time.perf_counter()
    env = await _call(tool, **kwargs)
    return env, (time.perf_counter() - t0) * 1000


# ── fixtures ──────────────────────────────────────────────────────────────────

from thinking_os.database import init_db  # noqa: E402

DB = init_db(str(ROOT / ".coding-os/coding-os.db"))
_obs = DB.execute("SELECT id FROM observations LIMIT 1").fetchone()
OBS_ID = _obs["id"] if _obs else 1
_pat = DB.execute("SELECT id FROM learned_patterns LIMIT 1").fetchone()
PAT_ID = _pat["id"] if _pat else 1
_task = DB.execute("SELECT task_id FROM tasks LIMIT 1").fetchone()
TASK_ID = _task["task_id"] if _task else "TASK-001"
SESSION = "ses-claude-audit-smoke"

GRAPH_FILE = "core/graph_os/tools/graph.py"
GRAPH_UID  = f"code:file:{GRAPH_FILE}"
FUNC_UID   = "code:function:core/graph_os/tools/graph.py::_resolve_uid"


# ── tests ────────────────────────────────────────────────────────────────────

async def test_health():
    print("\n═══ Health ═══════════════════════════════════════════════════════")
    env, ms = await T("cos_health")
    _rec("health", "cos_health", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        tables = d.get("tables", {})
        _ok("health", "cos_health", tables.get("graph_nodes", 0) > 0,
            f"graph_nodes={tables.get('graph_nodes')}")
        _ok("health", "cos_health", tables.get("tasks", 0) > 0,
            f"tasks={tables.get('tasks')}")
        print(f"    db_size={d.get('db_size_bytes',0)//1024//1024}MB "
              f"schema_v={d.get('schema_version')} fts5={d.get('fts5_available')}")


async def test_memory():
    print("\n═══ Memory ═══════════════════════════════════════════════════════")

    env, ms = await T("cos_search", query="graph_os uid resolver", limit=5)
    _rec("memory", "cos_search(graph_os)", env, ms=ms)
    if env.get("ok"):
        r = _d(env).get("results", [])
        _ok("memory", "cos_search results", isinstance(r, list), f"{len(r)} results")
        for x in r[:2]:
            print(f"    → [{x.get('memory_type','?')}] {x.get('title','?')[:70]}")

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

    env, ms = await T("cos_observation_record",
                      file_path="core/graph_os/tools/graph.py",
                      tool_name="Edit")
    _rec("memory", "cos_observation_record", env, ms=ms)


async def test_metrics():
    print("\n═══ Metrics ══════════════════════════════════════════════════════")

    env, ms = await T("cos_metric_record",
                      agent_type="claude", outcome="success",
                      task_id=TASK_ID, domain="graph_os",
                      metric_name="audit_smoke", value=1.0)
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

    env, ms = await T("cos_learn_feedback", min_rework=1)
    _rec("learning", "cos_learn_feedback", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        print(f"    feedback_preview={str(d)[:120]}")

    env, ms = await T("cos_learn_narrative",
                      task_id=TASK_ID,
                      what_failed="raw paths passed to cos_graph_impact returned not_found",
                      what_worked="auto-resolve prefix fallback in _resolve_uid",
                      key_insight="uid scheme never documented in tool description")
    _rec("learning", "cos_learn_narrative", env, ms=ms)


async def test_routing():
    print("\n═══ Routing ══════════════════════════════════════════════════════")

    env, ms = await T("cos_route_model", complexity="COMPLICATED", dimensions=3, domain="graph_os")
    _rec("routing", "cos_route_model", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok("routing", "cos_route_model", bool(d), f"rec={str(d)[:120]}")

    env, ms = await T("cos_route_skill", domain="python", task_type="implementation", complexity="CLEAR")
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
            print(f"    [{sc:.3f}] {fp} — {h.get('title','?')[:50]}")

    env, ms = await T("cos_doc_search", query="hook enforcement pre-tool-use blocking gate rule", limit=5)
    _rec("docs", "cos_doc_search(hook enforcement)", env, ms=ms)
    if env.get("ok"):
        hits = _d(env).get("results", [])
        relevant = [h for h in hits if any(kw in str(h).lower() for kw in ("hook","enforce","gate"))]
        _ok("docs", "cos_doc_search relevance",
            len(hits) == 0 or len(relevant) > 0,
            f"{len(relevant)}/{len(hits)} hook-related")

    env, ms = await T("cos_doc_search", query="meta-project DNA mRNA phenotype coding-os architecture", limit=3, mode="semantic")
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
            print(f"    {h.get('task_id','?')} — {h.get('title','?')[:60]}")

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

    env, ms = await T("cos_work_log_append",
                      task_id=TASK_ID,
                      summary="audit smoke — all MCP tools exercised",
                      source="audit")
    _rec("tasks", "cos_work_log_append", env, ms=ms)

    env, ms = await T("cos_digest_regenerate", project_root="")
    _rec("tasks", "cos_digest_regenerate", env, ms=ms)


async def test_graph():
    print("\n═══ Graph ════════════════════════════════════════════════════════")

    env, ms = await T("cos_graph_query", q="graph_os", limit=8)
    _rec("graph", "cos_graph_query('graph_os')", env, ms=ms)
    if env.get("ok"):
        r = _d(env).get("results", [])
        _ok("graph", "cos_graph_query", len(r) > 0, f"{len(r)} results")
        for x in r[:3]:
            print(f"    [{x.get('kind')}] {x.get('uid','?')[:70]}")

    env, ms = await T("cos_graph_query", q="", kinds="mcp_tool", limit=10)
    _rec("graph", "cos_graph_query(mcp_tool kind)", env, ms=ms)
    if env.get("ok"):
        r = _d(env).get("results", [])
        _ok("graph", "cos_graph_query kinds filter", isinstance(r, list), f"{len(r)} mcp_tool nodes")

    # cos_graph_context — raw path auto-resolve
    env, ms = await T("cos_graph_context", uid_or_name=GRAPH_FILE, depth=1)
    _rec("graph", "cos_graph_context(raw_path)", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        nb = d.get("neighbours", [])
        _ok("graph", "cos_graph_context", True, f"node={d.get('node',{}).get('uid','?')[:50]} neighbours={len(nb)}")

    # cos_graph_impact — raw path auto-resolve (was broken before fix)
    env, ms = await T("cos_graph_impact", uid=GRAPH_FILE, direction="downstream", depth=2)
    _rec("graph", "cos_graph_impact(raw_path)", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        tiers = d.get("tiers", {})
        _ok("graph", "cos_graph_impact 3 tiers",
            all(k in tiers for k in ("will_break","should_review","context")), "all 3 tiers present")
        wb = len(tiers.get("will_break",[]))
        sr = len(tiers.get("should_review",[]))
        ct = len(tiers.get("context",[]))
        print(f"    will_break={wb} should_review={sr} context={ct} impacted={d.get('impacted_count')}")

    env, ms = await T("cos_graph_impact", uid=GRAPH_UID, direction="upstream", depth=2)
    _rec("graph", "cos_graph_impact(upstream)", env, ms=ms)

    env, ms = await T("cos_graph_references", uid=GRAPH_FILE)
    _rec("graph", "cos_graph_references(raw_path)", env, ms=ms)
    if env.get("ok"):
        _ok("graph", "cos_graph_references", True, f"count={_d(env).get('count')}")

    env, ms = await T("cos_graph_similar", uid=GRAPH_FILE, top_k=5)
    _rec("graph", "cos_graph_similar(raw_path)", env, ms=ms)
    if env.get("ok"):
        _ok("graph", "cos_graph_similar", True, f"{len(_d(env).get('similar',[]))} candidates")

    env, ms = await T("cos_graph_path",
                      source_uid=GRAPH_FILE, target_uid="core/hooks/registry.yaml", max_hops=4)
    _rec("graph", "cos_graph_path(raw→raw)", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok("graph", "cos_graph_path", True, f"hops={d.get('hops')} path_len={len(d.get('path') or [])}")

    env, ms = await T("cos_graph_trace", entry_uid=FUNC_UID, max_steps=10)
    _rec("graph", "cos_graph_trace(func_uid)", env, ms=ms)
    if env.get("ok"):
        _ok("graph", "cos_graph_trace", True, f"{len(_d(env).get('steps',[]))} steps")

    env, ms = await T("cos_graph_entrypoints", top_k=8)
    _rec("graph", "cos_graph_entrypoints", env, ms=ms)
    if env.get("ok"):
        eps = _d(env).get("entrypoints", [])
        _ok("graph", "cos_graph_entrypoints", len(eps) > 0, f"{len(eps)} entrypoints")
        for ep in eps[:3]:
            print(f"    ep: {ep.get('uid','?')[:60]}  score={ep.get('score','?')}")

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

    env, ms = await T("cos_graph_detect_changes",
                      files="core/graph_os/tools/graph.py",
                      scope="working", analyze_downstream=True)
    _rec("graph", "cos_graph_detect_changes", env, ms=ms)

    env, ms = await T("cos_graph_rename_plan", uid=GRAPH_FILE, new_name="graph_tools")
    _rec("graph", "cos_graph_rename_plan(raw_path)", env, ms=ms)
    if env.get("ok"):
        plan = _d(env).get("plan") or _d(env)
        cs = plan.get("call_sites", []) if isinstance(plan, dict) else []
        _ok("graph", "cos_graph_rename_plan", bool(plan), f"call_sites={len(cs)}")


async def test_cognition():
    print("\n═══ Cognition ════════════════════════════════════════════════════")

    # cos_analyze_task — needs `prompt` not `task_description`
    env, ms = await T("cos_analyze_task",
                      prompt="Fix graph_os uid resolution: agents pass raw paths, tools return not_found",
                      task_marker="graph-os-uid-resolver", complexity="COMPLICATED",
                      dimensions=3, session_id=SESSION)
    _rec("cognition", "cos_analyze_task", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok("cognition", "cos_analyze_task signals", "domain" in d, f"keys={list(d.keys())[:5]}")
        print(f"    signals_preview={str(d.get('signals','?'))[:200]}")

    # cos_situation_detect — signals is JSON array string
    env, ms = await T("cos_situation_detect", signals='["new_developer","first_time","no_docs"]')
    _rec("cognition", "cos_situation_detect(onboarding signals)", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        print(f"    situation={str(d)[:120]}")

    env, ms = await T("cos_situation_detect", signals='[]')
    _rec("cognition", "cos_situation_detect(no signals)", env, ms=ms)

    # cos_role_info — needs role_id
    env, ms = await T("cos_role_info", role_id="analyst")
    _rec("cognition", "cos_role_info(F2)", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok("cognition", "cos_role_info", bool(d), f"keys={list(d.keys())[:5]}")

    env, ms = await T("cos_role_info", role_id="implementer")
    _rec("cognition", "cos_role_info(F5)", env, ms=ms)

    # cos_compose_chain — needs `signals_json`
    import task_analyzer  # lazy
    pd = Path.cwd()
    signals_obj = task_analyzer.analyze_task(
        "Fix graph_os uid resolution ergonomics",
        project_dir=str(pd)
    )
    signals_json_str = signals_obj.model_dump_json() if hasattr(signals_obj, "model_dump_json") else json.dumps({"domain":"graph_os","action":"fix","novelty":"low","urgency":"medium"})
    env, ms = await T("cos_compose_chain", signals_json=signals_json_str, session_id=SESSION)
    _rec("cognition", "cos_compose_chain", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok("cognition", "cos_compose_chain", bool(d), f"keys={list(d.keys())[:5]}")

    # cos_ambiguity_check — needs session_id, task_marker, persona_id
    env, ms = await T("cos_ambiguity_check",
                      session_id=SESSION, task_marker="graph-os-uid-resolver", persona_id="backend-engineer")
    _rec("cognition", "cos_ambiguity_check", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok("cognition", "cos_ambiguity_check", "passed" in d or bool(d), f"result={str(d)[:120]}")

    # cos_supervise
    env, ms = await T("cos_supervise",
                      session_id=SESSION, task_marker="graph-os-uid-resolver",
                      persona_id="backend-engineer", intensity="standard")
    _rec("cognition", "cos_supervise", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok("cognition", "cos_supervise", "action" in d, f"action={d.get('action')} formula={d.get('formula')}")

    # cos_dispatch_formula
    env, ms = await T("cos_dispatch_formula",
                      formula_id="analyst", session_id=SESSION,
                      task_marker="graph-os-uid-resolver", persona_id="backend-engineer")
    _rec("cognition", "cos_dispatch_formula(F2)", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok("cognition", "cos_dispatch_formula", bool(d), f"keys={list(d.keys())[:4]}")

    # cos_traceability
    env, ms = await T("cos_traceability",
                      session_id=SESSION, task_marker="graph-os-uid-resolver",
                      persona_id="backend-engineer", scope="task")
    _rec("cognition", "cos_traceability", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok("cognition", "cos_traceability", "gaps" in d or bool(d), f"result={str(d)[:120]}")

    # cos_backtrack_log
    env, ms = await T("cos_backtrack_log",
                      session_id=SESSION, from_formula="implementer", to_formula="analyst",
                      reason="uid scheme was wrong, need to re-research graph node format")
    _rec("cognition", "cos_backtrack_log", env, ms=ms)

    # cos_discovery
    env, ms = await T("cos_discovery",
                      session_id=SESSION, task_marker="graph-os-uid-resolver",
                      persona_id="backend-engineer",
                      kind="constraint_change",
                      summary="graph uid scheme requires prefix (code:file:, doc:file:, folder:) — undocumented",
                      impact_assessment="all graph tools fail silently when raw paths passed",
                      decision="record_for_later")
    _rec("cognition", "cos_discovery", env, ms=ms)

    # cos_takeover
    env, ms = await T("cos_takeover",
                      session_id=SESSION + "-takeover",
                      task_marker="existing-project-audit")
    _rec("cognition", "cos_takeover", env, ms=ms)

    # cos_situation_detect with actual signal
    env, ms = await T("cos_situation_detect", signals='["existing_project","no_tests","unknown_codebase"]')
    _rec("cognition", "cos_situation_detect(takeover signals)", env, ms=ms)


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
    for group, name, result in Results:
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
