"""Audit gates: ambiguity, traceability, backtrack, discovery.

Read-mostly checks over an existing bundle plus the backtrack ledger. They share
the canonical-remedy table and change with the reasoning protocol, not with the
dispatcher.
"""

from __future__ import annotations

import json
import logging
import sqlite3

from tools._shared import fail, ok, safe_tool

from ._cognition_shared import (
    _cog,
    _load_bundle,
    _now_iso,
    _resolve_role_persistence,
    _save_bundle,
    _schemas,
)

logger = logging.getLogger("coding_os.tools.cognition")


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
