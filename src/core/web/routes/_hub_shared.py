"""Leaf every hub endpoint stands on: the router, the error envelope, and
"is this directory a coding-os project?".

Owning the APIRouter here rather than in the facade is what keeps the endpoint
modules acyclic — each one imports this leaf, and no part module imports another
part module. The sys.path bootstrap runs here for the same reason: whichever hub
module is imported first, `cli.*` resolves.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logger = logging.getLogger("coding_os.web.hub")
router = APIRouter(prefix="/api/hub", tags=["hub"])

_PROJECT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _looks_like_cos_project(path: Path) -> bool:
    """Quick heuristic: directory exists and has .coding-os/ inside."""
    try:
        return path.is_dir() and (path / ".coding-os").is_dir()
    except OSError:
        return False


def _is_hub_state_dir(coding_os: Path) -> bool:
    """True when this .coding-os/ is the GLOBAL hub state dir, not a project's.

    The global ~/.coding-os/ carries the hub registry + pid; a project's
    .coding-os/ never does (hub-architecture.md § address spaces). Lets the
    home/global dir be rejected as a phantom "runtime-cwd" project.
    """
    try:
        return (coding_os / "registry.json").is_file() or (coding_os / "hub.pid").is_file()
    except OSError:
        return False


def _is_meta_repo(path: Path) -> bool:
    """True when `path` is the coding-os meta-repo checkout itself.

    Recognises the dogfood case: the meta-repo lives at
    `<somewhere>/coding-os/` AND ships its own `.coding-os/`
    (dogfood — Principle P5). It must never be flagged as "nested
    inside another coding-os project" just because a higher-up
    ancestor (e.g. `~/.coding-os/` scratch dir) happens to have a
    `.coding-os/`.
    """
    try:
        return (
            (path / "src" / "cli" / "main.py").is_file()
            and (path / "src" / "core" / "thinking_os" / "server.py").is_file()
            and (path / "pyproject.toml").is_file()
        )
    except OSError:
        return False


def _is_registered_project(path: Path) -> bool:
    """True iff `path` (resolved) is recorded in the cli registry.

    The nested-project check should only fire when the enclosing
    ancestor is an *actual registered project*. A stray
    `~/.coding-os/` (left over from a test run, or the user's
    scratch dir) is not a project — blocking on it has rejected
    legitimate contributor checkouts (issue reported 2026-05-23).
    """
    try:
        from cli.registry import load_registry  # type: ignore

        reg = load_registry()
    except Exception:
        return False
    target = str(path.resolve())
    for p in reg.projects:
        try:
            if str(Path(p.path).resolve()) == target:
                return True
        except (OSError, RuntimeError):
            continue
    return False


def _ancestor_with_coding_os(path: Path) -> Path | None:
    """Walk parents looking for an enclosing **registered** coding-os
    project root.

    Returns the first ancestor (strictly above `path`) that has a
    `.coding-os/` directory AND is recorded in the cli registry —
    a true nesting violation. An ancestor with just `.coding-os/`
    on disk but not in the registry is treated as noise (scratch,
    leftover) and ignored.

    Also skips the check entirely when `path` is the meta-repo
    itself (dogfood — see `_is_meta_repo`).
    """
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        return None
    if _is_meta_repo(resolved):
        return None
    for parent in resolved.parents:
        try:
            if (parent / ".coding-os").is_dir() and _is_registered_project(parent):
                return parent
        except OSError:
            continue
    return None


def _resolve_slug_from_registry(cwd: Path) -> str:
    """Match cli.registry._derive_slug so UI and API agree on spelling."""
    try:
        from cli.registry import _derive_slug  # type: ignore

        return _derive_slug(cwd)
    except Exception as exc:
        logger.debug("cli.registry._derive_slug unavailable: %s", exc)
        return cwd.name.lower().strip() or "project"


def _derive_runtime_entry() -> dict | None:
    """Return an in-memory entry for the cwd project when it's a cos repo."""
    cwd = Path(os.environ.get("COS_PROJECT_ROOT") or os.getcwd()).resolve()
    # $HOME hosts the GLOBAL hub state at ~/.coding-os/ — never a project.
    try:
        if cwd == Path.home().resolve():
            return None
    except (OSError, RuntimeError):
        pass
    if not _looks_like_cos_project(cwd):
        return None
    # A .coding-os/ carrying the hub registry/pid is the global state dir,
    # not a project root (e.g. the Hub booted from a non-home COS_HOME).
    if _is_hub_state_dir(cwd / ".coding-os"):
        return None
    # .coding-os/ only exists at the project root.  A nested .coding-os/
    # inside another project (e.g. src/core/web/ui/.coding-os/ left over
    # from a test run) must NEVER surface as a separate project entry —
    # we'd hijack the Hub's "default" slot with a stray dir.
    if _ancestor_with_coding_os(cwd) is not None:
        return None
    return {
        "slug": _resolve_slug_from_registry(cwd),
        "path": str(cwd),
        "created_at": "",
        "source": "runtime-cwd",
    }


def _err(category: str, message: str, *, status: int = 400) -> JSONResponse:
    """Shared error-envelope shape matching the rest of /api/*."""
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "category": category,
                "retryable": False,
                "message": message,
            },
        },
    )


def _validate_project_path(raw: str) -> tuple[Path | None, JSONResponse | None]:
    """Sanitize an incoming project-path string for registry mutations."""
    if not isinstance(raw, str) or not raw.strip():
        return None, _err("validation", "path is required and must be a non-empty string")
    try:
        path = Path(raw).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        return None, _err("validation", f"invalid path: {exc}")
    if not path.is_dir():
        return None, _err("not_found", f"path is not a directory: {path}", status=404)
    if not _looks_like_cos_project(path):
        return None, _err(
            "validation",
            f"{path} has no .coding-os/ — run `cos init` there first",
        )
    ancestor = _ancestor_with_coding_os(path)
    if ancestor is not None:
        return None, _err(
            "validation",
            (
                f"{path} sits inside {ancestor} which is already a coding-os "
                "project — .coding-os/ must only exist at the project root. "
                "Remove the nested .coding-os/ directory."
            ),
        )
    return path, None
