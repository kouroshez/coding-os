"""Shared foundation for the /api/cognition surface.

Holds the APIRouter every cognition route group decorates, plus the accessors
they all need: the state directory, the lazily-imported cognition tools module,
the DB path, the unavailable envelope, and the Auto-model triage. A leaf by
construction — it imports no sibling route module, so the route groups never
form an import cycle around the router they share.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

from fastapi import APIRouter

from .._envelope import ENVELOPE_ERROR_RESPONSES

# A trace jsonl can reach GBs (e.g. a long run_await loop). Read only the tail
# so the viewer shows the most-recent events without OOMing the server. TASK-225.
_MAX_TRACE_EVENTS = 2000

logger = logging.getLogger(__name__)

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

router = APIRouter(prefix="/api/cognition", tags=["cognition"], responses=ENVELOPE_ERROR_RESPONSES)


def _state_dir() -> Path:
    """Resolve the .coding-os state directory.

    Per-project requests (`/api/p/<slug>/...`) ALWAYS use that project's
    `.coding-os/` — env vars cannot override scope. Otherwise env vars
    win for backwards compatibility with tests + manual overrides.
    """
    from web._project_context import current_project_root, is_explicit_project_scope

    if is_explicit_project_scope():
        return current_project_root() / ".coding-os"
    base = os.environ.get("COS_STATE_DIR") or os.environ.get("COS_AGENT_DIR")
    if base:
        return Path(base).resolve()
    return current_project_root() / ".coding-os"


def _cognition_module():
    """Lazy import for cognition tools."""
    try:
        tos_dir = _CORE_DIR / "thinking_os"
        if str(tos_dir) not in sys.path:
            sys.path.insert(0, str(tos_dir))
        from tools import cognition as _cog  # type: ignore

        return _cog
    except ImportError:
        return None


def _unavailable(msg: str = "cognition tools not available"):
    return json.dumps(
        {
            "ok": False,
            "error": {"category": "unavailable", "retryable": False, "message": msg},
        }
    )


def _auto_route_model(prompt: str) -> dict:
    """Deterministic Auto-model triage (hub-architecture.md § Hub settings
    contract): classify the prompt, prefer cos_route_model's empirical pick
    when history exists, else the settings' orchestrator_model."""
    from .settings import _load as _load_hub_settings

    routing_cfg = _load_hub_settings().get("model_routing") or {}
    if not routing_cfg.get("enabled"):
        return {"error": "model 'auto' requires settings.model_routing.enabled"}

    cog = _cognition_module()
    complexity = "COMPLICATED"
    if cog is not None and hasattr(cog, "classify_prompt_heuristic"):
        complexity = cog.classify_prompt_heuristic(prompt)["complexity"]

    routed = ""
    source = "orchestrator_default"
    try:
        from tools.routing import route_model  # type: ignore

        from thinking_os.database import resolve_db_path  # type: ignore

        conn = sqlite3.connect(str(resolve_db_path()))
        try:
            recommendation = route_model(conn, complexity=complexity)
        finally:
            conn.close()
        if int(recommendation.get("data_points") or 0) > 0:
            routed = str(recommendation.get("recommended_model") or "")
            source = "empirical"
    except Exception as exc:
        logger.debug("auto-route empirical lookup failed: %s", exc)

    if not routed:
        routed = str(routing_cfg.get("orchestrator_model") or "")
        source = "orchestrator_default"
    return {"model": routed, "complexity": complexity, "source": source}


def _db_path() -> str | None:
    """Resolve coding-os SQLite DB path via canonical helper.

    Returns None when nothing exists yet (the route returns a typed
    ``unavailable`` envelope in that case).
    """
    try:
        from thinking_os.database import resolve_db_path  # type: ignore
        from web._project_context import current_project_root  # type: ignore[import]

        path = resolve_db_path(current_project_root())
        if path.exists():
            return str(path)
    except Exception as exc:
        logger.debug("project-root db path resolve failed: %s", exc)
    return None
