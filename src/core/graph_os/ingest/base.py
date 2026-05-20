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
    "*.yaml",
    "*.yml",
    "*.go",
    "*.json",
    "*.toml",
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
)


def walk_local(
    root: str | Path,
    *,
    alias: str | None = None,
    include: Iterable[str] = DEFAULT_INCLUDE,
    exclude: Iterable[str] = DEFAULT_EXCLUDE,
    max_files: int = 1_000_000,
    max_size_bytes: int = 50 * 1024 * 1024 * 1024,
) -> IngestPlan:
    """Walk a local folder → IngestPlan with guard rails.

    Defaults sized for monorepo-scale repos (1M files, 50 GB). Callers
    that want stricter caps should pass them explicitly.

    RAISES:       IngestError on caps exceeded.
    """
    root_path = Path(root).resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise IngestError(f"path not found or not a directory: {root_path}")

    include_set = tuple(include)
    exclude_set = set(exclude)

    total_bytes = 0
    collected: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in exclude_set]
        for name in filenames:
            if not any(fnmatch.fnmatchcase(name, pat) for pat in include_set):
                continue
            full = Path(dirpath) / name
            try:
                size = full.stat().st_size
            except OSError:
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
    "DEFAULT_INCLUDE",
    "IngestError",
    "IngestPlan",
    "walk_local",
]
