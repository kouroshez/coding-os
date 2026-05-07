"""core.web._project_context — per-request project scope."""
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
    """Return the active project root for this request (or env fallback)."""
    bound = _current_project.get()
    if bound is not None:
        return bound
    return Path(os.environ.get("COS_PROJECT_ROOT") or os.getcwd()).resolve()


def current_db_path() -> Path:
    """Return the active sqlite DB path (project-scoped or env fallback).

    Delegates filename + env resolution to the canonical helper in
    ``core.thinking_os.db.resolve_db_path`` — single source of truth so
    a future filename change is one edit, not 30. Legacy `thinking_os.db`
    is auto-renamed by `migrate_legacy_db_filename()` on first init_db().
    """
    from thinking_os.database import resolve_db_path  # type: ignore
    bound = _current_project.get()
    if bound is not None:
        return resolve_db_path(bound)
    return resolve_db_path(current_project_root())


class ProjectScopeMiddleware(BaseHTTPMiddleware):
    """Rewrite /api/p/<slug>/* → /api/* and bind slug's project root."""

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
        reg = load_registry()
    except Exception:  # noqa: BLE001 — registry optional, fall through to cwd
        reg = None
    if reg is not None:
        for entry in reg.projects:
            if entry.slug == slug:
                candidate = Path(entry.path).resolve()
                if (candidate / ".coding-os").is_dir():
                    return candidate
                return None

    cwd = Path(os.environ.get("COS_PROJECT_ROOT") or os.getcwd()).resolve()
    if not (cwd / ".coding-os").is_dir():
        return None
    # Match the same slug rule hub.py / registry use, so the auto-listed
    # cwd entry and the middleware agree on spelling (e.g. "coding os"
    # becomes "coding-os" in both places — not just one).
    cwd_slug = cwd.name.lower().strip() or "project"
    try:
        from cli.registry import _derive_slug  # type: ignore
        cwd_slug = _derive_slug(cwd)
    except Exception as exc:  # noqa: BLE001 — slug is UX; fall through
        import logging as _logging
        _logging.getLogger("coding_os.web.context").debug(
            "cli.registry._derive_slug unavailable: %s", exc,
        )
    if cwd_slug == slug.lower().strip():
        return cwd
    return None
