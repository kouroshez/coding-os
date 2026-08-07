from __future__ import annotations

import copy
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from thinking_os.adapter_registry import AdapterRecord, configured_adapter_ids, load_adapter_records
from thinking_os.project_settings import (
    project_settings_path,
    read_settings,
    settings_lock,
    write_settings,
)

logger = logging.getLogger("coding_os.supervision")

DEFAULT_MODEL_ROUTING: dict[str, Any] = {
    "enabled": False,
    "mode": "explicit",
    "complexity_threshold": "COMPLICATED",
    "fallback_policy": "fail_closed",
    "max_parallel": 3,
    "orchestrator_model": "",
    "orchestrator": {"adapter": "", "model": "", "effort": ""},
    "roles": {},
    "cooldown": {"default_seconds": 300, "maximum_seconds": 3600},
}


class AdapterTargetPolicy(BaseModel):
    adapter: str = ""
    model: str = ""
    effort: str = ""


class CooldownPolicy(BaseModel):
    default_seconds: int = Field(default=300, ge=1, le=86400)
    maximum_seconds: int = Field(default=3600, ge=1, le=604800)

    @model_validator(mode="after")
    def validate_range(self):
        if self.maximum_seconds < self.default_seconds:
            raise ValueError("maximum_seconds must be greater than or equal to default_seconds")
        return self


class ModelRoutingPolicy(BaseModel):
    enabled: bool
    orchestrator_model: str = ""
    mode: Literal["explicit", "suggest", "adaptive"] = "explicit"
    complexity_threshold: Literal["CLEAR", "COMPLICATED", "COMPLEX", "CHAOTIC"] = "COMPLICATED"
    fallback_policy: Literal["fail_closed", "same_adapter_default", "next_eligible"] = "fail_closed"
    max_parallel: int = Field(default=3, ge=1, le=16)
    orchestrator: AdapterTargetPolicy = Field(default_factory=AdapterTargetPolicy)
    roles: dict[str, AdapterTargetPolicy] = Field(default_factory=dict)
    cooldown: CooldownPolicy = Field(default_factory=CooldownPolicy)


COMPLEXITY_ORDER = ("CLEAR", "COMPLICATED", "COMPLEX", "CHAOTIC")


@dataclass(frozen=True)
class HealthDecision:
    allowed: bool
    state: str
    retry_after_s: int | None = None
    probe: bool = False
    reason: str = ""


def complexity_rank(value: str) -> int:
    normalized = str(value or "").strip().upper()
    return COMPLEXITY_ORDER.index(normalized) if normalized in COMPLEXITY_ORDER else -1


def current_project_root() -> Path:
    value = os.environ.get("COS_PROJECT_ROOT")
    return Path(value).resolve() if value else Path.cwd().resolve()


