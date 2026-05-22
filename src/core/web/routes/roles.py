"""core.web.routes.roles — /api/roles/* endpoints for role observability.

PURPOSE: Expose Formula (F1..F11) metadata, composed chain snapshots, and
         recent formula outputs so the Hub UI can inspect cognition routing.
INPUT:   HTTP request query params (`agent`, `limit`) and formula path params.
OUTPUT:  JSON responses unwrapped from the MCP envelope ({data, meta} on 200).
DEPENDENCIES: fastapi, pathlib/json, pyyaml, pydantic models.
NOTES:   Data sources are local files:
         - core/thinking_os/roles/*.yaml
         - .coding-os/<agent>/traces/*.jsonl
         - .coding-os/**/evidence_bundle_<session_id>.json
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, Query

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import unwrap
from .._project_context import current_project_root

_CORE_DIR = Path(__file__).resolve().parents[2]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))
_THINKING_OS_DIR = _CORE_DIR / "thinking_os"
if str(_THINKING_OS_DIR) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS_DIR))

router = APIRouter(prefix="/api/roles", tags=["roles"])


def _state_dir() -> Path:
    from .._project_context import is_explicit_project_scope

    if is_explicit_project_scope():
        return current_project_root() / ".coding-os"
    base = os.environ.get("COS_STATE_DIR") or os.environ.get("COS_AGENT_DIR")
    if base:
        return Path(base).resolve()
    return current_project_root() / ".coding-os"


def _roles_dir() -> Path:
    return _CORE_DIR / "thinking_os" / "roles"


def _schema_class(schema_ref: str):
    if not schema_ref or "." not in schema_ref:
        return None
    module_name, class_name = schema_ref.rsplit(".", 1)
    try:
        module = importlib.import_module(module_name)
        return getattr(module, class_name, None)
    except Exception:
        return None


def _role_defs() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(_roles_dir().glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if not isinstance(data, dict) or "id" not in data:
            continue
        output_schema = str(data.get("output_schema") or "")
        schema_cls = _schema_class(output_schema)
        out.append(
            {
                "formula_id": str(data.get("id") or path.stem),
                "role_name": str(data.get("role_name") or ""),
                "formula_ref": str(data.get("formula_ref") or ""),
                "output_schema": output_schema,
                "schema_json": schema_cls.model_json_schema() if schema_cls is not None else None,
                "agent_file": str(data.get("agent_file") or ""),
                "version": str(data.get("version") or "v1"),
                "path": str(path),
            }
        )
    return out


def _agents_with_traces(state: Path) -> list[str]:
    agents: list[str] = []
    for child in sorted(state.glob("*")):
        if child.is_dir() and (child / "traces").exists():
            agents.append(child.name)
    if not agents:
        for fallback in ("claude", "codex"):
            if (state / fallback / "traces").exists():
                agents.append(fallback)
    return agents


def _read_trace_events(state: Path, agent: str, session_id: str) -> list[dict[str, Any]]:
    p = state / agent / "traces" / f"{session_id}.jsonl"
    if not p.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return events


def _read_evidence_bundle(state: Path, agent: str, session_id: str) -> dict[str, Any] | None:
    candidates = [
        state / agent / f"evidence_bundle_{session_id}.json",
        state / f"evidence_bundle_{session_id}.json",
        current_project_root() / ".coding-os" / "claude" / f"evidence_bundle_{session_id}.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
    return None


def _bundle_field(formula_id: str) -> str | None:
    return {
        "F1": "F1_research",
        "F2": "F2_decompose",
        "F3": "F3_architect",
        "F4": "F4_document",
        "F5": "F5_implement",
        "F6": "F6_test_review",
        "F7": "F7_debug",
        "F8": "F8_security",
        "F9": "F9_deploy",
        "F10": "F10_monitor",
        "F11": "F11_refactor",
    }.get(formula_id)


# The API + traces + bundle fields key formulas as F1..F11; role yamls
# (src/core/thinking_os/roles/*.yaml) key by semantic role name. Map
# between them in the canonical formula order (formulas-en.md).
_FORMULA_TO_ROLE: dict[str, str] = {
    "F1": "researcher",
    "F2": "analyst",
    "F3": "architect",
    "F4": "documenter",
    "F5": "implementer",
    "F6": "reviewer",
    "F7": "debugger",
    "F8": "security_auditor",
    "F9": "deployer",
    "F10": "observer",
    "F11": "refactorer",
}


def _role_for_formula(formula_id: str, roles: dict[str, dict]) -> dict:
    """Resolve a role def by F-number or by raw role name."""
    if formula_id in roles:
        return roles[formula_id]
    return roles.get(_FORMULA_TO_ROLE.get(formula_id, ""), {})


@router.get("")
async def list_roles(
    _rl=Depends(make_rate_limit_dep("roles.list")),
    _m=Depends(make_metrics_dep("roles.list")),
):
    roles = _role_defs()
    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {"roles": roles, "count": len(roles)},
                "meta": {"layer": "cognition"},
            }
        )
    )


@router.get("/chain")
async def current_chain(
    agent: str = Query("claude"),
    _rl=Depends(make_rate_limit_dep("roles.chain")),
    _m=Depends(make_metrics_dep("roles.chain")),
):
    state = _state_dir()
    chain_file = state / agent / ".roles"
    active_file = state / agent / ".role"
    chain: list[str] = []
    active_formula: str | None = None

    if chain_file.exists():
        raw = chain_file.read_text(encoding="utf-8").strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                chain = [str(x) for x in parsed]
        except json.JSONDecodeError:
            chain = [x.strip() for x in raw.split(",") if x.strip()]

    if active_file.exists():
        active_raw = active_file.read_text(encoding="utf-8").strip()
        active_formula = active_raw or None

    if not chain:
        traces_dir = state / agent / "traces"
        for p in sorted(traces_dir.glob("*.jsonl"), reverse=True):
            events = _read_trace_events(state, agent, p.stem)
            for ev in reversed(events):
                if ev.get("kind") == "compose_done":
                    chain = [str(x) for x in (ev.get("data", {}) or {}).get("chain", [])]
                    break
            if chain:
                break

    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "agent": agent,
                    "chain": chain,
                    "active_formula": active_formula,
                    "has_active_session": bool(chain),
                },
                "meta": {"layer": "cognition"},
            }
        )
    )


@router.get("/{formula_id}/outputs")
async def formula_outputs(
    formula_id: str,
    agent: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    _rl=Depends(make_rate_limit_dep("roles.outputs")),
    _m=Depends(make_metrics_dep("roles.outputs")),
):
    state = _state_dir()
    roles = {r["formula_id"]: r for r in _role_defs()}
    role = _role_for_formula(formula_id, roles)
    schema_cls = _schema_class(str(role.get("output_schema") or ""))
    field_name = _bundle_field(formula_id)

    agents = [agent] if agent else _agents_with_traces(state)
    outputs: list[dict[str, Any]] = []
    planned: list[dict[str, Any]] = []
    for ag in agents:
        traces_dir = state / ag / "traces"
        if not traces_dir.exists():
            continue
        for p in sorted(traces_dir.glob("*.jsonl"), reverse=True):
            session_id = p.stem
            events = _read_trace_events(state, ag, session_id)
            bundle = _read_evidence_bundle(state, ag, session_id)
            output_json = None
            if bundle and field_name:
                output_json = bundle.get(field_name)
            executed_in_session = False
            for ev in reversed(events):
                if ev.get("kind") != "role_output_recorded":
                    continue
                data = ev.get("data", {}) or {}
                if str(data.get("formula_id")) != formula_id:
                    continue
                schema_ok = None
                schema_errors: list[str] = []
                if schema_cls is not None and output_json is not None:
                    try:
                        schema_cls.model_validate(output_json)
                        schema_ok = True
                    except Exception as exc:
                        schema_ok = False
                        schema_errors = [str(exc)]
                outputs.append(
                    {
                        "session_id": session_id,
                        "agent": ag,
                        "ts": ev.get("ts"),
                        "status": data.get("status"),
                        "latency_ms": data.get("latency_ms"),
                        "output_hash": data.get("output_hash"),
                        "bundle_fields_filled": data.get("bundle_fields_filled"),
                        "output_json": output_json,
                        "schema_ok": schema_ok,
                        "schema_errors": schema_errors,
                    }
                )
                executed_in_session = True
                break
            if executed_in_session:
                continue
            # Lifecycle fallback: the session composed a chain that
            # INCLUDED this formula but never reached the
            # supervise_record_output step.  Surface it as "planned"
            # so the Roles tab is no longer silent — that empty state
            # was hiding the fact that compose_chain is firing but
            # the recording side never runs.
            for ev in reversed(events):
                if ev.get("kind") != "compose_done":
                    continue
                chain = (ev.get("data", {}) or {}).get("chain") or []
                if formula_id in chain:
                    planned.append(
                        {
                            "session_id": session_id,
                            "agent": ag,
                            "ts": ev.get("ts"),
                            "status": "planned",
                            "latency_ms": None,
                            "output_hash": None,
                            "bundle_fields_filled": None,
                            "output_json": None,
                            "schema_ok": None,
                            "schema_errors": [],
                            "chain": chain,
                            "preset_id": (ev.get("data", {}) or {}).get("preset_id"),
                        }
                    )
                break

    outputs.sort(key=lambda row: float(row.get("ts") or 0.0), reverse=True)
    planned.sort(key=lambda row: float(row.get("ts") or 0.0), reverse=True)
    combined = (outputs + planned)[:limit]

    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "formula_id": formula_id,
                    "outputs": combined,
                    "count": len(combined),
                    "executed_count": len(outputs),
                    "planned_count": len(planned),
                },
                "meta": {"layer": "cognition"},
            }
        )
    )
