"""core.web.routes.settings — hub-level settings read/write."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("coding_os.web.settings")
router = APIRouter(prefix="/api/settings", tags=["settings"])

_DEFAULTS: dict = {
    "budget_cap": {"enabled": False, "cap_usd": 5.0},
    "trace_rotation": {"gzip_age_days": 3, "delete_age_days": 30},
    "model_routing": {"enabled": False, "orchestrator_model": ""},
}


def _settings_path() -> Path:
    state_dir = os.environ.get("COS_STATE_DIR") or ".coding-os"
    return Path(state_dir) / "hub-settings.json"


def _load() -> dict:
    path = _settings_path()
    raw: dict = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text())
        except Exception as exc:
            logger.debug("hub-settings.json load error: %s", exc)
    merged: dict = {}
    for section, defaults in _DEFAULTS.items():
        merged[section] = {**defaults, **(raw.get(section) or {})}
    return merged


def _save(data: dict) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _env_overrides() -> dict:
    overrides: dict = {}
    for var in (
        "COS_DAILY_BUDGET_USD",
        "COS_TRACE_GZIP_AGE_DAYS",
        "COS_TRACE_DELETE_AGE_DAYS",
    ):
        val = os.environ.get(var)
        if val:
            overrides[var] = val
    return overrides


@router.get("")
def get_settings():
    return {"data": {"settings": _load(), "env_overrides": _env_overrides()}}


def _module_error(status: int, category: str, message: str, retryable: bool) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "ok": False,
            "error": {"category": category, "message": message, "retryable": retryable},
        },
    )


@router.get("/modules")
def get_modules():
    """Per-module subsystem state for the Config tab (TASK-354)."""
    try:
        from cli.module_commands import module_state_payload
        from web._project_context import current_project_root

        payload = module_state_payload(current_project_root())
    except Exception as exc:
        return _module_error(503, "unavailable", f"module registry unavailable: {exc}", True)
    return {"data": payload, "meta": {"layer": "settings", "source": "settings.modules"}}


@router.get("/modules/drift")
def get_module_drift():
    """Non-PASS module drift (skill/command/state_integrity) for a Hub WARN banner.

    Reuses the three existing `cos doctor` check functions verbatim — no new check
    logic — so the toggle UI surfaces the drift its own cascade can produce
    (HUB-PB2 / TASK-504).
    """
    try:
        from cli.doctor import (
            SEV_PASS,
            DoctorReport,
            _check_module_command_drift,
            _check_module_skill_drift,
            _check_subsystems_state_integrity,
        )
        from web._project_context import current_project_root

        project = current_project_root()
        report = DoctorReport(project_dir=str(project), agent=None, templates=[])
        for check in (
            _check_module_skill_drift,
            _check_module_command_drift,
            _check_subsystems_state_integrity,
        ):
            check(project, report)
        drift = [
            {"id": c.id, "severity": c.severity, "message": c.message}
            for c in report.checks
            if c.severity != SEV_PASS
        ]
    except Exception as exc:
        return _module_error(503, "unavailable", f"module drift unavailable: {exc}", True)
    return {
        "data": {"drift": drift, "ok": not drift},
        "meta": {"layer": "settings", "source": "settings.modules.drift"},
    }


@router.patch("/modules/{module_id}")
def patch_module(module_id: str, body: dict = Body(...)):
    """Toggle a non-kernel module; regenerates dependent artifacts (TASK-354)."""
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        return _module_error(400, "validation", "body must carry {'enabled': true|false}", False)
    try:
        from cli.module_commands import toggle_and_regen
        from web._project_context import current_project_root

        result, notes = toggle_and_regen(current_project_root(), module_id, enabled)
    except Exception as exc:
        return _module_error(503, "unavailable", f"module toggle unavailable: {exc}", True)
    if not result.ok:
        status = 404 if "unknown module" in result.reason else 400
        return _module_error(status, "validation", result.reason, False)
    return {
        "data": {"module": module_id, "enabled": enabled, "regenerated": notes},
        "meta": {"layer": "settings", "source": "settings.module_toggle"},
    }


class _BudgetCapIn(BaseModel):
    enabled: bool
    cap_usd: float


class _TraceRotationIn(BaseModel):
    gzip_age_days: int
    delete_age_days: int


class _ModelRoutingIn(BaseModel):
    enabled: bool
    orchestrator_model: str = ""


class _PatchBody(BaseModel):
    budget_cap: _BudgetCapIn | None = None
    trace_rotation: _TraceRotationIn | None = None
    model_routing: _ModelRoutingIn | None = None


@router.patch("")
def patch_settings(body: _PatchBody):
    current = _load()
    if body.budget_cap is not None:
        current["budget_cap"] = body.budget_cap.model_dump()
    if body.trace_rotation is not None:
        current["trace_rotation"] = body.trace_rotation.model_dump()
    if body.model_routing is not None:
        current["model_routing"] = body.model_routing.model_dump()
    _save(current)
    return {"data": {"settings": current, "env_overrides": _env_overrides()}}