def normalize_policy(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    merged = {**copy.deepcopy(DEFAULT_MODEL_ROUTING), **source}
    for key in ("orchestrator", "cooldown"):
        value = source.get(key)
        merged[key] = {
            **copy.deepcopy(DEFAULT_MODEL_ROUTING[key]),
            **(value if isinstance(value, dict) else {}),
        }
    roles = source.get("roles")
    merged["roles"] = roles if isinstance(roles, dict) else {}
    if not merged["orchestrator"].get("model") and merged.get("orchestrator_model"):
        merged["orchestrator"]["model"] = merged["orchestrator_model"]
    if merged["orchestrator"].get("model"):
        merged["orchestrator_model"] = merged["orchestrator"]["model"]
    return ModelRoutingPolicy.model_validate(merged).model_dump()


def _accepts_model(record: AdapterRecord, model: str) -> bool:
    if "model_selection" not in record.capabilities:
        return False
    declared = {str(entry.get("id")) for entry in record.models if entry.get("id")}
    # An empty catalog means the runtime forwards any model string; core does not
    # invent ids for a runtime that has not published a list.
    return not declared or model in declared


def _accepts_effort(record: AdapterRecord, effort: str) -> bool:
    if "effort_selection" not in record.capabilities:
        return False
    return not record.efforts or effort in record.efforts


def _target_errors(label: str, target: dict[str, Any], records: list[AdapterRecord]) -> list[str]:
    known = {record.id: record for record in records}
    adapter_id = str(target.get("adapter") or "")
    if adapter_id and adapter_id not in known:
        return [f"{label}: unknown adapter {adapter_id!r} (eligible: {', '.join(sorted(known))})"]
    candidates = [known[adapter_id]] if adapter_id else records
    where = repr(adapter_id) if adapter_id else "any eligible adapter"
    errors = []
    model = str(target.get("model") or "")
    if model and not any(_accepts_model(record, model) for record in candidates):
        errors.append(f"{label}: model {model!r} is not declared by {where}")
    effort = str(target.get("effort") or "")
    if effort and not any(_accepts_effort(record, effort) for record in candidates):
        errors.append(f"{label}: effort {effort!r} is not supported by {where}")
    return errors


def validate_targets(targets: list[tuple[str, dict[str, Any]]], project_root: Path) -> None:
    records = eligible_records(project_root)
    if not records:
        return
    errors = [
        message
        for label, target in targets
        for message in _target_errors(label, target if isinstance(target, dict) else {}, records)
    ]
    if errors:
        raise ValueError("; ".join(errors))


def load_policy(project_root: Path | None = None) -> dict[str, Any]:
    try:
        data = read_settings(project_settings_path(project_root))
        raw = data.get("model_routing")
        return normalize_policy(raw if isinstance(raw, dict) else {})
    except ValueError as exc:
        logger.debug("supervision settings unavailable: %s", exc)
        return normalize_policy()


def update_policy(
    project_root: Path,
    patch: dict[str, Any],
    *,
    clear_role: str = "",
    clear_orchestrator: bool = False,
) -> dict[str, Any]:
    root = project_root.resolve()
    state_dir = root / ".coding-os"
    if not state_dir.is_dir():
        raise ValueError(f"{root} is not a coding-os project (.coding-os/ missing)")
    path = project_settings_path(root)
    with settings_lock(path):
        settings = read_settings(path)
        raw_policy = settings.get("model_routing", {})
        if not isinstance(raw_policy, dict):
            raise ValueError("model_routing must be a JSON object")
        current = normalize_policy(raw_policy)
        candidate = {**current, **patch}
        for key in ("orchestrator", "cooldown"):
            value = patch.get(key)
            candidate[key] = {
                **current[key],
                **(value if isinstance(value, dict) else {}),
            }
        roles = {**current["roles"]}
        role_patch = patch.get("roles")
        if isinstance(role_patch, dict):
            for role, target in role_patch.items():
                if not role.strip():
                    raise ValueError("role id must not be empty")
                if not isinstance(target, dict):
                    raise ValueError(f"role {role!r} must be an object")
                roles[role] = {**roles.get(role, {}), **target}
        if clear_role:
            roles.pop(clear_role, None)
        candidate["roles"] = roles
        if clear_orchestrator:
            candidate["orchestrator"] = copy.deepcopy(DEFAULT_MODEL_ROUTING["orchestrator"])
            candidate["orchestrator_model"] = ""
        normalized = normalize_policy(candidate)
        # Validate only what this patch touched: a role pinned to an adapter that
        # was later uninstalled must not lock the operator out of every other edit.
        touched: list[tuple[str, dict[str, Any]]] = []
        if isinstance(patch.get("orchestrator"), dict) and not clear_orchestrator:
            touched.append(("orchestrator", normalized["orchestrator"]))
        if isinstance(role_patch, dict):
            touched.extend(
                (f"role {name!r}", normalized["roles"].get(name, {})) for name in role_patch
            )
        validate_targets(touched, root)
        settings["model_routing"] = normalized
        write_settings(path, settings)
    return normalized


def policy_snapshot(project_root: Path | None = None) -> dict[str, Any]:
    root = (project_root or current_project_root()).resolve()
    records = eligible_records(root)
    return {
        "policy": load_policy(root),
        "settings_path": str(project_settings_path(root)),
        "adapters": [
            {
                "id": record.id,
                "models": [str(model.get("id")) for model in record.models if model.get("id")],
                "efforts": list(record.efforts),
                "capabilities": sorted(record.capabilities),
            }
            for record in records
        ],
    }


def enabled(project_root: Path | None = None) -> bool:
    return load_policy(project_root).get("enabled") is True


def policy_applies(policy: dict[str, Any], complexity: str = "") -> bool:
    if policy.get("enabled") is not True:
        return False
    if str(policy.get("mode") or "explicit") != "adaptive":
        return True
    threshold = complexity_rank(str(policy.get("complexity_threshold") or ""))
    return complexity_rank(complexity) >= threshold


def role_policy(
    role: str, project_root: Path | None = None, complexity: str = ""
) -> dict[str, str]:
    policy = load_policy(project_root)
    if not policy_applies(policy, complexity):
        return {"adapter": "", "model": "", "effort": ""}
    # The orchestrator target is the project-wide default; a role entry overrides
    # it field by field, so pinning one role does not restate the others.
    default = policy.get("orchestrator")
    default = default if isinstance(default, dict) else {}
    value = policy.get("roles", {}).get(role, {})
    value = value if isinstance(value, dict) else {}
    return {
        key: str(value.get(key) or default.get(key) or "")
        for key in ("adapter", "model", "effort")
    }


def eligible_records(project_root: Path | None = None) -> list[AdapterRecord]:
    root = project_root or current_project_root()
    records = load_adapter_records()
    configured = configured_adapter_ids(root, records)
    return [
        records[adapter_id]
        for adapter_id in configured
        if adapter_id in records and "dispatch" in records[adapter_id].capabilities
    ]


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
        str(scope): _health_row(state, failure_count, cooldown_until, probe_lease_until, reason, clock)
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
    scoped = {
        scope: row for scope, row in snapshot.items() if adapter_of(scope) == adapter_id
    }
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
