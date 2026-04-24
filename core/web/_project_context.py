"""core.web._project_context — per-request project scope.

PURPOSE: Let a single uvicorn process serve multiple coding-os projects
         by carrying the active project root through each request via a
         ContextVar.  Routes that need the project root or sqlite DB
         should call `current_project_root()` / `current_db_path()` and
         fall back to env vars if no project is bound.
INPUT:   Set by ProjectScopeMiddleware when the URL matches /api/p/<slug>/.
OUTPUT:  Context accessors used by route helpers (`_db_conn`, etc.).
DEPENDENCIES: stdlib contextvars + the registry module under cli/.
NOTES:   ContextVar is task-local so concurrent ASGI requests do not
         leak project scope across each other.
"""
from __future__ import annotations

import os
import sys
from contextvars import ContextVar
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Ensure the cli/ module is importable (registry lives there, outside
# core/web/, so the web server can call it without re-implementing the
# schema).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


_current_project: ContextVar[Path | None] = ContextVar(
    "cos_current_project", default=None,
)


def current_project_root() -> Path:
    """Return the active project root for this request (or env fallback).

    PURPOSE: Single resolver every route uses.  Prefers the ContextVar
             set by middleware; falls back to COS_PROJECT_ROOT / cwd so
             the old single-project launch path keeps working.
    """
    bound = _current_project.get()
    if bound is not None:
        return bound
    return Path(os.environ.get("COS_PROJECT_ROOT") or os.getcwd()).resolve()


def current_db_path() -> Path:
    """Return the active sqlite DB path (project-scoped or env fallback)."""
    bound = _current_project.get()
    if bound is not None:
        return bound / ".coding-os" / "thinking-os.db"
    env = os.environ.get("COS_DB_PATH")
    if env:
        return Path(env)
    return current_project_root() / ".coding-os" / "thinking-os.db"


class ProjectScopeMiddleware(BaseHTTPMiddleware):
    """Rewrite /api/p/<slug>/* → /api/* and bind slug's project root.

    PURPOSE: Enable Hub-style multi-project serving.  When a request
             arrives at /api/p/<slug>/foo, this middleware:
               1. looks up <slug> in the global registry,
               2. binds the project root to the ContextVar,
               3. rewrites the ASGI path to /api/foo so all existing
                  routes match unchanged.
             Requests without /api/p/<slug>/ pass through untouched.
    NOTES:   404 with a clear message if the slug is not registered.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path: str = request.url.path
        if path.startswith("/api/p/"):
            remainder = path[len("/api/p/") :]
            slug, _, rest = remainder.partition("/")
            if not slug:
                return JSONResponse(
                    {"detail": "missing project slug"},
                    status_code=400,
                )
            project_root = _resolve_slug(slug)
            if project_root is None:
                return JSONResponse(
                    {"detail": f"project slug {slug!r} not in registry; run `cos registry add`"},
                    status_code=404,
                )
            token = _current_project.set(project_root)
            new_path = "/api/" + rest if rest else "/api/"
            request.scope["path"] = new_path
            request.scope["raw_path"] = new_path.encode("utf-8")
            try:
                return await call_next(request)
            finally:
                _current_project.reset(token)
        return await call_next(request)


def _resolve_slug(slug: str) -> Path | None:
    """Look up a slug → absolute path via the global registry."""
    try:
        from cli.registry import load_registry  # type: ignore
    except Exception:
        return None
    try:
        reg = load_registry()
    except Exception:
        return None
    for entry in reg.projects:
        if entry.slug == slug:
            candidate = Path(entry.path).resolve()
            if (candidate / ".coding-os").is_dir():
                return candidate
            return None
    return None
