"""Local filesystem ingestion + shared IngestPlan type (I.11)."""

from __future__ import annotations

import fnmatch
import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("graph_os.ingest.base")


class IngestError(RuntimeError):
    """Raised when a guard rail trips (size / file-count / timeout)."""


@dataclass
class IngestPlan:
    """Normalised view of "a set of files to index"."""

    alias: str
    root: Path
    files: list[Path] = field(default_factory=list)
    source: str = "local"  # "local" | "github" | "zip"
    metadata: dict[str, object] = field(default_factory=dict)

    def iter_files(self) -> Iterable[Path]:
        yield from self.files


# ---------------------------------------------------------------------------
# Local walk
# ---------------------------------------------------------------------------


DEFAULT_INCLUDE = (
    "*.py",
    "*.ts",
    "*.tsx",
    "*.md",
    "*.sh",
    "*.php",
    "*.yaml",
    "*.yml",
    "*.go",
    "*.json",
    "*.toml",
    "*.js",
    "*.jsx",
    "*.mjs",
    "*.cjs",
)
DEFAULT_EXCLUDE = (
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    ".build",
    ".coding-os",
    ".claude",
    ".codex",
    ".cursor",
    ".agents",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    # Build / dependency output dirs for the shipped stacks. Excluded for
    # the same reason as node_modules: generated artifacts pollute the
    # graph and are never source. (Mitigates the lack of .gitignore
    # awareness — see COS_GRAPH_EXCLUDE_PATHS for project-specific extras.)
    ".next",
    ".nuxt",
    ".svelte-kit",
    ".turbo",
    ".gradle",
    ".terraform",
    "Pods",
    "vendor",
    "target",
)

# Path-segment excludes: pruned when this exact relative-path sequence
# appears anywhere under the walked root. Distinct from DEFAULT_EXCLUDE
# (folder-name match) so the meta-repo can drop scaffolded test fixtures
# (`tests/golden/<adapter>_<stack>/...` mirrors of real repo structure
# rendered by cos init test scaffolds) without also excluding a folder
# literally named "golden" in a consumer project. 6.1k nodes / 16 % of
# graph were coming from these mirrors and surfacing as duplicate spine
# entries in the Hub UI.
DEFAULT_EXCLUDE_PATHS = ("tests/golden",)


def walk_local(
    root: str | Path,
    *,
    alias: str | None = None,
    include: Iterable[str] = DEFAULT_INCLUDE,
    exclude: Iterable[str] = DEFAULT_EXCLUDE,
    exclude_paths: Iterable[str] = DEFAULT_EXCLUDE_PATHS,
    max_files: int = 1_000_000,
    max_size_bytes: int = 50 * 1024 * 1024 * 1024,
    max_file_bytes: int | None = None,
) -> IngestPlan:
    """Walk a local folder → IngestPlan with guard rails.

    Defaults sized for monorepo-scale repos (1M files, 50 GB). Callers
    that want stricter caps should pass them explicitly. ``max_file_bytes``
    skips (does NOT abort on) any single file larger than the cap — a
    vendored multi-MB lockfile/minified asset is dropped, not read whole
    into memory. Defaults to ``COS_GRAPH_MAX_FILE_BYTES`` env or 2 MB.

    RAISES:       IngestError on aggregate caps exceeded.
    """
    root_path = Path(root).resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise IngestError(f"path not found or not a directory: {root_path}")

    if max_file_bytes is None:
        try:
            max_file_bytes = int(os.environ.get("COS_GRAPH_MAX_FILE_BYTES", "") or 2 * 1024 * 1024)
        except ValueError:
            max_file_bytes = 2 * 1024 * 1024

    include_set = tuple(include)
    exclude_set = set(exclude)
    # Normalise to forward-slash POSIX form for stable substring match
    # regardless of host filesystem. Empty patterns are silently dropped
    # so an env-var override like COS_GRAPH_EXCLUDE_PATHS="" deactivates
    # the feature cleanly.
    exclude_paths_set = {p.strip("/").replace(os.sep, "/") for p in exclude_paths if p}

    total_bytes = 0
    collected: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Folder-name pruning (cheap, runs first).
        dirnames[:] = [d for d in dirnames if d not in exclude_set]
        # Relative-path pruning — drop subtrees whose rel-path contains
        # any configured segment sequence (e.g. tests/golden mirrors).
        if exclude_paths_set:
            rel = Path(dirpath).relative_to(root_path).as_posix()
            # rel == "." at the root; segment substring match works for
            # nested matches like "src/old/tests/golden/...". The "/"
            # suffix avoids matching "tests/golden_clone" by accident.
            if any(rel == p or rel.startswith(p + "/") for p in exclude_paths_set):
                dirnames.clear()
                continue
        for name in filenames:
            if not any(fnmatch.fnmatchcase(name, pat) for pat in include_set):
                continue
            full = Path(dirpath) / name
            # Skip symlinks — the target is indexed on its own pass, so a
            # symlink node (e.g. CLAUDE.md -> AGENTS.md) would just be an
            # orphan duplicate that nothing links to.
            if full.is_symlink():
                continue
            try:
                size = full.stat().st_size
            except OSError:
                continue
            # Per-file cap: skip oversized single files (generated/minified
            # /vendored) instead of reading them whole into memory.
            if max_file_bytes and size > max_file_bytes:
                logger.debug("skip oversized file %s (%d > %d bytes)", full, size, max_file_bytes)
                continue
            total_bytes += size
            if total_bytes > max_size_bytes:
                raise IngestError(f"ingest aborted: total size exceeds {max_size_bytes} bytes")
            collected.append(full)
            if len(collected) > max_files:
                raise IngestError(f"ingest aborted: file count exceeds {max_files}")

    return IngestPlan(
        alias=alias or root_path.name,
        root=root_path,
        files=collected,
        source="local",
        metadata={"total_bytes": total_bytes},
    )


__all__ = [
    "DEFAULT_EXCLUDE",
    "DEFAULT_EXCLUDE_PATHS",
    "DEFAULT_INCLUDE",
    "IngestError",
    "IngestPlan",
    "walk_local",
]
