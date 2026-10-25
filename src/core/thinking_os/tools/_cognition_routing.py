"""Routing: compose the role chain from the role and preset registries."""

from __future__ import annotations

import logging

from tools._shared import ok, safe_tool

from ._cognition_shared import _schemas

logger = logging.getLogger("coding_os.tools.cognition")


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
        # agent-scoped state files the Hub's chain reader uses. Both live in
        # roles_state so this MCP path and the auto-compose hook
        # (hooks/_helpers/auto_compose.py) never drift on what it reads
        # — the drift that once left the chain empty.
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
