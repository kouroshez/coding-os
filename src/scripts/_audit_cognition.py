"""Cognition and supervision probes for the cos_* MCP audit. Driven by audit_mcp_tools.py."""

from __future__ import annotations

import json
from pathlib import Path

from _audit_harness import SESSION, T, _d, _ok, _rec


async def test_cognition():
    print("\n═══ Cognition ════════════════════════════════════════════════════")

    # cos_analyze_task — needs `prompt` not `task_description`
    env, ms = await T(
        "cos_analyze_task",
        prompt="Fix graph_os uid resolution: agents pass raw paths, tools return not_found",
        task_marker="graph-os-uid-resolver",
        complexity="COMPLICATED",
        dimensions=3,
        session_id=SESSION,
    )
    _rec("cognition", "cos_analyze_task", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok("cognition", "cos_analyze_task signals", "domain" in d, f"keys={list(d.keys())[:5]}")
        print(f"    signals_preview={str(d.get('signals', '?'))[:200]}")

    # cos_situation_detect — signals is JSON array string
    env, ms = await T("cos_situation_detect", signals='["new_developer","first_time","no_docs"]')
    _rec("cognition", "cos_situation_detect(onboarding signals)", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        print(f"    situation={str(d)[:120]}")

    env, ms = await T("cos_situation_detect", signals="[]")
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
        "Fix graph_os uid resolution ergonomics", project_dir=str(pd)
    )
    signals_json_str = (
        signals_obj.model_dump_json()
        if hasattr(signals_obj, "model_dump_json")
        else json.dumps(
            {"domain": "graph_os", "action": "fix", "novelty": "low", "urgency": "medium"}
        )
    )
    env, ms = await T("cos_compose_chain", signals_json=signals_json_str, session_id=SESSION)
    _rec("cognition", "cos_compose_chain", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok("cognition", "cos_compose_chain", bool(d), f"keys={list(d.keys())[:5]}")

    # cos_ambiguity_check — needs session_id, task_marker, persona_id
    env, ms = await T(
        "cos_ambiguity_check",
        session_id=SESSION,
        task_marker="graph-os-uid-resolver",
        persona_id="backend-engineer",
    )
    _rec("cognition", "cos_ambiguity_check", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok("cognition", "cos_ambiguity_check", "passed" in d or bool(d), f"result={str(d)[:120]}")

    # cos_supervise
    env, ms = await T(
        "cos_supervise",
        session_id=SESSION,
        task_marker="graph-os-uid-resolver",
        persona_id="backend-engineer",
        intensity="standard",
    )
    _rec("cognition", "cos_supervise", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok(
            "cognition",
            "cos_supervise",
            "action" in d,
            f"action={d.get('action')} formula={d.get('formula')}",
        )

    # cos_dispatch_formula
    env, ms = await T(
        "cos_dispatch_formula",
        formula_id="analyst",
        session_id=SESSION,
        task_marker="graph-os-uid-resolver",
        persona_id="backend-engineer",
    )
    _rec("cognition", "cos_dispatch_formula(F2)", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok("cognition", "cos_dispatch_formula", bool(d), f"keys={list(d.keys())[:4]}")

    # cos_traceability
    env, ms = await T(
        "cos_traceability",
        session_id=SESSION,
        task_marker="graph-os-uid-resolver",
        persona_id="backend-engineer",
        scope="task",
    )
    _rec("cognition", "cos_traceability", env, ms=ms)
    if env.get("ok"):
        d = _d(env)
        _ok("cognition", "cos_traceability", "gaps" in d or bool(d), f"result={str(d)[:120]}")

    # cos_backtrack_log
    env, ms = await T(
        "cos_backtrack_log",
        session_id=SESSION,
        from_formula="implementer",
        to_formula="analyst",
        reason="uid scheme was wrong, need to re-research graph node format",
    )
    _rec("cognition", "cos_backtrack_log", env, ms=ms)

    # cos_discovery
    env, ms = await T(
        "cos_discovery",
        session_id=SESSION,
        task_marker="graph-os-uid-resolver",
        persona_id="backend-engineer",
        kind="constraint_change",
        summary="graph uid scheme requires prefix (code:file:, doc:file:, folder:) — undocumented",
        impact_assessment="all graph tools fail silently when raw paths passed",
        decision="record_for_later",
    )
    _rec("cognition", "cos_discovery", env, ms=ms)

    # cos_takeover
    env, ms = await T(
        "cos_takeover", session_id=SESSION + "-takeover", task_marker="existing-project-audit"
    )
    _rec("cognition", "cos_takeover", env, ms=ms)

    # cos_situation_detect with actual signal
    env, ms = await T(
        "cos_situation_detect", signals='["existing_project","no_tests","unknown_codebase"]'
    )
    _rec("cognition", "cos_situation_detect(takeover signals)", env, ms=ms)
