"""core.web.routes.scheduled — /api/scheduled/* hub endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import plistlib
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

# Package-qualified, not sys.path + bare `_state`: those inserts were computed
# from the source-tree depth (parents[3] == src/), which resolves to a garbage
# directory once installed, so `cos hub start` from a wheel died here. The
# module object also locates nightly.py without re-deriving a path.
import scheduled
from scheduled._state import read_registry, read_state
from scheduled.config import DEFAULTS, load_config, save_config
from thinking_os.database import PROJECT_SCOPED_ENV_VARS

router = APIRouter(prefix="/api/scheduled", tags=["scheduled"])
logger = logging.getLogger("codingos.web.scheduled")

_PLIST_DEST = Path.home() / "Library" / "LaunchAgents" / "com.codingos.nightly.plist"
_GLOBAL_SUMMARY = Path.home() / ".coding-os" / "scheduled" / "last_summary.json"


def _plist_installed() -> bool:
    return _PLIST_DEST.exists()


def _launchd_loaded() -> bool:
    try:
        result = subprocess.run(
            ["launchctl", "list", "com.codingos.nightly"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False
    except subprocess.TimeoutExpired:
        logger.debug("launchctl list timed out")
        return False


def _plist_hour(default: int = 3) -> int:
    """Hour the installed launchd job actually fires at, read from the plist's
    StartCalendarInterval — so next_run_at reflects the installed schedule
    rather than a hardcoded assumption."""
    try:
        with _PLIST_DEST.open("rb") as fh:
            data = plistlib.load(fh)
    except (OSError, ValueError, plistlib.InvalidFileException) as exc:
        logger.debug("plist hour read failed: %s", exc)
        return default
    cal = data.get("StartCalendarInterval")
    if isinstance(cal, dict) and isinstance(cal.get("Hour"), int):
        return cal["Hour"]
    if isinstance(cal, list):  # multiple intervals — the earliest fire hour
        hours = [c["Hour"] for c in cal if isinstance(c, dict) and isinstance(c.get("Hour"), int)]
        if hours:
            return min(hours)
    return default


def _next_run_at() -> str | None:
    try:
        hour = _plist_hour()
        now = datetime.now()
        next_run = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if now.hour >= hour:
            next_run = next_run + timedelta(days=1)
        return next_run.astimezone(timezone.utc).isoformat()
    except (ValueError, OSError) as exc:
        logger.debug("_next_run_at error: %s", exc)
        return None


class CronStatus(BaseModel):
    installed: bool
    loaded: bool
    last_run_at: str | None = None
    next_run_at: str | None = None
    plist_path: str
    log_dir: str


class ProjectScheduled(BaseModel):
    slug: str | None = None
    path: str | None = None
    last_run_at: str | None = None
    tasks: dict = {}
    consecutive_failures: int = 0
    disabled_reason: str | None = None
    last_error: str | None = None


class ScheduledStatus(BaseModel):
    cron_a: CronStatus
    projects: list[ProjectScheduled]


@router.get("/status", response_model=ScheduledStatus)
def scheduled_status() -> ScheduledStatus:
    """Return nightly cron status + per-project last_run.json contents."""
    projects_data = []
    for proj in read_registry():
        root = Path(proj.get("path", ""))
        state = read_state(root)
        projects_data.append(
            {
                "slug": proj.get("slug"),
                "path": proj.get("path"),
                "last_run_at": state.get("run_at"),
                "tasks": state.get("tasks", {}),
                "consecutive_failures": state.get("consecutive_failures", 0),
                "disabled_reason": state.get("disabled_reason"),
                "last_error": state.get("last_error"),
            }
        )

    global_summary: dict = {}
    if _GLOBAL_SUMMARY.exists():
        try:
            global_summary = json.loads(_GLOBAL_SUMMARY.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("could not read global summary: %s", exc)

    loaded = _launchd_loaded()
    return {
        "cron_a": {
            "installed": _plist_installed(),
            "loaded": loaded,
            "last_run_at": global_summary.get("run_at"),
            "next_run_at": _next_run_at() if loaded else None,
            "plist_path": str(_PLIST_DEST),
            "log_dir": str(Path.home() / ".coding-os" / "scheduled"),
        },
        "projects": projects_data,
    }


@router.get("/project/{slug}")
def project_scheduled_status(slug: str):
    """Return last_run.json for a single project."""
    for proj in read_registry():
        if proj.get("slug") == slug:
            root = Path(proj.get("path", ""))
            state = read_state(root)
            return {"slug": slug, **state}
    return {"error": f"project {slug!r} not found in registry"}


class RunResult(BaseModel):
    slug: str
    ran: bool
    summary: dict | None = None
    error: str | None = None


# Per-project scoping overrides the Hub sets for its own request handling. The
# isolated nightly child must NOT inherit them, else its internal legs resolve
# the Hub launch project's paths instead of the target project's (matches the
# clean env the standalone launchd cron runs with). Same SSOT the Hub daemon
# strips at startup — docs/engineering/state-files.md § The multi-project
# exception.
_SCOPE_ENV_VARS = PROJECT_SCOPED_ENV_VARS


def _clean_child_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in _SCOPE_ENV_VARS}


@router.post("/run/{slug}", response_model=RunResult)
async def run_scheduled_now(slug: str) -> RunResult:
    """Manually trigger the nightly maintenance loop (decay + learn-extract + reindex) for one project."""
    proj = next((p for p in read_registry() if p.get("slug") == slug), None)
    if proj is None:
        return RunResult(slug=slug, ran=False, error=f"project {slug!r} not found in registry")
    root = Path(proj.get("path", ""))
    # Run in a SUBPROCESS, never in-process: run_project's reclaim + dep_reconcile
    # legs mutate os.environ["COS_PROJECT_ROOT"] process-wide, which would corrupt
    # a concurrent unscoped Hub request's project resolution. A child owns its own
    # env, so the live worker is never touched (mirrors nightly's
    # _run_graph_reindex_if_stale subprocess pattern).
    nightly_py = Path(scheduled.__file__).resolve().parent / "nightly.py"
    before_run_at = read_state(root).get("run_at")
    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, str(nightly_py), "--project", slug],
            capture_output=True,
            text=True,
            timeout=900,
            env=_clean_child_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:  # fail-soft: never 500 the hub
        logger.warning("manual scheduled run failed for %s: %s", slug, exc)
        return RunResult(slug=slug, ran=False, error=str(exc))
    # run_project persists a fresh last_run.json; a changed run_at proves the
    # child executed (an early skip / crash leaves it stale).
    summary = read_state(root)
    if summary.get("run_at") and summary.get("run_at") != before_run_at:
        return RunResult(slug=slug, ran=True, summary=summary)
    err = (completed.stderr or "").strip()[-300:] or f"nightly rc={completed.returncode}"
    return RunResult(slug=slug, ran=False, error=err)


def _root_for_slug(slug: str) -> Path | None:
    for proj in read_registry():
        if proj.get("slug") == slug:
            return Path(proj.get("path", ""))
    return None


class ScheduledConfigUpdate(BaseModel):
    # Mirror every editable key in scheduled.config.DEFAULTS — a field missing
    # here is silently dropped by Pydantic before save_config sees it, so a UI
    # edit (e.g. Archive prune) would report success yet never persist.
    enabled: bool | None = None
    hour: int | None = None
    decay_throttle_days: int | None = None
    learn_extract_min_outcomes: int | None = None
    responsive_extract_threshold: int | None = None
    archive_prune_days: int | None = None
    error_sweep_occ_threshold: int | None = None
    error_sweep_session_threshold: int | None = None


@router.get("/config/{slug}")
def get_scheduled_config(slug: str):
    """Return the editable scheduled-maintenance config for one project."""
    root = _root_for_slug(slug)
    if root is None:
        return {"error": f"project {slug!r} not found in registry"}
    return {"slug": slug, "config": load_config(root), "defaults": DEFAULTS}


@router.patch("/config/{slug}")
def patch_scheduled_config(slug: str, update: ScheduledConfigUpdate):
    """Persist edited scheduled config (cadence + responsive thresholds)."""
    root = _root_for_slug(slug)
    if root is None:
        return {"error": f"project {slug!r} not found in registry"}
    updates = {k: v for k, v in update.model_dump().items() if v is not None}
    saved = save_config(root, updates)
    return {"slug": slug, "config": saved}
