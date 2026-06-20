"""Coding OS — Formula-agent supervisor MCP tools."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools._shared import fail, ok, safe_tool

logger = logging.getLogger("coding_os.tools.cognition")


# Lazy import of cognition — avoids circular at module load time
def _cog():
    import cognition as _mod

    return _mod


def _schemas():
    import cognition_schemas as _mod

    return _mod


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_role_persistence_cache: dict[str, tuple[str | None, Any]] | None = None


def _resolve_role_persistence(role_id: str) -> tuple[str | None, Any]:
    global _role_persistence_cache
    if _role_persistence_cache is None:
        _role_persistence_cache = {}
        cog = _cog()
        schemas_mod = _schemas()
        # Primary source: ROLE_OUTPUT_CLASSES registry in cognition_schemas.
        # Frontmatter `output_schema:` / `bundle_field:` override on a per-
        # role basis (lets a deployment swap the Pydantic class without
        # editing the registry).
        for rid, cls in schemas_mod.ROLE_OUTPUT_CLASSES.items():
            _role_persistence_cache[rid] = (rid, cls)

        try:
            registry = cog.load_agent_registry()
        except Exception as exc:
            logger.warning("agent registry load failed: %s", exc)
            registry = {}
        for rid, meta in registry.items():
            if not isinstance(meta, dict):
                continue
            field = meta.get("bundle_field") or rid
            schema_ref = meta.get("output_schema")
            cls = _role_persistence_cache.get(rid, (None, None))[1]
            if isinstance(schema_ref, str) and schema_ref.strip():
                cls_name = schema_ref.split(".")[-1].strip()
                if cls_name.isidentifier():
                    override = getattr(schemas_mod, cls_name, None)
                    if override is not None:
                        cls = override
            _role_persistence_cache[rid] = (field, cls)
    return _role_persistence_cache.get(role_id, (None, None))


def _all_bundle_fields() -> set[str]:
    """Bundle field names from every registered role (data-driven)."""
    cog = _cog()
    try:
        registry = cog.load_agent_registry()
    except Exception:
        return set()
    out: set[str] = set()
    for rid, meta in registry.items():
        if isinstance(meta, dict):
            out.add(str(meta.get("bundle_field") or rid))
    return out


def _resolve_agent_dir() -> Path:
    import os as _os

    explicit = _os.environ.get("COS_AGENT_DIR")
    if explicit:
        d = Path(explicit)
        d.mkdir(parents=True, exist_ok=True)
        return d
    agent = _os.environ.get("COS_AGENT") or "claude"
    d = Path(".coding-os") / agent
    d.mkdir(parents=True, exist_ok=True)
    return d


def _bundle_path(session_id: str) -> Path:
    agent_dir = _resolve_agent_dir()
    return agent_dir / f"evidence_bundle_{session_id}.json"


def _load_bundle(session_id: str, task_marker: str, persona_id: str) -> Any:
    schemas = _schemas()
    path = _bundle_path(session_id)
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return schemas.EvidenceBundle.model_validate(data)
        except Exception as exc:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            corrupt = path.with_suffix(f".corrupt-{ts}.json")
            path.rename(corrupt)
            logger.warning("Corrupted bundle quarantined to %s: %s", corrupt, exc)
    return schemas.EvidenceBundle(task_marker=task_marker, persona_id=persona_id)


def _save_bundle(session_id: str, bundle: Any) -> None:
    path = _bundle_path(session_id)
    path.write_text(bundle.model_dump_json(indent=2))


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


def register_cos_dispatch_formula(mcp, db_path):
    @mcp.tool(
        name="cos_dispatch_formula",
        description=(
            "Return the rendered agent prompt and input slice for a formula-agent. "
            "The main agent uses this to construct the subagent dispatch. "
            "Does NOT spawn the subagent — returns prompt text only."
        ),
    )
    @safe_tool
    def cos_dispatch_formula(
        formula_id: str,
        session_id: str,
        task_marker: str,
        persona_id: str,
        intensity: str = "standard",
    ) -> str:
        cog = _cog()
        agents = cog.load_agent_registry()
        meta = agents.get(formula_id)
        if not meta:
            return fail("not_found", f"No agent file for formula {formula_id}")

        agent_file = f"src/core/thinking_os/agents/{meta['_file']}"
        agent_path = Path(__file__).resolve().parent.parent / "agents" / meta["_file"]
        prompt_text = agent_path.read_text() if agent_path.exists() else ""

        bundle = _load_bundle(session_id, task_marker, persona_id)
        input_slice = cog.build_input_slice(formula_id, bundle)
        input_slice["intensity_steps"] = cog._intensity_steps(formula_id, intensity)

        return ok(
            {
                "formula_id": formula_id,
                "agent_file": agent_file,
                "prompt_text": prompt_text,
                "input_slice": input_slice,
                "timeout_s": meta.get("timeout_s", 90),
                "model_pref": meta.get("model_pref", {}),
            },
            meta={"layer": "routing"},
        )

    return cos_dispatch_formula


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
                conn.execute(
                    "DELETE FROM ambiguity_violations WHERE session_id = ?", (session_id,)
                )
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
        _VALID_ROOT_CAUSES = {
            "wrong_model",
            "scope_too_large",
            "missing_context",
            "tool_failure",
            "spec_ambiguity",
            "env_mismatch",
            "other",
        }
        _SUGGESTED_ACTIONS: dict[str, str] = {
            "wrong_model": "Use cos_route_model to select the right model before re-dispatching.",
            "scope_too_large": "Decompose via cos_task_create and pick the smallest slice.",
            "missing_context": "Run cos_doc_search or cos_search to load relevant context first.",
            "tool_failure": "Run cos_health to verify permissions/env vars, then retry with explicit paths.",
            "spec_ambiguity": "Log open questions via cos_discovery and resolve with user before implementing.",
            "env_mismatch": "Run cos doctor to validate environment config, then restart the session.",
            "other": "Re-classify the problem (Cynefin gate) and review the Anti-Paralysis advisory.",
        }

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
        suggested_action = _SUGGESTED_ACTIONS.get(root_cause, "") if root_cause else ""

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


def _persist_dispatch_output(
    *,
    session_id: str,
    task_marker: str,
    persona_id: str,
    formula_id: str,
    output_json: dict,
    status: str,
    latency_ms: int,
    db_path: str,
) -> int:
    bundle = _load_bundle(session_id, task_marker, persona_id)
    # Data-driven role → bundle field + Pydantic class resolution.
    # Role frontmatter declares `output_schema: cognition.<X>Output`;
    # `bundle_field` defaults to role id but can be overridden in frontmatter.
    field, cls = _resolve_role_persistence(formula_id)
    validation_failed = False
    if field and cls and status == "ok":
        try:
            parsed = cls.model_validate(output_json)
            setattr(bundle, field, parsed)
        except Exception as exc:
            # T1.6 — Pydantic validation runs BEFORE persistence.
            # On failure: mark degraded, skip the formula_dispatches INSERT
            # entirely (row would carry untrusted output_hash). Bundle still
            # saved with degraded_formulas marker so the supervisor can
            # backtrack.
            logger.warning(
                "Failed to validate %s output against schema: %s",
                formula_id,
                exc,
            )
            bundle.degraded_formulas.append(formula_id)
            status = "fail"
            validation_failed = True
    elif status == "timeout":
        bundle.degraded_formulas.append(formula_id)

    _save_bundle(session_id, bundle)

    # T1.6: skip the dispatch row INSERT when schema validation failed.
    # Returning the bundle field count keeps the caller signature stable.
    if validation_failed:
        return sum(1 for f in _all_bundle_fields() if getattr(bundle, f, None) is not None)

    raw = json.dumps(output_json, sort_keys=True, default=str).encode()
    output_hash = hashlib.sha256(raw).hexdigest()[:16]
    input_hash = hashlib.sha256(f"{session_id}:{formula_id}".encode()).hexdigest()[:16]
    # pull telemetry the Claude dispatcher stamps
    # into output_json["_meta"] (cost_usd, usage, model_usage, tool_calls,
    # tool_failures) and persist into the v23 columns. JSON-encoded so
    # the schema migration stays append-only — readers parse on demand.
    meta = output_json.get("_meta") if isinstance(output_json, dict) else None
    meta = meta if isinstance(meta, dict) else {}
    cost_usd_raw = meta.get("total_cost_usd")
    if isinstance(cost_usd_raw, (int, float)):
        cost_usd_val: float | None = float(cost_usd_raw)
    else:
        cost_usd_val = None

    def _jsonb(value: Any) -> str | None:
        if value is None:
            return None
        try:
            return json.dumps(value, default=str, sort_keys=True)
        except (TypeError, ValueError):
            return None

    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO formula_dispatches "
                "(session_id, task_marker, persona_id, formula_id, input_hash, "
                "output_hash, latency_ms, status, ts, "
                "cost_usd, budget_usd, usage_jsonb, model_usage_jsonb, "
                "tool_calls_jsonb, tool_failures_jsonb, "
                "sub_session_id, model, checkpoints_jsonb, error) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                    cost_usd_val,
                    meta.get("budget_usd"),
                    _jsonb(meta.get("usage")),
                    _jsonb(meta.get("model_usage")),
                    _jsonb(meta.get("tool_calls")),
                    _jsonb(meta.get("tool_failures")),
                    meta.get("session_id"),
                    meta.get("model"),
                    _jsonb(meta.get("checkpoints")),
                    str(meta.get("error"))[:1000] if meta.get("error") else None,
                ),
            )
    except Exception as exc:
        logger.debug("formula_dispatches insert failed: %s", exc)

    return sum(1 for f in _all_bundle_fields() if getattr(bundle, f, None) is not None)


def _emit_dispatch_metrics_safe(
    *,
    db_path: str,
    formula_id: str,
    status: str,
    latency_ms: int,
    output_json: dict,
) -> None:
    import sqlite3 as _sqlite3

    try:
        from tools.metrics import metric_record  # type: ignore[import]

        _outcome_map = {
            "ok": "success",
            "timeout": "blocked",
            "error": "partial",
            "skipped": "partial",
        }
        outcome = _outcome_map.get(status, "partial")
        meta = output_json.get("_meta") if isinstance(output_json, dict) else {}
        meta = meta if isinstance(meta, dict) else {}
        model_used = meta.get("model") or None
        with _sqlite3.connect(db_path) as conn:
            metric_record(
                conn,
                agent_type="dispatch",
                outcome=outcome,
                duration_ms=latency_ms,
                domain=formula_id,
                model=model_used,
                complexity="CLEAR",
            )
    except Exception as exc:
        logger.debug("dispatch metric emit failed: %s", exc)


def _preset_role_hint(session_id: str, formula_id: str, db_path) -> dict:
    # Tier-2 lookup (claude-sdk.md §7.3): the session's composed preset is
    # read back from persona_selections (preset_id lives in its task_marker
    # column — see register_cos_compose_chain's INSERT), then that preset's
    # roles_adapter_hints[formula_id]. Fail-open: hints are advisory.
    if not db_path:
        return {}
    try:
        import sqlite3 as _sqlite3

        conn = _sqlite3.connect(db_path)
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

        from tools.routing import route_model

        conn = _sqlite3.connect(db_path)
        try:
            result = route_model(conn, complexity=complexity.strip().upper())
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
) -> str:
    level = complexity.strip().lower()
    hint_pref = _preset_role_hint(session_id, formula_id, db_path).get("model_pref") or {}
    role_pref = meta.get("model_pref") or {}
    for candidate, source in (
        (model.strip(), "explicit"),
        (hint_pref.get(level, ""), "preset_hint"),
        (role_pref.get(level, ""), "role_pref"),
        (_empirical_model(complexity, db_path), "empirical"),
    ):
        if candidate:
            logger.info(
                "dispatch model resolved for %s: %s via %s", formula_id, candidate, source
            )
            return candidate
    return ""


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

    resolved_model = _resolve_dispatch_model(
        formula_id, session_id, meta, model, complexity, db_path
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
    )


def register_cos_dispatch_formula_run(mcp, db_path):
    @mcp.tool(
        name="cos_dispatch_formula_run",
        description=(
            "EXPLICIT, OPT-IN sub-agent spawn for one role. Costs ~5k tokens "
            "per call (system prompt + input slice + completion) and rebuilds "
            "context inside the sub-agent. PREFER lazy-loading: read "
            "src/core/thinking_os/agents/<role>.md inline and produce the output "
            "schema yourself — same accuracy, far fewer tokens, no context "
            "rebuild penalty. Use this tool only when (a) the role's work is "
            "long-running and would dominate the main loop, or (b) you "
            "explicitly want a separate session for parallelism. If no SDK is "
            "available, returns status='skipped' and the main agent should "
            "execute the role's procedure inline."
        ),
    )
    @safe_tool
    def cos_dispatch_formula_run(
        formula_id: str,
        session_id: str,
        task_marker: str,
        persona_id: str,
        intensity: str = "standard",
        timeout_s: float | None = None,
        model: str = "",
        complexity: str = "",
    ) -> str:
        import asyncio as _asyncio

        from thinking_os import budget as _budget, dispatcher as _disp

        gate = _budget.check(db_path)
        if not gate.allowed:
            return fail("budget", gate.reason)

        try:
            req = _build_dispatch_request(
                formula_id,
                session_id,
                task_marker,
                persona_id,
                intensity,
                timeout_s,
                model,
                complexity,
                db_path,
            )
        except Exception as exc:
            return fail("validation", f"failed to build request: {exc}")

        d = _disp.get_dispatcher(request=req)

        # Trace event — visible in cos cognition trace replay so the
        # flowchart shows the actual sub-agent execution span.
        try:
            import tracing

            tracing.emit(
                session_id,
                "dispatch_started",
                {
                    "formula_id": formula_id,
                    "dispatcher_name": getattr(d, "name", "unknown"),
                    "intensity": intensity,
                    "model": req.model,
                    "long_context": req.long_context,
                },
                role=formula_id,
                phase="EXECUTE",
            )
        except Exception as exc:
            logger.debug("dispatch_started trace emit failed: %s", exc)

        try:
            result = _asyncio.run(d.dispatch(req))
        except RuntimeError as exc:
            # Nested loop — fall back to a fresh thread-owned loop
            if "already running" in str(exc):
                import threading

                box: dict = {}

                def _runner():
                    loop = _asyncio.new_event_loop()
                    try:
                        box["result"] = loop.run_until_complete(d.dispatch(req))
                    finally:
                        loop.close()

                t = threading.Thread(target=_runner, daemon=True)
                t.start()
                t.join(timeout=req.timeout_s + 10)
                if "result" not in box:
                    return fail("transient", "dispatcher thread did not return")
                result = box["result"]
            else:
                return fail("internal", f"asyncio.run failed: {exc}")

        filled = 0
        if result.status in ("ok", "timeout") and result.output_json:
            filled = _persist_dispatch_output(
                session_id=session_id,
                task_marker=task_marker,
                persona_id=persona_id,
                formula_id=formula_id,
                output_json=result.output_json,
                status=result.status,
                latency_ms=result.latency_ms,
                db_path=db_path,
            )

        # T2.5 + T8.4: emit dispatch cost and duration as coding-os metrics
        # so cos_metric_trend surfaces spend over time.
        _emit_dispatch_metrics_safe(
            db_path=db_path,
            formula_id=formula_id,
            status=result.status,
            latency_ms=result.latency_ms,
            output_json=result.output_json,
        )

        # Trace event — pairs with dispatch_started above so the cognition
        # replay shows the full sub-agent execution span (not just supervisor
        # routing decision).
        try:
            import tracing

            _meta = result.output_json.get("_meta") if isinstance(result.output_json, dict) else {}
            _meta = _meta if isinstance(_meta, dict) else {}
            tracing.emit(
                session_id,
                "dispatch_completed",
                {
                    "formula_id": formula_id,
                    "status": result.status,
                    "latency_ms": result.latency_ms,
                    "cost_usd": _meta.get("total_cost_usd"),
                    "sub_session_id": _meta.get("session_id"),
                    "model": _meta.get("model"),
                    "bundle_fields_filled": filled,
                    "error": result.error,
                },
                role=formula_id,
                phase="EXECUTE",
            )
        except Exception as exc:
            logger.debug("dispatch_completed trace emit failed: %s", exc)

        return ok(
            {
                "status": result.status,
                "formula_id": result.formula_id,
                "dispatcher_name": result.dispatcher_name,
                "latency_ms": result.latency_ms,
                "output_json": result.output_json,
                "error": result.error,
                "bundle_fields_filled": filled,
            },
            meta={"layer": "dispatch"},
        )

    return cos_dispatch_formula_run


def register_cos_dispatch_parallel_run(mcp, db_path):
    @mcp.tool(
        name="cos_dispatch_parallel_run",
        description=(
            "Spawn multiple formula-agents concurrently via asyncio.gather. "
            "Use when the supervisor returns action='dispatch_parallel' "
            "(e.g. security_auditor layers). Each output is persisted to the bundle. "
            "Returns list of DispatchResults in input order."
        ),
    )
    @safe_tool
    def cos_dispatch_parallel_run(
        formula_ids: list[str],
        session_id: str,
        task_marker: str,
        persona_id: str,
        intensity: str = "standard",
        timeout_s: float | None = None,
        model: str = "",
        complexity: str = "",
    ) -> str:
        import asyncio as _asyncio

        from thinking_os import budget as _budget, dispatcher as _disp

        if not formula_ids:
            return fail("validation", "formula_ids must be non-empty")

        gate = _budget.check(db_path)
        if not gate.allowed:
            return fail("budget", gate.reason)

        try:
            requests = [
                _build_dispatch_request(
                    fid,
                    session_id,
                    task_marker,
                    persona_id,
                    intensity,
                    timeout_s,
                    model,
                    complexity,
                    db_path,
                )
                for fid in formula_ids
            ]
        except Exception as exc:
            return fail("validation", f"failed to build requests: {exc}")

        d = _disp.get_dispatcher()

        async def _gather_all():
            return await _asyncio.gather(
                *(d.dispatch(req) for req in requests),
                return_exceptions=True,
            )

        import time as _time

        t0 = _time.monotonic()
        try:
            gathered = _asyncio.run(_gather_all())
        except RuntimeError:
            # Nested-loop fallback: run in a dedicated thread with fresh loop
            import threading

            box: dict = {}

            def _runner():
                loop = _asyncio.new_event_loop()
                try:
                    box["result"] = loop.run_until_complete(_gather_all())
                finally:
                    loop.close()

            t = threading.Thread(target=_runner, daemon=True)
            t.start()
            deadline = max(req.timeout_s for req in requests) + 10
            t.join(timeout=deadline)
            gathered = box.get("result", [])
        wall_ms = int((_time.monotonic() - t0) * 1000)

        results = []
        ok_count = 0
        for req, outcome in zip(requests, gathered):
            if isinstance(outcome, Exception):
                results.append(
                    {
                        "status": "error",
                        "formula_id": req.formula_id,
                        "error": f"{type(outcome).__name__}: {outcome}",
                        "dispatcher_name": d.name,
                        "latency_ms": 0,
                        "output_json": {},
                        "bundle_fields_filled": 0,
                    }
                )
                continue
            filled = 0
            if outcome.status == "ok" and outcome.output_json:
                filled = _persist_dispatch_output(
                    session_id=session_id,
                    task_marker=task_marker,
                    persona_id=persona_id,
                    formula_id=outcome.formula_id,
                    output_json=outcome.output_json,
                    status=outcome.status,
                    latency_ms=outcome.latency_ms,
                    db_path=db_path,
                )
                ok_count += 1
            results.append(
                {
                    "status": outcome.status,
                    "formula_id": outcome.formula_id,
                    "dispatcher_name": outcome.dispatcher_name,
                    "latency_ms": outcome.latency_ms,
                    "output_json": outcome.output_json,
                    "error": outcome.error,
                    "bundle_fields_filled": filled,
                }
            )

        return ok(
            {
                "results": results,
                "parallel_wall_ms": wall_ms,
                "ok_count": ok_count,
                "total": len(results),
            },
            meta={"layer": "dispatch"},
        )

    return cos_dispatch_parallel_run


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

        return ok(
            {
                "complexity": complexity,
                "dimensions": dimensions,
                "reasoning": reasoning,
                "signals": signals,
                "domains": hit_domains,
                "recorded": recorded,
                "record_hint": record_hint,
            },
            meta={"layer": "routing"},
        )

    return cos_classify_prompt


def register_all(mcp, db_path: str) -> None:
    """Register all 15 cognition tools with the MCP server."""
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
