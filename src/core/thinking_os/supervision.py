from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from thinking_os.adapter_registry import AdapterRecord, configured_adapter_ids, load_adapter_records

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


@dataclass(frozen=True)
class HealthDecision:
    allowed: bool
    state: str
    retry_after_s: int | None = None
    probe: bool = False
    reason: str = ""


def current_project_root() -> Path:
    value = os.environ.get("COS_PROJECT_ROOT")
    return Path(value).resolve() if value else Path.cwd().resolve()


def _settings_path(project_root: Path | None = None) -> Path:
    if project_root is not None:
        return project_root / ".coding-os" / "hub-settings.json"
    state_dir = os.environ.get("COS_STATE_DIR")
    if state_dir:
        return Path(state_dir) / "hub-settings.json"
    return current_project_root() / ".coding-os" / "hub-settings.json"


def load_policy(project_root: Path | None = None) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    try:
        data = json.loads(_settings_path(project_root).read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("model_routing"), dict):
            raw = data["model_routing"]
    except (OSError, ValueError):
        pass
    policy = {**DEFAULT_MODEL_ROUTING, **raw}
    for key in ("orchestrator", "cooldown"):
        base = DEFAULT_MODEL_ROUTING[key]
        value = raw.get(key)
        policy[key] = {**base, **(value if isinstance(value, dict) else {})}
    policy["roles"] = raw.get("roles") if isinstance(raw.get("roles"), dict) else {}
    return policy


def enabled(project_root: Path | None = None) -> bool:
    return load_policy(project_root).get("enabled") is True


def role_policy(role: str, project_root: Path | None = None) -> dict[str, str]:
    policy = load_policy(project_root)
    value = policy.get("roles", {}).get(role, {}) if policy.get("enabled") else {}
    value = value if isinstance(value, dict) else {}
    return {
        "adapter": str(value.get("adapter") or ""),
        "model": str(value.get("model") or ""),
        "effort": str(value.get("effort") or ""),
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


def check_capacity(
    db_path: str | Path, adapter_id: str, now: float | None = None
) -> HealthDecision:
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
            lease_until = clock + 30
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
                max(1, int(retry_after_s))
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
        str(adapter_id): {
            "state": str(state),
            "failure_count": int(failure_count or 0),
            "retry_after_s": max(0, int(float(cooldown_until or 0) - clock)),
            "probe_active": str(state) == "half_open" and float(probe_lease_until or 0) > clock,
            "reason": str(reason or ""),
        }
        for adapter_id, state, failure_count, cooldown_until, probe_lease_until, reason in rows
    }


def clear_health(db_path: str | Path, adapter_id: str) -> bool:
    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            cursor = conn.execute("DELETE FROM adapter_health WHERE adapter_id = ?", (adapter_id,))
            conn.commit()
            return cursor.rowcount > 0
    except sqlite3.OperationalError as exc:
        logger.debug("capacity reset unavailable for %s: %s", adapter_id, exc)
        return False
