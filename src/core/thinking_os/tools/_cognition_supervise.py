"""Supervisor loop: advance the chain, record role output, set the policy.

These four tools own the SupervisorState/EvidenceBundle write path and the
policy that governs it, so a change to the loop and a change to what the loop
is allowed to do land in the same file.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3

from tools._shared import fail, ok, safe_tool

from ._cognition_dispatch import _preset_role_hint
from ._cognition_shared import (
    _all_bundle_fields,
    _cog,
    _load_bundle,
    _now_iso,
    _resolve_role_persistence,
    _save_bundle,
    _schemas,
)

logger = logging.getLogger("coding_os.tools.cognition")


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
