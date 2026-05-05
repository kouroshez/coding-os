"""core.web.routes.hooks — /api/hooks/* HTTP wrappers (T19.4).

PURPOSE: Surface the hook registry (core/hooks/registry.yaml) for the hub
         dashboard so operators can audit which hooks are wired per agent
         + event without grepping the filesystem.
INPUT:   Optional adapter / event filters.
OUTPUT:  JSON list of hook entries.
DEPENDENCIES: cli.hook_renderer (canonical loader).
NOTES:   Read-only, fast — registry.yaml is small. No DB hit.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import unwrap

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

router = APIRouter(prefix="/api/hooks", tags=["hooks"])


@router.get("/list")
async def list_hooks(
    adapter: Optional[str] = Query(None, description="Filter by adapter_scope (claude / codex / cursor)"),
    event: Optional[str] = Query(None, description="Filter by event (PreToolUse / Stop / …)"),
    _rl=Depends(make_rate_limit_dep("hooks.list")),
    _m=Depends(make_metrics_dep("hooks.list")),
):
    """List registered hooks with their event, matcher, scope, category.

    PURPOSE: Hub dashboard — show every hook the runtime would fire so
             operators can audit blast-radius before merging changes.
    INPUT:   adapter / event filters.
    OUTPUT:  {data: {hooks: [...], count}, meta}.
    """
    try:
        from cli.hook_renderer import load_registry  # type: ignore[import]
    except ImportError as exc:
        return unwrap(json.dumps({
            "ok": False,
            "error": {"category": "unavailable", "retryable": False,
                      "message": f"hook_renderer not importable: {exc}"},
        }))

    try:
        entries = load_registry()
    except Exception as exc:
        return unwrap(json.dumps({
            "ok": False,
            "error": {"category": "internal", "retryable": False, "message": str(exc)},
        }))

    rows = []
    for h in entries:
        if adapter and getattr(h, "adapter_scope", None) and h.adapter_scope != adapter:
            continue
        if event and getattr(h, "event", None) != event:
            continue
        rows.append({
            "name": getattr(h, "name", None),
            "event": getattr(h, "event", None),
            "matcher": getattr(h, "matcher", None),
            "category": getattr(h, "category", None),
            "phase": getattr(h, "phase", None),
            "adapter_scope": getattr(h, "adapter_scope", None),
            "script": getattr(h, "script", None),
        })

    return unwrap(json.dumps({
        "ok": True,
        "data": {"hooks": rows, "count": len(rows), "meta": {"layer": "hooks"}},
    }))
