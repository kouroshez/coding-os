"""Bundle persistence, the ``formula_dispatches`` row and dispatch metric emission."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from typing import Any

from ._cognition_shared import (
    _all_bundle_fields,
    _load_bundle,
    _now_iso,
    _resolve_role_persistence,
    _save_bundle,
)

logger = logging.getLogger("thinking_os.cognition")


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
    raw_transcript: str | None = None,
    resolved_route: dict[str, Any] | None = None,
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

    # The adapter's own report wins — only the runtime knows whether it honoured
    # the requested model. But core resolved the route, so a runtime that does
    # not echo it back can no longer leave the row's provenance NULL: that is
    # how every historical row ended up structurally complete and route-blind.
    route = resolved_route or {}
    # The adapter's own message wins, but the dispatcher's result.error is the
    # fallback: an `error` row whose message is NULL records that something
    # failed while discarding the only field that says what.
    _reported_error = meta.get("error") or route.get("error")
    _error_text = str(_reported_error)[:1000] if _reported_error else None

    def _from_route(key: str) -> Any:
        reported = meta.get(key)
        return reported if reported not in (None, "") else route.get(key)

    try:
        with sqlite3.connect(db_path, timeout=10) as conn:
            conn.execute(
                "INSERT INTO formula_dispatches "
                "(session_id, task_marker, persona_id, formula_id, input_hash, "
                "output_hash, latency_ms, status, ts, "
                "cost_usd, budget_usd, usage_jsonb, model_usage_jsonb, "
                "tool_calls_jsonb, tool_failures_jsonb, "
                "sub_session_id, model, checkpoints_jsonb, error, raw_transcript, "
                "adapter, effort, error_category, retry_after_s, health_state, health_probe) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                    _from_route("model"),
                    _jsonb(meta.get("checkpoints")),
                    _error_text,
                    raw_transcript[:50000] if raw_transcript else None,
                    _from_route("adapter"),
                    _from_route("effort"),
                    _from_route("error_category"),
                    _from_route("retry_after_s"),
                    _from_route("health_state"),
                    1 if _from_route("health_probe") else 0,
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
    resolved_route: dict[str, Any] | None = None,
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
        # A NULL model here is not cosmetic: this row is the empirical history
        # that routing precedence step 6 consults, so an unnamed model means
        # routing can never learn from the run it just paid for.
        model_used = meta.get("model") or (resolved_route or {}).get("model") or None
        with _sqlite3.connect(db_path, timeout=10) as conn:
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
