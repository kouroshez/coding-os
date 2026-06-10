"""core.web.routes.settings — hub-level settings read/write."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter
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
async def get_settings():
    return {"data": {"settings": _load(), "env_overrides": _env_overrides()}}


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
async def patch_settings(body: _PatchBody):
    current = _load()
    if body.budget_cap is not None:
        current["budget_cap"] = body.budget_cap.model_dump()
    if body.trace_rotation is not None:
        current["trace_rotation"] = body.trace_rotation.model_dump()
    if body.model_routing is not None:
        current["model_routing"] = body.model_routing.model_dump()
    _save(current)
    return {"data": {"settings": current, "env_overrides": _env_overrides()}}
