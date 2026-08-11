"""Private sibling of thinking_os.supervision — the routing policy document.

Owns `hub-settings.json::model_routing`: its defaults, its schema, the
normalize/read/patch cycle, and validation of a target against the adapter
descriptors. It knows nothing about adapter health — the capacity breaker in
`supervision` reads this module for its cooldown defaults, never the reverse.
"""

from __future__ import annotations

import copy
import logging
import os
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
        key: str(value.get(key) or default.get(key) or "") for key in ("adapter", "model", "effort")
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
