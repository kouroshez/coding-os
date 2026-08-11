"""Adapter capacity breaker — the `adapter_health` state machine.

Owns one thing: cooling_down → half_open → healthy, the single-probe lease, the
escalating backoff, and the per-pool scope keys the breaker meters against. The
routing policy document it reads its cooldown defaults from lives in
`_supervision_policy`, re-exported here so `supervision` stays the one import
every caller needs. Contract: src/core/rules/model-routing.md.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from thinking_os._supervision_policy import (
    COMPLEXITY_ORDER as COMPLEXITY_ORDER,
    DEFAULT_MODEL_ROUTING as DEFAULT_MODEL_ROUTING,
    AdapterTargetPolicy as AdapterTargetPolicy,
    CooldownPolicy as CooldownPolicy,
    ModelRoutingPolicy as ModelRoutingPolicy,
    _accepts_effort as _accepts_effort,
    _accepts_model as _accepts_model,
    _target_errors as _target_errors,
    complexity_rank as complexity_rank,
    current_project_root as current_project_root,
    eligible_records as eligible_records,
    enabled as enabled,
    load_policy as load_policy,
    normalize_policy as normalize_policy,
    policy_applies as policy_applies,
    policy_snapshot as policy_snapshot,
    role_policy as role_policy,
    update_policy as update_policy,
    validate_targets as validate_targets,
)
from thinking_os.adapter_registry import AdapterRecord

logger = logging.getLogger("coding_os.supervision")


@dataclass(frozen=True)
class HealthDecision:
    allowed: bool
    state: str
    retry_after_s: int | None = None
    probe: bool = False
    reason: str = ""


def capacity_key(record: AdapterRecord, model: str | None) -> str:
    # Providers meter separately per model pool, so one pool's limit must not
    # take the others out of service. An adapter that declares no pool is
    # treated as a single one, keyed by its id exactly as before.
    wanted = str(model or "")
    for entry in record.models:
        if str(entry.get("id")) == wanted and entry.get("bucket"):
            return f"{record.id}:{entry['bucket']}"
    return record.id


def adapter_of(scope: str) -> str:
    return scope.split(":", 1)[0]


# Back to healthy, not half_open: the cooldown already expired and nothing here
# is evidence of a capacity problem. failure_count survives so escalating
# backoff is not reset by an unrelated error.
_RELEASE_PROBE_SQL = (
    "UPDATE adapter_health SET state = 'healthy', probe_lease_until = NULL, "
    "cooldown_until = NULL, reason = NULL, updated_at = ? "
    "WHERE adapter_id = ? AND state = 'half_open'"
)


def release_probe(db_path: str | Path, scope: str, now: float | None = None) -> None:
    clock = time.time() if now is None else now
    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            conn.execute(_RELEASE_PROBE_SQL, (clock, scope))
            conn.commit()
    except sqlite3.OperationalError as exc:
        logger.debug("probe release unavailable for %s: %s", scope, exc)


def check_capacity(
    db_path: str | Path,
    scope: str,
    *,
    now: float | None = None,
    lease_seconds: float = 300.0,
) -> HealthDecision:
    adapter_id = scope
    clock = time.time() if now is None else now
    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT state, cooldown_until, probe_lease_until, reason "
                "FROM adapter_health WHERE adapter_id = ?",
                (adapter_id,),
            ).fetchone()
            if row is None or row[0] == "healthy":
                return HealthDecision(True, "healthy")
            state, cooldown_until, probe_lease_until, reason = row
            cooldown_until = float(cooldown_until or 0)
            probe_lease_until = float(probe_lease_until or 0)
            if state == "cooling_down" and cooldown_until > clock:
                return HealthDecision(
                    False,
                    state,
                    max(1, int(cooldown_until - clock + 0.999)),
                    reason=str(reason or "capacity unavailable"),
                )
            if state in ("cooling_down", "half_open") and probe_lease_until > clock:
                return HealthDecision(
                    False,
                    "half_open",
                    max(1, int(probe_lease_until - clock + 0.999)),
                    reason="capacity recovery probe already running",
                )
            # The lease must outlive the probe dispatch itself. A lease shorter
            # than the run lets a second caller in mid-probe — two live requests
            # against the provider that just rate-limited us, which is the retry
            # storm the breaker exists to prevent.
            lease_until = clock + max(1.0, lease_seconds)
            conn.execute(
                "UPDATE adapter_health SET state = 'half_open', probe_lease_until = ?, updated_at = ? "
                "WHERE adapter_id = ?",
                (lease_until, clock, adapter_id),
            )
            conn.commit()
            return HealthDecision(True, "half_open", probe=True, reason=str(reason or ""))
    except sqlite3.OperationalError as exc:
        logger.debug("capacity check unavailable for %s: %s", adapter_id, exc)
        return HealthDecision(True, "unknown")


def record_result(
    db_path: str | Path,
    adapter_id: str,
    *,
    success: bool,
    error_category: str | None = None,
    retryable: bool = False,
    retry_after_s: int | None = None,
    reason: str = "",
    policy: dict[str, Any] | None = None,
    now: float | None = None,
) -> None:
    clock = time.time() if now is None else now
    try:
        from thinking_os.sanitizer import redact_secrets

        safe_reason = redact_secrets(reason)[0][:500]
    except Exception as exc:
        logger.debug("capacity reason redaction unavailable: %s", exc)
        safe_reason = "capacity unavailable"
    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            if success:
                conn.execute(
                    "INSERT INTO adapter_health "
                    "(adapter_id, state, failure_count, cooldown_until, probe_lease_until, reason, updated_at) "
                    "VALUES (?, 'healthy', 0, NULL, NULL, NULL, ?) "
                    "ON CONFLICT(adapter_id) DO UPDATE SET state = 'healthy', failure_count = 0, "
                    "cooldown_until = NULL, probe_lease_until = NULL, reason = NULL, updated_at = excluded.updated_at",
                    (adapter_id, clock),
                )
                conn.commit()
                return
            if error_category != "capacity" or not retryable:
                # A probe that failed for an unrelated reason says nothing about
                # capacity — settle it instead of stalling recovery for the whole
                # lease window or pinning the adapter to half_open forever.
                conn.execute(_RELEASE_PROBE_SQL, (clock, adapter_id))
                conn.commit()
                return
            row = conn.execute(
                "SELECT failure_count FROM adapter_health WHERE adapter_id = ?",
                (adapter_id,),
            ).fetchone()
            failures = int(row[0] or 0) + 1 if row else 1
            active_policy = policy or DEFAULT_MODEL_ROUTING
            cooldown_policy = active_policy.get("cooldown") or {}
            base = max(1, int(cooldown_policy.get("default_seconds") or 300))
            maximum = max(base, int(cooldown_policy.get("maximum_seconds") or 3600))
            delay = (
                min(maximum, max(1, int(retry_after_s)))
                if retry_after_s
                else min(maximum, base * (2 ** (failures - 1)))
            )
            conn.execute(
                "INSERT INTO adapter_health "
                "(adapter_id, state, failure_count, cooldown_until, probe_lease_until, reason, updated_at) "
                "VALUES (?, 'cooling_down', ?, ?, NULL, ?, ?) "
                "ON CONFLICT(adapter_id) DO UPDATE SET state = 'cooling_down', "
                "failure_count = excluded.failure_count, cooldown_until = excluded.cooldown_until, "
                "probe_lease_until = NULL, reason = excluded.reason, updated_at = excluded.updated_at",
                (
                    adapter_id,
                    failures,
                    clock + delay,
                    safe_reason or "capacity unavailable",
                    clock,
                ),
            )
            conn.commit()
    except sqlite3.OperationalError as exc:
        logger.debug("capacity result unavailable for %s: %s", adapter_id, exc)


def health_snapshot(db_path: str | Path, now: float | None = None) -> dict[str, dict[str, Any]]:
    clock = time.time() if now is None else now
    try:
        with sqlite3.connect(str(db_path)) as conn:
            rows = conn.execute(
                "SELECT adapter_id, state, failure_count, cooldown_until, probe_lease_until, reason "
                "FROM adapter_health"
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {
        str(scope): _health_row(
            state, failure_count, cooldown_until, probe_lease_until, reason, clock
        )
        for scope, state, failure_count, cooldown_until, probe_lease_until, reason in rows
    }


def _health_row(state, failure_count, cooldown_until, probe_lease_until, reason, clock) -> dict:
    waiting = max(0, int(float(cooldown_until or 0) - clock))
    probing = str(state) == "half_open" and float(probe_lease_until or 0) > clock
    # An expired cooldown is over: check_capacity already lets the next caller
    # through, so reporting 'cooling_down · 0s' forever misleads the operator.
    settled = str(state) == "cooling_down" and waiting == 0
    return {
        "state": "healthy" if settled else str(state),
        "failure_count": int(failure_count or 0),
        "retry_after_s": waiting,
        "probe_active": probing,
        "reason": "" if settled else str(reason or ""),
    }


def adapter_health(snapshot: dict[str, dict[str, Any]], adapter_id: str) -> dict[str, Any] | None:
    scoped = {scope: row for scope, row in snapshot.items() if adapter_of(scope) == adapter_id}
    if not scoped:
        return None
    rank = {"cooling_down": 2, "half_open": 1, "healthy": 0}
    worst = max(scoped.items(), key=lambda item: rank.get(item[1]["state"], 0))
    waits = [row["retry_after_s"] for row in scoped.values() if row["retry_after_s"] > 0]
    limited = sorted(scope for scope, row in scoped.items() if row["state"] != "healthy")
    return {
        **worst[1],
        # The soonest pool to recover, and which pools are limited — an adapter
        # whose Opus pool is capped still has its other pools available.
        "retry_after_s": min(waits) if waits else 0,
        "buckets": scoped,
        "limited_buckets": limited,
    }


def clear_health(db_path: str | Path, adapter_id: str) -> bool:
    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            # Operator intent is "clear this adapter", so every pool it meters
            # against goes with it.
            cursor = conn.execute(
                "DELETE FROM adapter_health WHERE adapter_id = ? OR adapter_id GLOB ?",
                (adapter_id, f"{adapter_id}:*"),
            )
            conn.commit()
            return cursor.rowcount > 0
    except sqlite3.OperationalError as exc:
        logger.debug("capacity reset unavailable for %s: %s", adapter_id, exc)
        return False
