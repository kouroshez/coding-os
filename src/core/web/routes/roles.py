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
import logging
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


def _newest_marker(agent_dir: Path, basename: str) -> str | None:
    """Newest copy of a per-panel marker across agent_dir + every panels/*/.

    Post-TASK-035/057 the role markers (.roles, .role) live under panels/<id>/.
    The panel id is not stable across hook subprocesses, so one session's
    markers scatter; the agent-level copy is a stale fossil. The Hub wants the
    live value, so the newest mtime wins. Mirrors presence.py::_newest_marker.
    """
    candidates = [agent_dir / basename]
    panels = agent_dir / "panels"
    if panels.is_dir():
        try:
            candidates.extend(p / basename for p in panels.iterdir() if p.is_dir())
        except OSError:
            pass
    best_text: str | None = None
    best_mtime = -1.0
    for path in candidates:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > best_mtime:
            try:
                best_text = path.read_text(encoding="utf-8")
                best_mtime = mtime
            except OSError:
                continue
    return best_text


def _schema_class(schema_ref: str):
    if not schema_ref or "." not in schema_ref:
        return None
    module_name, class_name = schema_ref.rsplit(".", 1)
    try:
        module = importlib.import_module(module_name)
        return getattr(module, class_name, None)
    except Exception as exc:
        logging.getLogger("coding_os.web.roles").debug("schema import failed: %s", exc)
        return None


# Role yamls are static core artifacts; parsing + building Pydantic JSON
# schemas on every /api/roles + /outputs request is wasted work. Cache keyed
# on (newest mtime, file count) so an edit/add/delete still invalidates but a
# polling panel re-uses the parsed defs. Shared safely — _roles_dir() is the
# core dir, identical across projects (roles are not per-project).
_ROLE_DEFS_CACHE: dict[str, Any] = {"key": None, "defs": []}


def _role_defs() -> list[dict[str, Any]]:
    paths = sorted(p for p in _roles_dir().glob("*.yaml") if not p.name.startswith("_"))
    cache_key = (max((p.stat().st_mtime for p in paths), default=0.0), len(paths))
    if _ROLE_DEFS_CACHE["key"] == cache_key and _ROLE_DEFS_CACHE["defs"]:
        return _ROLE_DEFS_CACHE["defs"]
    out: list[dict[str, Any]] = []
    for path in paths:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logging.getLogger("coding_os.web.roles").debug("role yaml parse failed %s: %s", path, exc)
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
    _ROLE_DEFS_CACHE["key"] = cache_key
    _ROLE_DEFS_CACHE["defs"] = out
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


def _dispatch_available() -> bool:
    # Sub-agent dispatch (Path B: cos_dispatch_formula_run → real Claude
    # sub-sessions that produce "dispatched"/executed evidence) needs the
    # Claude Agent SDK extra. Without it roles run in-session only ("composed").
    # Surfacing this lets the panel show "dispatched: 0" as capability-off,
    # not a bug.
    try:
        import claude_agent_sdk  # type: ignore  # noqa: F401

        return True
    except ImportError:
        return False


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
                "data": {
                    "roles": roles,
                    "count": len(roles),
                    "dispatch_available": _dispatch_available(),
                },
                "meta": {"layer": "cognition"},
            }
        )
    )


def resolve_chain(state: Path, agent: str) -> tuple[list[str], str | None]:
    """The agent's composed role chain + active role — trace-first, marker
    fallback. Shared by /api/roles/chain and the unified live-agent endpoint
    (TASK-191) so both read the chain the same way."""
    agent_dir = state / agent
    # Active role is the freshest per-panel signal (what the agent is DOING).
    active_raw = _newest_marker(agent_dir, ".role")
    active_formula = (active_raw.strip() or None) if active_raw else None

    # Chain: prefer the newest agent-level compose_done trace — the
    # cross-panel-safe source the EVIDENCE view also reads.
    # Scattered per-panel .roles markers can be stale under concurrent panels.
    chain: list[str] = []
    traces_dir = state / agent / "traces"
    if traces_dir.exists():
        for p in sorted(traces_dir.glob("*.jsonl"), reverse=True):
            events = _read_trace_events(state, agent, p.stem)
            for ev in reversed(events):
                if ev.get("kind") == "compose_done":
                    chain = [str(x) for x in (ev.get("data", {}) or {}).get("chain", [])]
                    break
            if chain:
                break

    # Fallback to the per-panel .roles marker when no trace exists yet.
    if not chain:
        raw = _newest_marker(agent_dir, ".roles")
        if raw:
            raw = raw.strip()
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    chain = [str(x) for x in parsed]
            except json.JSONDecodeError:
                chain = [x.strip() for x in raw.split(",") if x.strip()]
    return chain, active_formula


@router.get("/chain")
async def current_chain(
    agent: str = Query("claude"),
    _rl=Depends(make_rate_limit_dep("roles.chain")),
    _m=Depends(make_metrics_dep("roles.chain")),
):
    chain, active_formula = resolve_chain(_state_dir(), agent)
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
                # schema_status disambiguates the schema_ok=None cases the UI
                # used to lump under one ambiguous message:
                #   no_payload — output never landed in the evidence bundle
                #   no_schema  — role has no resolvable Output schema class
                #   ok / fail  — schema validated / failed
                if output_json is None:
                    schema_status = "no_payload"
                elif schema_cls is None:
                    schema_status = "no_schema"
                else:
                    try:
                        schema_cls.model_validate(output_json)
                        schema_ok = True
                        schema_status = "ok"
                    except Exception as exc:
                        schema_ok = False
                        schema_status = "fail"
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
                        "schema_status": schema_status,
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
                            "schema_status": "planned",
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
