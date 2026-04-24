"""core.web.routes.hub — global Hub registry endpoints.

PURPOSE: Expose the ~/.coding-os/registry.json contents so the SPA home
         page can render a project switcher and deep-link into each
         project's /p/<slug>/board.
INPUT:   GET /api/hub/projects.
OUTPUT:  JSON {projects: [{slug, path, created_at}], count}.
DEPENDENCIES: cli.registry (read-only here).
NOTES:   Listed in server.py alongside the other routers.  Stateless.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

router = APIRouter(prefix="/api/hub", tags=["hub"])


@router.get("/projects")
def hub_projects() -> dict:
    """List every registered coding-os project."""
    try:
        from cli.registry import load_registry  # type: ignore
    except Exception:
        return {"projects": [], "count": 0}
    reg = load_registry()
    return {
        "projects": [
            {"slug": p.slug, "path": p.path, "created_at": p.created_at}
            for p in reg.projects
        ],
        "count": len(reg.projects),
    }
