"""Routing: extract task signals, compose the role chain, describe a role.

The composer surface — everything between a prompt and an ordered chain. It
reads the role/preset/situation registries and never touches the EvidenceBundle.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from tools._shared import fail, ok, safe_tool

from ._cognition_shared import _cog, _resolve_agent_dir, _schemas

logger = logging.getLogger("coding_os.tools.cognition")


def register_cos_situation_detect(mcp, db_path):
    @mcp.tool(
        name="cos_situation_detect",
        description=(
            "Classify a set of signals into a situational dispatch chain id "
            "(incident-response, onboarding, scope-change, external-integration, "
            "design-review, existing-project-takeover) or null if none match. "
            "The matched situation overrides persona primary_formulas."
        ),
    )
    @safe_tool
    def cos_situation_detect(signals: str = "[]") -> str:
        cog = _cog()
        signal_set = set(json.loads(signals))
        situations = cog.load_situation_registry()

        for sit_id, sit in situations.items():
            triggers = set(sit.get("trigger_signals", []))
            matched = signal_set & triggers
            if matched:
                return ok(
                    {"situation_id": sit_id, "matched_signals": list(matched)},
                    meta={"layer": "routing"},
                )

        return ok({"situation_id": None, "matched_signals": []}, meta={"layer": "routing"})

    return cos_situation_detect


def register_cos_analyze_task(mcp, db_path):
    @mcp.tool(
        name="cos_analyze_task",
        description=(
            "Extract TaskSignals (domain, action, novelty, urgency, scope, "
            "external_dependency, is_takeover, breaking_change, ...) from a "
            "prompt + optional memory/graph context. Replaces persona "
            "keyword matching. Under 500ms; cached per task_marker."
        ),
    )
    @safe_tool
    def cos_analyze_task(
        prompt: str,
        task_marker: str = "",
        complexity: str = "COMPLICATED",
        dimensions: int = 1,
        project_dir: str = "",
        session_id: str = "",
    ) -> str:
        import task_analyzer  # lazy
        import tracing

        agent_dir = _resolve_agent_dir()
        pd = Path(project_dir) if project_dir else Path.cwd()
        sid = session_id or "anon"
        tracing.emit(
            sid,
            "analyze_start",
            {
                "prompt_len": len(prompt),
                "task_marker": task_marker,
                "complexity": complexity,
                "dimensions": dimensions,
            },
        )
        signals = task_analyzer.analyze_task(
            prompt=prompt,
            task_marker=task_marker or None,
            complexity=complexity,
            dimensions=dimensions,
            agent_dir=agent_dir,
            project_dir=pd,
        )
        tracing.emit(
            sid,
            "analyze_done",
            {
                "action": signals.action,
                "domain": signals.domain,
                "urgency": signals.urgency,
                "scope_size": signals.scope_size,
                "external_dependency": signals.external_dependency,
                "is_takeover": signals.is_takeover,
                "breaking_change": signals.breaking_change,
                "extraction_ms": signals.extraction_ms,
                "source_errors": signals.source_errors,
            },
        )
        return ok(
            signals.model_dump(),
            meta={"layer": "routing", "source": "task_analyzer"},
        )

    return cos_analyze_task


def register_cos_compose_chain(mcp, db_path):
    @mcp.tool(
        name="cos_compose_chain",
        description=(
            "Compose an ordered formula-role chain from TaskSignals. "
            "Strategy: situation override > preset match > per-role scoring "
            "composer > hard fallback. Returns ComposedChain with provenance "
            "(preset_id, preset_version, effective_threshold, activations)."
        ),
    )
    @safe_tool
    def cos_compose_chain(
        signals_json: str,
        situation_id: str = "",
        preset_min_score: int = -1,
        session_id: str = "",
    ) -> str:
        import formula_composer  # lazy

        schemas = _schemas()
        signals = schemas.TaskSignals.model_validate_json(signals_json)
        chain = formula_composer.compose_chain(
            signals=signals,
            situation_id=situation_id or None,
            preset_min_score=None if preset_min_score < 0 else preset_min_score,
        )
        sid = session_id or "anon"
        # Emit branch + compose_done traces AND stamp the chain to the
        # agent-scoped state files the Hub /api/roles panel reads. Both live in
        # roles_state so this MCP path and the auto-compose hook
        # (hooks/_helpers/auto_compose.py) never drift on what the panel reads
        # — the drift that left the panel empty.
        try:
            import roles_state

            roles_state.record_compose_traces(chain, sid)
            roles_state.stamp_roles(chain.chain)
        except Exception as exc:  # fire-and-forget telemetry — a write/serialize
            logger.debug("roles trace/state write failed: %s", exc)  # error must never fail compose

        # telemetry — persist the lead persona for the dispatch.
        # Schema (migration v14): one row per compose_chain call.
        try:
            import sqlite3 as _sqlite

            _conn = _sqlite.connect(db_path)
            try:
                lead_persona = chain.chain[0] if chain.chain else "unknown"
                # Confidence proxy: preset_matched > situation_override >
                # composer_fallback > hard_fallback (1.0 / 0.85 / 0.7 / 0.4).
                conf_map = {"preset": 1.0, "situation": 0.85, "composer": 0.7, "hard": 0.4}
                conf = conf_map.get(chain.source, 0.5)
                # Intensity is per-role; use lead role's first step as the
                # session-level signal (pragmatic — full breakdown lives in
                # the trace event).
                intensity = "default"
                _conn.execute(
                    "INSERT INTO persona_selections "
                    "(session_id, task_marker, persona_id, confidence, reason, intensity, ts) "
                    "VALUES (?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))",
                    (sid, chain.preset_id or "", lead_persona, conf, chain.source, intensity),
                )
                _conn.commit()
            finally:
                _conn.close()
        except Exception as exc:
            logger.debug("persona_selections insert failed: %s", exc)
        return ok(
            chain.model_dump(),
            meta={"layer": "routing", "source": "formula_composer"},
        )

    return cos_compose_chain


def register_cos_role_info(mcp, db_path):
    @mcp.tool(
        name="cos_role_info",
        description=(
            "Return metadata for a formula-role (researcher..refactorer): prompt_prefix, "
            "tools_budget, intensity_steps, backtrack_triggers, "
            "criteria_required. Useful for the main agent before dispatch."
        ),
    )
    @safe_tool
    def cos_role_info(role_id: str) -> str:
        import formula_composer  # lazy

        roles = formula_composer.load_roles()
        role = roles.get(role_id)
        if role is None:
            return fail("not_found", f"unknown role_id: {role_id}")
        keep = {
            k: role.get(k)
            for k in (
                "id",
                "role_name",
                "formula_ref",
                "agent_file",
                "intensity_steps",
                "tools_budget",
                "max_tokens_in",
                "max_tokens_out",
                "timeout_s",
                "model_pref",
                "backtrack_triggers",
                "criteria_required",
                "prompt_prefix",
                "parallel_dispatch",
            )
            if k in role
        }
        return ok(keep, meta={"layer": "routing", "source": "role_registry"})

    return cos_role_info
