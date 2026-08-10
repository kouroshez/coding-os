"""Find projects that already exist: scan a root, prune the dead, suggest roots.

The import half of the Hub registry — read-only filesystem walks plus the
registry garbage collection they feed.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import Body, Query

from ._hub_shared import (
    _ancestor_with_coding_os,
    _err,
    _is_meta_repo,
    _looks_like_cos_project,
    _resolve_slug_from_registry,
    router,
)

logger = logging.getLogger("coding_os.web.hub")


# Hard caps so a malicious/misconfigured scan can't lock the process.
_SCAN_MAX_DEPTH = 6
_SCAN_MAX_VISITED_DIRS = 5000


@router.post("/registry/scan")
def hub_registry_scan(
    root: str = Body(..., embed=True),
    max_depth: int = Body(_SCAN_MAX_DEPTH, embed=True),
    limit: int = Body(50, embed=True),
):
    """Walk a filesystem root and return every `.coding-os/` project found."""
    if not isinstance(root, str) or not root.strip():
        return _err("validation", "root is required")
    try:
        root_path = Path(root).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        return _err("validation", f"invalid root: {exc}")
    if not root_path.is_dir():
        return _err("not_found", f"root is not a directory: {root_path}", status=404)

    max_depth = max(1, min(_SCAN_MAX_DEPTH, int(max_depth) if max_depth else _SCAN_MAX_DEPTH))
    limit = max(1, min(500, int(limit) if limit else 50))

    _SKIP_DIR_NAMES = {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".coding-os",  # never recurse INTO a cos state dir
        "dist",
        "build",
        ".next",
        ".turbo",
        "Library",
        "Trash",
        ".Trash",
    }

    # Snapshot registered paths for the "already_registered" annotation.
    registered_paths: set[str] = set()
    try:
        from cli.registry import load_registry  # type: ignore

        for p in load_registry().projects:
            try:
                registered_paths.add(str(Path(p.path).resolve()))
            except (OSError, RuntimeError):
                continue
    except Exception as exc:
        logger.debug("scan: could not snapshot registry: %s", exc)

    hits: list[dict] = []
    visited = 0
    hit_limit_reached = False
    depth_limit_reached = False

    # BFS so shallow hits surface first (a consumer usually cares about
    # "~/code/my-app" before "~/code/my-app/backend/vendor/old/...").
    from collections import deque

    queue: deque[tuple[Path, int]] = deque([(root_path, 0)])
    while queue:
        if len(hits) >= limit:
            hit_limit_reached = True
            break
        if visited >= _SCAN_MAX_VISITED_DIRS:
            break
        current, depth = queue.popleft()
        visited += 1
        if not current.is_dir():
            continue
        if _looks_like_cos_project(current):
            resolved = str(current.resolve())
            hits.append(
                {
                    "path": resolved,
                    "slug": _resolve_slug_from_registry(current),
                    "already_registered": resolved in registered_paths,
                }
            )
            # Don't recurse into a cos project; nested cos repos are
            # extremely rare and the skip keeps scans snappy.
            continue
        if depth >= max_depth:
            depth_limit_reached = True
            continue
        try:
            children = list(current.iterdir())
        except (OSError, PermissionError):
            continue
        for child in children:
            if not child.is_dir():
                continue
            if child.name in _SKIP_DIR_NAMES:
                continue
            if child.name.startswith("."):
                # Don't descend into dotfiles directories (browser caches,
                # editor state); .coding-os is explicitly skipped above.
                continue
            queue.append((child, depth + 1))

    return {
        "data": {
            "root": str(root_path),
            "hits": hits,
            "count": len(hits),
            "visited_dirs": visited,
            "hit_limit_reached": hit_limit_reached,
            "depth_limit_reached": depth_limit_reached,
        },
        "meta": {
            "layer": "hub",
            "source": "hub.registry_scan",
            "max_depth": max_depth,
            "limit": limit,
        },
    }


# ---------------------------------------------------------------------------
# POST /api/hub/registry/gc
# ---------------------------------------------------------------------------


@router.post("/registry/gc")
def hub_registry_gc(
    dry_run: bool = Body(False, embed=True),
):
    """Remove registry entries whose directory no longer exists."""
    try:
        from cli.registry import load_registry, save_registry  # type: ignore
    except Exception as exc:
        return _err("unavailable", f"cli.registry unavailable: {exc}", status=503)

    try:
        reg = load_registry()
    except Exception as exc:
        return _err("internal", f"load_registry failed: {exc}", status=500)

    kept: list[dict] = []
    removed: list[dict] = []
    for entry in reg.projects:
        path = Path(entry.path)
        alive = _looks_like_cos_project(path)
        item = {"slug": entry.slug, "path": entry.path, "created_at": entry.created_at}
        (kept if alive else removed).append(item)

    if not dry_run and removed:
        reg.projects = [p for p in reg.projects if _looks_like_cos_project(Path(p.path))]
        try:
            save_registry(reg)
        except Exception as exc:
            return _err("internal", f"save_registry failed: {exc}", status=500)

    return {
        "data": {
            "kept": kept,
            "removed": removed,
            "dry_run": bool(dry_run),
            "kept_count": len(kept),
            "removed_count": len(removed),
        },
        "meta": {"layer": "hub", "source": "hub.registry_gc"},
    }


# ---------------------------------------------------------------------------
# GET /api/hub/suggest-roots — surface likely scan roots for the UI
# ---------------------------------------------------------------------------


@router.get("/suggest-roots")
def hub_suggest_roots(depth: int = Query(0)):
    """Return sensible default scan roots for the UI's import wizard."""
    _ = depth  # reserved — currently unused; keeps the route parameter list stable
    candidates: list[Path] = [
        Path(os.environ.get("COS_PROJECT_ROOT") or os.getcwd()).resolve(),
        Path.home() / "code",
        Path.home() / "Projects",
        Path.home() / "Developer",
        Path.home(),
    ]
    seen: set[str] = set()
    suggestions: list[str] = []
    for c in candidates:
        try:
            resolved = str(c.resolve())
        except (OSError, RuntimeError):
            continue
        if resolved in seen:
            continue
        if not c.is_dir():
            continue
        seen.add(resolved)
        suggestions.append(resolved)
    # The Composer scaffolds INTO the picked root, so it needs the subset that
    # `_validate_init_inputs` would accept; import/scan happily target the rest.
    scaffoldable = [
        s
        for s in suggestions
        if not _is_meta_repo(Path(s)) and _ancestor_with_coding_os(Path(s)) is None
    ]
    return {
        "data": {"suggestions": suggestions, "scaffoldable": scaffoldable},
        "meta": {"layer": "hub", "source": "hub.suggest_roots"},
    }
