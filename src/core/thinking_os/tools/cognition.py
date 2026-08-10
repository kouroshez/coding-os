"""Coding OS — Formula-agent supervisor MCP tools."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from pathlib import Path

from tools._shared import _gated_module, fail, ok, safe_tool

logger = logging.getLogger("coding_os.tools.cognition")

from ._cognition_dispatch import (  # noqa: F401 — re-exported for tests + siblings
    _build_dispatch_request,
    _emit_dispatch_metrics_safe,
    _empirical_model,
    _persist_dispatch_output,
    _preset_role_hint,
    _resolve_dispatch_model,
    register_cos_dispatch_formula,
    register_cos_dispatch_formula_run,
    register_cos_dispatch_parallel_run,
)
from ._cognition_shared import (  # noqa: F401 — re-exported for tests + siblings
    _all_bundle_fields,
    _bundle_path,
    _cog,
    _load_bundle,
    _now_iso,
    _resolve_agent_dir,
    _resolve_role_persistence,
    _save_bundle,
    _schemas,
)

# Canonical corrective action per backtrack root cause — the SSOT shared by
# cos_backtrack_log (returned as the agent's next-step suggestion) and
# learn_extract's anatomy mining (the remedy paired with a recurring cause that
# carries no recorded remedy). Keys match the backtrack root_cause enum.
CANONICAL_REMEDIES: dict[str, str] = {
    "wrong_model": "Use cos_route_model to select the right model before re-dispatching.",
    "scope_too_large": "Decompose via cos_task_create and pick the smallest slice.",
    "missing_context": "Run cos_doc_search or cos_search to load relevant context first.",
    "tool_failure": "Run cos_health to verify permissions/env vars, then retry with explicit paths.",
    "spec_ambiguity": "Log open questions via cos_discovery and resolve with user before implementing.",
    "env_mismatch": "Run cos doctor to validate environment config, then restart the session.",
    "other": "Re-classify the problem (Cynefin gate) and review the Anti-Paralysis advisory.",
}


# Lazy import of cognition — avoids circular at module load time


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# cos_supervise
# ---------------------------------------------------------------------------


def register_cos_supervise(mcp, db_path):  # db_path reserved for future warm-history ranking
    @mcp.tool(
        name="cos_supervise",
        description=(
            "Return the next action the main agent should take: dispatch a "
            "formula-agent, backtrack, or signal done. Call repeatedly after "
            "recording each formula output via cos_supervise_record_output. "
            "Never spawns agents itself — only tells the main agent what to dispatch."
        ),
    )
    @safe_tool
    def cos_supervise(
        session_id: str,
        task_marker: str,
        persona_id: str,
        intensity: str = "standard",
        situation_id: str = "",
        phase: str = "ROUTING",
        dispatched: str = "[]",
        pending: str = "[]",
        backtrack_count: int = 0,
    ) -> str:
        cog = _cog()
        schemas = _schemas()

        state = schemas.SupervisorState(
            session_id=session_id,
            task_marker=task_marker,
            persona_id=persona_id,
            intensity=intensity,
            situation_id=situation_id or None,
            phase=phase,
            dispatched=json.loads(dispatched),
            pending=json.loads(pending),
            backtrack_count=backtrack_count,
        )
        bundle = _load_bundle(session_id, task_marker, persona_id)
        action = cog.advance(state, bundle)

        # emit trace event for every supervisor transition
        try:
            import tracing

            event_kind = "supervise_action"
            if action.action == "dispatch":
                event_kind = "role_dispatch"
            elif action.action == "dispatch_parallel":
                event_kind = "parallel_dispatch"
            elif action.action == "backtrack":
                event_kind = "backtrack"
            elif action.action == "done":
                event_kind = "task_done"
            tracing.emit(
                session_id,
                event_kind,
                {
                    "action": action.action,
                    "formula": action.formula,
                    "formulas": action.formulas,
                    "reason": action.reason,
                    "phase": state.phase,
                    "dispatched_count": len(state.dispatched),
                    "backtrack_count": state.backtrack_count,
                },
                role=action.formula,
                phase=state.phase,
            )
        except Exception as exc:
            from core.logging_os import swallow_safe

            swallow_safe("thinking_os.cognition", "supervise output trace emit failed", exc=exc)

        # Mirror the dispatch-time model precedence (claude-sdk.md §7.3
        # tiers 2-3) so the main agent can pick a model BEFORE the run tool.
        model_hints: dict = {}
        if action.action in ("dispatch", "dispatch_parallel") and action.formula:
            role_meta = cog.load_agent_registry().get(action.formula) or {}
            model_hints = {
                "preset_hint": _preset_role_hint(session_id, action.formula, db_path),
                "role_pref": role_meta.get("model_pref") or {},
            }

        return ok(
            {
                "action": action.action,
                "formula": action.formula,
                "formulas": action.formulas,
                "agent_file": action.agent_file,
                "reason": action.reason,
                "advisory": action.advisory,
                "model_hints": model_hints,
                "state": {
                    "phase": state.phase,
                    "dispatched": state.dispatched,
                    "pending": state.pending,
                    "backtrack_count": state.backtrack_count,
                },
            },
            meta={"layer": "routing", "source": "supervisor"},
        )

    return cos_supervise


# ---------------------------------------------------------------------------
# cos_supervise_record_output
# ---------------------------------------------------------------------------


def register_cos_supervise_record_output(mcp, db_path):
    @mcp.tool(
        name="cos_supervise_record_output",
        description=(
            "Append a formula-agent's output to the session EvidenceBundle "
            "and record the dispatch in formula_dispatches. Call after each "
            "formula-agent returns. status: ok|fail|timeout."
        ),
    )
    @safe_tool
    def cos_supervise_record_output(
        session_id: str,
        task_marker: str,
        persona_id: str,
        formula_id: str,
        output_json: str,
        status: str = "ok",
        latency_ms: int = 0,
    ) -> str:
        # Validate formula_id before any use. A malformed value (e.g. an XML
        # tool-call fragment leaking the arg boundary — `researcher</formula_id>...`)
        # once landed verbatim in the typed column. Reject non-identifier values
        # up front rather than persisting garbage.
        if not formula_id or not re.fullmatch(r"[a-z0-9_]+", formula_id):
            return fail("validation", "formula_id must match [a-z0-9_]+")

        bundle = _load_bundle(session_id, task_marker, persona_id)

        # Data-driven role → bundle-field + Pydantic class (frontmatter SSOT).
        error_detail: str | None = None
        field, cls = _resolve_role_persistence(formula_id)
        if field and cls and status == "ok":
            try:
                parsed = cls.model_validate_json(output_json)
                setattr(bundle, field, parsed)
            except Exception as exc:
                logger.warning("Failed to parse %s output: %s", formula_id, exc)
                bundle.degraded_formulas.append(formula_id)
                status = "fail"
                error_detail = f"{formula_id} parse: {exc}"
        elif status == "timeout":
            bundle.degraded_formulas.append(formula_id)
            error_detail = "timeout"

        # Caller-supplied non-ok status (not a parse failure) carries its reason
        # in output_json — keep a bounded slice so the failure stays diagnosable.
        if status != "ok" and not error_detail:
            error_detail = (output_json or "")[:1000]

        _save_bundle(session_id, bundle)

        output_hash = hashlib.sha256(output_json.encode()).hexdigest()[:16]
        input_hash = hashlib.sha256(f"{session_id}:{formula_id}".encode()).hexdigest()[:16]

        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "INSERT INTO formula_dispatches "
                    "(session_id, task_marker, persona_id, formula_id, input_hash, "
                    "output_hash, latency_ms, status, ts, error) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        session_id,
                        task_marker,
                        persona_id,
                        formula_id,
                        input_hash,
                        output_hash,
                        latency_ms,
                        status,
                        _now_iso(),
                        error_detail,
                    ),
                )
        except Exception as exc:
            logger.debug("formula_dispatches insert failed: %s", exc)

        filled = sum(1 for f in _all_bundle_fields() if getattr(bundle, f, None) is not None)
        # emit trace event so the flowchart replay knows a role completed
        try:
            import tracing

            tracing.emit(
                session_id,
                "role_output_recorded",
                {
                    "formula_id": formula_id,
                    "status": status,
                    "latency_ms": latency_ms,
                    "output_hash": output_hash,
                    "bundle_fields_filled": filled,
                },
                role=formula_id,
            )
        except Exception:
            pass  # tracing must never break caller
        return ok(
            {"formula_id": formula_id, "status": status, "bundle_fields_filled": filled},
            meta={"layer": "routing"},
        )

    return cos_supervise_record_output


# ---------------------------------------------------------------------------
# cos_dispatch_formula
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# cos_ambiguity_check
# ---------------------------------------------------------------------------


def register_cos_ambiguity_check(mcp, db_path):
    @mcp.tool(
        name="cos_ambiguity_check",
        description=(
            "Run the 7-criteria Anti-Ambiguity gate over the session EvidenceBundle. "
            "Returns violations (formula, criterion, detail). Empty list = gate passes. "
            "Fires once at PLAN→EXECUTE; CLEAR 1 tasks skip this check."
        ),
    )
    @safe_tool
    def cos_ambiguity_check(
        session_id: str,
        task_marker: str,
        persona_id: str,
    ) -> str:
        cog = _cog()
        bundle = _load_bundle(session_id, task_marker, persona_id)
        violations = cog.ambiguity_check(bundle)

        # The enforce-anti-ambiguity gate reads this table as the CURRENT ambiguity
        # state for the session, so each check supersedes the prior one: clear old
        # rows first (a pass leaves none → the gate clears) then record this check's.
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute("DELETE FROM ambiguity_violations WHERE session_id = ?", (session_id,))
                for v in violations:
                    conn.execute(
                        "INSERT INTO ambiguity_violations "
                        "(session_id, formula_id, criterion, detail, ts) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            session_id,
                            v["formula"],
                            v["criterion"],
                            v.get("detail", ""),
                            _now_iso(),
                        ),
                    )
        except Exception as exc:
            logger.debug("ambiguity_violations write failed: %s", exc)

        return ok(
            {"violations": violations, "passed": len(violations) == 0},
            meta={"layer": "routing"},
        )

    return cos_ambiguity_check


# ---------------------------------------------------------------------------
# cos_traceability
# ---------------------------------------------------------------------------


def register_cos_traceability(mcp, db_path):
    @mcp.tool(
        name="cos_traceability",
        description=(
            "Read-only audit: verify that tasks have doc anchors and that "
            "recent formula dispatches have matching evidence in the bundle. "
            "Idempotent and non-blocking. scope: task|project."
        ),
    )
    @safe_tool
    def cos_traceability(
        session_id: str,
        task_marker: str,
        persona_id: str,
        scope: str = "task",
    ) -> str:
        gaps = []
        bundle = _load_bundle(session_id, task_marker, persona_id)

        try:
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute(
                    "SELECT formula_id, status FROM formula_dispatches "
                    "WHERE session_id=? ORDER BY ts",
                    (session_id,),
                ).fetchall()
        except Exception:
            rows = []

        dispatched_ids = {r[0] for r in rows if r[1] == "ok"}
        # Data-driven traceability: every dispatched role with a bundle field
        # is checked. Roles missing bundle_field in their frontmatter are skipped
        # (correct behavior — non-persisting roles don't appear in the bundle).
        for fid in dispatched_ids:
            field, _cls = _resolve_role_persistence(fid)
            if field and getattr(bundle, field, None) is None:
                gaps.append({"formula": fid, "detail": "dispatched but no output in bundle"})

        total = len(dispatched_ids)
        score = 1.0 if total == 0 else (total - len(gaps)) / total

        return ok(
            {"gaps": gaps, "redundancies": [], "score": round(score, 2), "scope": scope},
            meta={"layer": "routing"},
        )

    return cos_traceability


# ---------------------------------------------------------------------------
# cos_backtrack_log
# ---------------------------------------------------------------------------


def register_cos_backtrack_log(mcp, db_path):
    @mcp.tool(
        name="cos_backtrack_log",
        description=(
            "Record a backtrack event. Returns {count, advisory, suggested_action, "
            "root_cause_summary}. advisory fires at ≥3/≥5 backtracks. "
            "suggested_action gives a concrete next step when root_cause is supplied. "
            "root_cause_summary shows per-cause counts for this session."
        ),
    )
    @safe_tool
    def cos_backtrack_log(
        session_id: str,
        from_formula: str,
        to_formula: str,
        reason: str,
        task_marker: str = "",
        persona_id: str = "",
        hypothesis: str = "",
        failure_signal: str = "",
        root_cause: str = "",
        corrective_action: str = "",
    ) -> str:
        _VALID_ROOT_CAUSES = set(CANONICAL_REMEDIES)

        # Silently clear invalid root_cause to avoid polluting the enum
        if root_cause and root_cause not in _VALID_ROOT_CAUSES:
            root_cause = "other"

        try:
            with sqlite3.connect(db_path) as conn:
                # Try inserting with anatomy columns (v25); fall back to base schema
                try:
                    conn.execute(
                        "INSERT INTO backtrack_events "
                        "(session_id, from_formula, to_formula, reason, ts, "
                        " hypothesis, failure_signal, root_cause, corrective_action) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            session_id,
                            from_formula,
                            to_formula,
                            reason,
                            _now_iso(),
                            hypothesis or None,
                            failure_signal or None,
                            root_cause or None,
                            corrective_action or None,
                        ),
                    )
                except sqlite3.OperationalError:
                    # v25 columns not yet applied — insert base fields only
                    conn.execute(
                        "INSERT INTO backtrack_events "
                        "(session_id, from_formula, to_formula, reason, ts) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (session_id, from_formula, to_formula, reason, _now_iso()),
                    )
                count = conn.execute(
                    "SELECT COUNT(*) FROM backtrack_events WHERE session_id=?",
                    (session_id,),
                ).fetchone()[0]

                # C1: root_cause_summary — per-cause backtrack counts this session
                root_cause_summary: dict[str, int] = {}
                try:
                    rows = conn.execute(
                        "SELECT root_cause, COUNT(*) AS cnt FROM backtrack_events "
                        "WHERE session_id=? AND root_cause IS NOT NULL "
                        "GROUP BY root_cause",
                        (session_id,),
                    ).fetchall()
                    root_cause_summary = {r[0]: r[1] for r in rows}
                except sqlite3.OperationalError:
                    root_cause_summary = {}  # pre-v25: root_cause column absent

        except Exception as exc:
            return fail("internal", f"backtrack_log failed: {exc}")

        advisory = ""
        if count >= 5:
            advisory = (
                f"Anti-Paralysis: {count} backtracks this session. "
                "Consider narrowing task scope or raising intensity level."
            )
        elif count >= 3:
            advisory = f"Anti-Paralysis: {count} backtracks. Review scope if pattern continues."

        # C2: concrete next step for the supplied root_cause
        suggested_action = CANONICAL_REMEDIES.get(root_cause, "") if root_cause else ""

        # emit trace event for replay
        try:
            import tracing

            tracing.emit(
                session_id,
                "backtrack",
                {
                    "from": from_formula,
                    "to": to_formula,
                    "reason": reason,
                    "count": count,
                },
                role=from_formula,
            )
            if advisory:
                tracing.emit(
                    session_id,
                    "anti_paralysis_warn",
                    {
                        "count": count,
                        "advisory": advisory,
                    },
                )
        except Exception as _exc:
            logger.debug("backtrack tracing skipped: %s", _exc)

        return ok(
            {
                "count": count,
                "advisory": advisory,
                "suggested_action": suggested_action,
                "root_cause_summary": root_cause_summary,
            },
            meta={"layer": "routing"},
        )

    return cos_backtrack_log


# ---------------------------------------------------------------------------
# cos_discovery
# ---------------------------------------------------------------------------


def register_cos_discovery(mcp, db_path):
    @mcp.tool(
        name="cos_discovery",
        description=(
            "Capture a mid-work discovery. decision=backtrack_now triggers an "
            "immediate backtrack recommendation. decision=record_for_later stores "
            "the discovery for session summary review."
        ),
    )
    @safe_tool
    def cos_discovery(
        session_id: str,
        task_marker: str,
        persona_id: str,
        kind: str,
        summary: str,
        impact_assessment: str,
        decision: str,
    ) -> str:
        if decision not in ("backtrack_now", "record_for_later"):
            return fail("validation", "decision must be backtrack_now or record_for_later")

        bundle = _load_bundle(session_id, task_marker, persona_id)
        schemas = _schemas()
        disc = schemas.Discovery(
            kind=kind,
            summary=summary,
            impact_assessment=impact_assessment,
            decision=decision,
            ts=_now_iso(),
        )
        bundle.discoveries.append(disc)
        _save_bundle(session_id, bundle)

        # Also store as observation for session_summary to surface
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "INSERT INTO observations (session_id, kind, content, ts) VALUES (?, ?, ?, ?)",
                    (
                        session_id,
                        f"discovery:{kind}",
                        json.dumps(
                            {"summary": summary, "impact": impact_assessment, "decision": decision}
                        ),
                        _now_iso(),
                    ),
                )
        except Exception as exc:
            logger.debug("observation insert failed: %s", exc)

        return ok(
            {"stored": True, "action_required": decision == "backtrack_now"},
            meta={"layer": "routing"},
        )

    return cos_discovery


# ---------------------------------------------------------------------------
# cos_situation_detect
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# cos_takeover
# ---------------------------------------------------------------------------


def register_cos_takeover(mcp, db_path):
    @mcp.tool(
        name="cos_takeover",
        description=(
            "Bootstrap an existing-project-takeover session: sets the situation "
            "to existing-project-takeover, picks legacy-maintainer persona, "
            "and returns the first dispatch action (Analyst in reverse mode). "
            "Use when inheriting a legacy repo with no docs."
        ),
    )
    @safe_tool
    def cos_takeover(
        session_id: str,
        task_marker: str,
        repo_description: str = "",  # reserved for Researcher pre-seeding in future slice
    ) -> str:
        cog = _cog()
        schemas = _schemas()

        persona_id = "legacy-maintainer"
        situation_id = "existing-project-takeover"

        bundle = schemas.EvidenceBundle(
            task_marker=task_marker,
            persona_id=persona_id,
            situation_id=situation_id,
            intensity="full",
        )
        _save_bundle(session_id, bundle)

        state = schemas.SupervisorState(
            session_id=session_id,
            task_marker=task_marker,
            persona_id=persona_id,
            intensity="full",
            situation_id=situation_id,
            phase="ROUTING",
        )
        first_action = cog.advance(state, bundle)

        return ok(
            {
                "persona_id": persona_id,
                "situation_id": situation_id,
                "first_action": {
                    "action": first_action.action,
                    "formula": first_action.formula,
                    "agent_file": first_action.agent_file,
                    "reason": first_action.reason,
                },
            },
            meta={"layer": "routing"},
        )

    return cos_takeover


# ---------------------------------------------------------------------------
# Registration entry point
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Role-based cognitive routing
# Spec: docs/phase-n-role-based-routing-plan.md §2.6
# ---------------------------------------------------------------------------


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
                    "(session_id, task_marker, persona_id, confidence, reason, intensity) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
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


# ---------------------------------------------------------------------------
# cos_dispatch_formula_run — real-dispatch tool
# ---------------------------------------------------------------------------


def classify_prompt_heuristic(prompt: str) -> dict:
    """Deterministic Cynefin + dimensions heuristic — shared by the
    cos_classify_prompt tool and the hub chat auto-router (no LLM call)."""
    import re as _re

    text = (prompt or "").strip().lower()
    if not text:
        return {
            "complexity": "CLEAR",
            "dimensions": 1,
            "signals": [],
            "hit_domains": [],
            "reasoning": "empty prompt",
        }

    signals: list[str] = []
    complexity = "CLEAR"

    chaotic_re = _re.compile(
        r"\b(p0|p1|outage|down|broken|crashed?|emergency|urgent|"
        r"fire|on[- ]call|paged|rollback (?:now|asap))\b"
    )
    if chaotic_re.search(text):
        complexity = "CHAOTIC"
        signals.append("incident-language")

    complex_re = _re.compile(
        r"\b(best way|explore|experiment|optimi[sz]e|research|novel|"
        r"investigate|figure out|prototype|spike|trade[- ]off|benchmark)\b"
    )
    if complexity == "CLEAR" and complex_re.search(text):
        complexity = "COMPLEX"
        signals.append("exploratory-language")

    complicated_re = _re.compile(
        r"\b(design|architect|integrate|refactor|implement|build|migrat\w*|"
        r"split|merge|extract|generali[sz]e|extend|orchestrat\w*|"
        r"normali[sz]e|denormali[sz]e)\b"
    )
    if complexity == "CLEAR" and complicated_re.search(text):
        complexity = "COMPLICATED"
        signals.append("design-language")

    word_count = len(text.split())
    if complexity == "CLEAR" and word_count > 60:
        complexity = "COMPLICATED"
        signals.append(f"prompt-length={word_count}")

    domain_patterns = {
        "backend": r"\b(api|backend|server|django|fastapi|fiber|endpoint|router|service)\b",
        "frontend": r"\b(frontend|react|next\.?js|nextjs|component|ui|client|page|jsx|tsx)\b",
        "mobile": r"\b(mobile|ios|android|react native|expo|swift|kotlin)\b",
        "ai": r"\b(llm|ai|prompt|embedding|rag|model|completion|token)\b",
        "security": r"\b(security|auth|permission|csrf|xss|sql injection|jwt|oauth|tls|encryption|secret)\b",
        "ops": r"\b(deploy|ci/cd|docker|kubernetes|k8s|infra|monitoring|alert|runbook|sre)\b",
        "docs": r"\b(doc|documentation|readme|spec|playbook|adr)\b",
        "db": r"\b(database|sql|sqlite|postgres|mysql|migration|schema|index|query)\b",
        "graph": r"\b(graph|neo4j|kuzu|node|edge|traversal)\b",
        "test": r"\b(test|testing|pytest|jest|coverage|fixture|mock)\b",
    }
    hit_domains: list[str] = []
    for name, pat in domain_patterns.items():
        if _re.search(pat, text):
            hit_domains.append(name)
    dimensions = max(1, len(hit_domains))
    if dimensions >= 5 and complexity == "CLEAR":
        complexity = "COMPLICATED"
        signals.append(f"multi-dimension={dimensions}")

    trivial_re = _re.compile(r"^(fix typo|update doc(?:string)?|tweak (?:wording|comment))\b")
    if (
        trivial_re.search(text)
        and word_count < 15
        and len(hit_domains) <= 1
        and complexity != "CHAOTIC"
    ):
        complexity = "CLEAR"
        dimensions = 1
        signals = ["trivial-edit-shortcut"]

    reasoning = (
        f"Cynefin: {complexity} ({', '.join(signals) or 'no escalating signals'}); "
        f"dims={dimensions} from domains: {', '.join(hit_domains) or 'none'}"
    )
    return {
        "complexity": complexity,
        "dimensions": dimensions,
        "signals": signals,
        "hit_domains": hit_domains,
        "reasoning": reasoning,
    }


def register_cos_classify_prompt(mcp, db_path):
    """Register cos_classify_prompt — heuristic Cynefin + dimensions classifier.

    Replaces the manual `bash write-state.sh .thinking_os-gate "COMPLICATED 3"`
    step. The agent calls this on the user's prompt and gets back a recorded
    gate without manually counting domains or evaluating Cynefin signals.
    """

    @mcp.tool(
        name="cos_classify_prompt",
        description=(
            "Heuristic Cynefin + dimensions classifier. Reads a user prompt "
            "and returns {complexity, dimensions, reasoning, signals}. "
            "Optionally writes the gate marker so enforce-task-start.sh "
            "passes. Replaces the manual `write-state.sh .thinking_os-gate` "
            "step. Sub-second; deterministic; no LLM call."
        ),
    )
    @safe_tool
    def cos_classify_prompt(
        prompt: str,
        record: bool = True,
        agent_dir: str = "",
    ) -> str:
        import os as _os

        if not (prompt or "").strip():
            return ok(
                {
                    "complexity": "CLEAR",
                    "dimensions": 1,
                    "reasoning": "empty prompt",
                    "signals": [],
                    "recorded": False,
                },
                meta={"layer": "routing"},
            )

        heuristic = classify_prompt_heuristic(prompt)
        complexity = heuristic["complexity"]
        dimensions = heuristic["dimensions"]
        signals = heuristic["signals"]
        hit_domains = heuristic["hit_domains"]
        reasoning = heuristic["reasoning"]

        # Record the gate so enforce-task-start.sh passes — but ONLY when a
        # panel session is resolvable. The MCP server has no per-call panel
        # env, so this succeeds mainly when COS_PANEL_DIR is set (or agent_dir
        # is a real panel dir). It writes the SAME session-prefixed format the
        # strict panel reader (check-state.sh) requires; a bare
        # value or an agent-dir write would be silently rejected and leave a
        # misleading fossil — so we do neither, reporting recorded=false + a
        # shell hint instead. (Fixes the prior wrong-dir/wrong-format
        # /no-trace bug.)
        recorded = False
        record_hint = ""
        if record:
            panel_dir = _os.environ.get("COS_PANEL_DIR") or agent_dir
            sid = ""
            if panel_dir:
                sid_file = Path(panel_dir) / "session-id"
                if sid_file.exists():
                    try:
                        sid = sid_file.read_text(encoding="utf-8").strip().split(" ")[0]
                    except OSError:
                        sid = ""
            if panel_dir and sid:
                try:
                    gate_path = Path(panel_dir) / ".thinking_os-gate"
                    gate_path.parent.mkdir(parents=True, exist_ok=True)
                    tmp_path = gate_path.with_name(".thinking_os-gate.tmp")
                    tmp_path.write_text(f"{sid} {complexity} {dimensions}\n", encoding="utf-8")
                    tmp_path.replace(gate_path)
                    recorded = True
                    try:
                        import tracing

                        tracing.emit(
                            sid,
                            "classify",
                            {"complexity": complexity, "dimensions": dimensions},
                        )
                    except Exception as exc:
                        from core.logging_os import swallow_safe

                        swallow_safe("thinking_os.cognition", "classify trace emit failed", exc=exc)
                except OSError:
                    recorded = False
            if not recorded:
                record_hint = (
                    "gate not recorded (no panel session context from MCP); "
                    "record it in your shell: write-state.sh .thinking_os-gate "
                    f'"{complexity} {dimensions}"'
                )

        # Discoverability nudge (TASK-509): a COMPLICATED+ gate needs the
        # cognition surface (role composition / formula dispatch, Rule 15), but a
        # lean profile may have disabled it. Surface the one-liner to re-enable
        # rather than letting the agent hit a module_disabled wall mid-plan.
        nudge = ""
        if (
            complexity in ("COMPLICATED", "COMPLEX")
            and _gated_module("cos_compose_chain") == "cognition"
        ):
            nudge = (
                f"{complexity} work but the cognition module is OFF — role "
                "composition / formula dispatch are unavailable. Enable it with "
                "`cos module enable cognition` (or scaffold with `--profile full`)."
            )

        return ok(
            {
                "complexity": complexity,
                "dimensions": dimensions,
                "reasoning": reasoning,
                "signals": signals,
                "domains": hit_domains,
                "recorded": recorded,
                "record_hint": record_hint,
                "nudge": nudge,
            },
            meta={"layer": "routing"},
        )

    return cos_classify_prompt


def register_cos_supervision_config(mcp, db_path):
    @mcp.tool(
        name="cos_supervision_config",
        description=(
            "Show, enable, disable, or partially configure the current project's "
            "adapter-neutral supervision policy without requiring Hub."
        ),
    )
    @safe_tool
    def cos_supervision_config(
        action: str = "show",
        mode: str = "",
        complexity_threshold: str = "",
        fallback_policy: str = "",
        max_parallel: int = 0,
        cooldown_default_seconds: int = 0,
        cooldown_maximum_seconds: int = 0,
        orchestrator_adapter: str = "",
        orchestrator_model: str = "",
        orchestrator_effort: str = "",
        clear_orchestrator: bool = False,
        role: str = "",
        role_adapter: str = "",
        role_model: str = "",
        role_effort: str = "",
        clear_role: bool = False,
    ) -> str:
        """Manage the normalized project supervision policy without Hub."""
        from thinking_os import supervision

        normalized_action = action.strip().lower()
        if normalized_action not in {"show", "enable", "disable", "set"}:
            return fail("validation", "action must be show, enable, disable, or set")
        root = supervision.current_project_root()
        if normalized_action == "show":
            return ok(supervision.policy_snapshot(root), meta={"layer": "routing"})
        if normalized_action in {"enable", "disable"}:
            try:
                supervision.update_policy(root, {"enabled": normalized_action == "enable"})
            except ValueError as exc:
                return fail("validation", str(exc))
            return ok(supervision.policy_snapshot(root), meta={"layer": "routing"})

        patch: dict[str, object] = {}
        for key, value in (
            ("mode", mode),
            ("complexity_threshold", complexity_threshold),
            ("fallback_policy", fallback_policy),
        ):
            if value:
                patch[key] = value
        if max_parallel:
            patch["max_parallel"] = max_parallel
        cooldown: dict[str, int] = {}
        if cooldown_default_seconds:
            cooldown["default_seconds"] = cooldown_default_seconds
        if cooldown_maximum_seconds:
            cooldown["maximum_seconds"] = cooldown_maximum_seconds
        if cooldown:
            patch["cooldown"] = cooldown
        orchestrator = {
            key: value
            for key, value in (
                ("adapter", orchestrator_adapter),
                ("model", orchestrator_model),
                ("effort", orchestrator_effort),
            )
            if value
        }
        if orchestrator:
            patch["orchestrator"] = orchestrator
        role_target = {
            key: value
            for key, value in (
                ("adapter", role_adapter),
                ("model", role_model),
                ("effort", role_effort),
            )
            if value
        }
        if (role_target or clear_role) and not role.strip():
            return fail("validation", "role is required with role fields or clear_role")
        if clear_role and role_target:
            return fail(
                "validation", "clear_role cannot be combined with role adapter/model/effort"
            )
        if clear_orchestrator and orchestrator:
            return fail(
                "validation",
                "clear_orchestrator cannot be combined with orchestrator adapter/model/effort",
            )
        if role_target:
            patch["roles"] = {role.strip(): role_target}
        if not patch and not clear_role and not clear_orchestrator:
            return fail("validation", "set requires at least one policy field")
        try:
            supervision.update_policy(
                root,
                patch,
                clear_role=role.strip() if clear_role else "",
                clear_orchestrator=clear_orchestrator,
            )
        except ValueError as exc:
            return fail("validation", str(exc))
        return ok(supervision.policy_snapshot(root), meta={"layer": "routing"})

    return cos_supervision_config


def register_all(mcp, db_path: str) -> None:
    """Register all cognition tools with the MCP server."""
    register_cos_supervise(mcp, db_path)
    register_cos_supervise_record_output(mcp, db_path)
    register_cos_dispatch_formula(mcp, db_path)
    register_cos_ambiguity_check(mcp, db_path)
    register_cos_traceability(mcp, db_path)
    register_cos_backtrack_log(mcp, db_path)
    register_cos_discovery(mcp, db_path)
    register_cos_situation_detect(mcp, db_path)
    register_cos_takeover(mcp, db_path)
    # Additions
    register_cos_analyze_task(mcp, db_path)
    register_cos_compose_chain(mcp, db_path)
    register_cos_role_info(mcp, db_path)
    # real dispatch (opt-in, costly)
    register_cos_dispatch_formula_run(mcp, db_path)
    register_cos_dispatch_parallel_run(mcp, db_path)
    # auto-Classify (eliminates manual gate recording)
    register_cos_classify_prompt(mcp, db_path)
    register_cos_supervision_config(mcp, db_path)
