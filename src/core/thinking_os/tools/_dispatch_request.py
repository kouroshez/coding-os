"""Model-tier resolution and DispatchRequest construction from session state."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from ._cognition_shared import _cog, _load_bundle

logger = logging.getLogger("thinking_os.cognition")


def _preset_role_hint(session_id: str, formula_id: str, db_path) -> dict:
    # Tier-2 lookup (claude-sdk.md §7.3): the session's composed preset is
    # read back from persona_selections (preset_id lives in its task_marker
    # column — see register_cos_compose_chain's INSERT), then that preset's
    # roles_adapter_hints[formula_id]. Fail-open: hints are advisory.
    if not db_path:
        return {}
    try:
        import sqlite3 as _sqlite3

        conn = _sqlite3.connect(db_path, timeout=10)
        try:
            row = conn.execute(
                "SELECT task_marker FROM persona_selections WHERE session_id = ? "
                "ORDER BY rowid DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()
        preset_id = row[0] if row and row[0] else ""
        if not preset_id:
            return {}
        import formula_composer

        presets, _version = formula_composer.load_presets()
        preset = next((p for p in presets if p.get("id") == preset_id), {})
        hint = (preset.get("roles_adapter_hints") or {}).get(formula_id) or {}
        return hint if isinstance(hint, dict) else {}
    except Exception as exc:
        logger.debug("preset hint lookup failed: %s", exc)
        return {}


def _empirical_model(complexity: str, db_path) -> str:
    # Tier-4: cos_route_model's recommendation, only when real outcome
    # history backs it (cold-start static defaults must not override the
    # SDK default for every dispatch).
    if not db_path or not complexity.strip():
        return ""
    try:
        import sqlite3 as _sqlite3

        from tools.routing import route_model_bandit

        conn = _sqlite3.connect(db_path, timeout=10)
        try:
            result = route_model_bandit(conn, complexity=complexity.strip().upper())
        finally:
            conn.close()
        if int(result.get("data_points") or 0) > 0:
            return str(result.get("recommended_model") or "")
        return ""
    except Exception as exc:
        logger.debug("empirical model lookup failed: %s", exc)
        return ""


def _resolve_dispatch_model(
    formula_id: str,
    session_id: str,
    meta: dict,
    model: str,
    complexity: str,
    db_path,
    supervised: dict[str, str] | None = None,
) -> str:
    level = complexity.strip().lower()
    hint_pref = _preset_role_hint(session_id, formula_id, db_path).get("model_pref") or {}
    role_pref = meta.get("model_pref") or {}
    resolved = ""
    for candidate, source in (
        (model.strip(), "explicit"),
        ((supervised or {}).get("model", ""), "supervision_policy"),
        (hint_pref.get(level, ""), "preset_hint"),
        (role_pref.get(level, ""), "role_pref"),
    ):
        if candidate:
            logger.info("dispatch model resolved for %s: %s via %s", formula_id, candidate, source)
            resolved = candidate
            break
    if not resolved:
        # Empirical is the expensive tier (sqlite connect + bandit query/sampling)
        # — consult it lazily, only when the static tiers all miss.
        empirical = _empirical_model(complexity, db_path)
        if empirical:
            logger.info("dispatch model resolved for %s: %s via empirical", formula_id, empirical)
            resolved = empirical
    # Cost-routed independent reviewer: a review role runs one tier cheaper than
    # the generator. Gated by COS_ROUTER_REVIEWER_CHEAPER (default off, unchanged).
    if resolved and os.environ.get("COS_ROUTER_REVIEWER_CHEAPER"):
        from tools.routing import _REVIEW_ROLES, reviewer_model

        if formula_id in _REVIEW_ROLES:
            cheaper = reviewer_model(resolved)
            if cheaper and cheaper != resolved:
                logger.info("reviewer %s downgraded to cheaper tier %s", formula_id, cheaper)
                resolved = cheaper
    return resolved


def _build_dispatch_request(
    formula_id: str,
    session_id: str,
    task_marker: str,
    persona_id: str,
    intensity: str,
    timeout_s: float | None,
    model: str = "",
    complexity: str = "",
    db_path=None,
    adapter: str = "",
    effort: str = "",
):
    """Build a DispatchRequest from session state (shared by run-one and run-parallel)."""
    from thinking_os import dispatcher as _disp  # lazy: avoid circular at import time

    cog = _cog()
    agents = cog.load_agent_registry()
    meta = agents.get(formula_id) or {}
    agent_file_rel = f"src/core/thinking_os/agents/{meta.get('_file', f'{formula_id}.md')}"
    agent_path = Path(__file__).resolve().parent.parent / "agents" / meta.get("_file", "")
    prompt_text = agent_path.read_text() if agent_path.exists() else ""

    bundle = _load_bundle(session_id, task_marker, persona_id)
    input_slice = cog.build_input_slice(formula_id, bundle)
    input_slice["intensity_steps"] = cog._intensity_steps(formula_id, intensity)

    from thinking_os import supervision

    supervised = supervision.role_policy(formula_id, complexity=complexity)
    resolved_model = _resolve_dispatch_model(
        formula_id, session_id, meta, model, complexity, db_path, supervised
    )

    return _disp.DispatchRequest(
        formula_id=formula_id,
        agent_file=str(agent_path if agent_path.exists() else agent_file_rel),
        prompt=prompt_text,
        input_slice=input_slice,
        persona_id=persona_id,
        intensity=intensity if intensity in ("light", "standard", "full") else "standard",
        timeout_s=float(timeout_s) if timeout_s else float(meta.get("timeout_s", 300)),
        session_id=session_id,
        long_context=bool(meta.get("long_context", False)),
        model=resolved_model or None,
        adapter=adapter.strip() or supervised.get("adapter") or None,
        effort=effort.strip() or supervised.get("effort") or None,
        complexity=complexity.strip(),
    )
