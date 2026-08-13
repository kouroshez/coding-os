"""Local filesystem ingestion + shared IngestPlan type (I.11)."""

from __future__ import annotations

import fnmatch
import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

try:
    import pathspec as _pathspec
except Exception:  # pragma: no cover - optional dep; walk degrades to denylist
    _pathspec = None

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
    # Polyglot baseline (code_generic extractor). Routed in
    # reindex_dispatch._EXT_MAP; symbols extracted only when the language's
    # tree-sitter grammar is installed (rust/ruby ship by default).
    "*.rs",
    "*.rb",
    "*.java",
    "*.c",
    "*.h",
    "*.cc",
    "*.cpp",
    "*.cxx",
    "*.hpp",
    "*.hh",
    "*.cs",
    "*.scala",
    "*.kt",
    "*.kts",
    "*.lua",
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


def _gitignore_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _path_gitignored(rel_posix: str, specs: list[tuple[str, object]], *, is_dir: bool) -> bool:
    # Ignored if ANY applicable .gitignore spec matches. Each spec's patterns
    # are relative to the directory that declared it, so the path is re-based
    # onto that directory before matching. Directories are probed with a
    # trailing slash so dir-only patterns (`build/`) match the directory node.
    for base, spec in specs:
        if base:
            if rel_posix == base or rel_posix.startswith(base + "/"):
                sub = rel_posix[len(base) + 1 :]
            else:
                continue
        else:
            sub = rel_posix
        if not sub:
            continue
        probe = sub + "/" if is_dir else sub
        if spec.match_file(probe):
            return True
    return False


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

    # .gitignore-aware exclusion, additive over the static denylist. When
    # pathspec is unavailable the feature is skipped and the denylist remains
    # the backstop. Specs accumulate top-down: .git/info/exclude + the root
    # .gitignore act at the repo root; a nested .gitignore applies only to
    # its own subtree (re-based in _path_gitignored). This makes the walk
    # exclude exactly what `git status` ignores — no more, no less.
    gitignore_specs: list[tuple[str, object]] = []
    use_gitignore = _pathspec is not None
    if use_gitignore:
        info_exclude = root_path / ".git" / "info" / "exclude"
        if info_exclude.is_file():
            lines = _gitignore_lines(info_exclude)
            if lines:
                gitignore_specs.append(("", _pathspec.GitIgnoreSpec.from_lines(lines)))

    total_bytes = 0
    collected: list[Path] = []
    # Oversized files are dropped (not read into memory). Track them so the
    # drop is visible — a silently-skipped large source file is a coverage
    # gap, not a no-op (TASK-293 logging-completeness).
    skipped_oversize: list[str] = []
    # Symlinks (target indexed on its own pass) and unreadable files are also
    # skipped — count them so the summary can surface that they happened
    # (TASK-302). Counts, not paths: symlinks can be numerous and the count
    # is the actionable signal.
    skipped_symlink = 0
    skipped_read_error = 0
    for dirpath, dirnames, filenames in os.walk(root_path):
        rel_dir = Path(dirpath).relative_to(root_path).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir

        # Load a nested .gitignore declared here (top-down walk guarantees
        # ancestors are already loaded before their children are visited).
        if use_gitignore:
            gi = Path(dirpath) / ".gitignore"
            if gi.is_file():
                lines = _gitignore_lines(gi)
                if lines:
                    gitignore_specs.append((rel_dir, _pathspec.GitIgnoreSpec.from_lines(lines)))

        # Folder-name pruning (cheap, runs first), then .gitignore subtree
        # pruning — skip whole ignored directories before descending.
        pruned = [d for d in dirnames if d not in exclude_set]
        if gitignore_specs:
            pruned = [
                d
                for d in pruned
                if not _path_gitignored(
                    f"{rel_dir}/{d}" if rel_dir else d, gitignore_specs, is_dir=True
                )
            ]
        dirnames[:] = pruned

        # Relative-path pruning — drop subtrees whose rel-path contains
        # any configured segment sequence (e.g. tests/golden mirrors). The
        # "/" suffix avoids matching "tests/golden_clone" by accident.
        if (
            exclude_paths_set
            and rel_dir
            and any(rel_dir == p or rel_dir.startswith(p + "/") for p in exclude_paths_set)
        ):
            dirnames.clear()
            continue
        for name in filenames:
            if not any(fnmatch.fnmatchcase(name, pat) for pat in include_set):
                continue
            if gitignore_specs and _path_gitignored(
                f"{rel_dir}/{name}" if rel_dir else name, gitignore_specs, is_dir=False
            ):
                continue
            full = Path(dirpath) / name
            # Skip symlinks — the target is indexed on its own pass, so a
            # symlink node (e.g. CLAUDE.md -> AGENTS.md) would just be an
            # orphan duplicate that nothing links to.
            if full.is_symlink():
                skipped_symlink += 1
                continue
            try:
                size = full.stat().st_size
            except OSError:
                skipped_read_error += 1
                continue
            # Per-file cap: skip oversized single files (generated/minified
            # /vendored) instead of reading them whole into memory.
            if max_file_bytes and size > max_file_bytes:
                rel_file = full.relative_to(root_path).as_posix()
                logger.warning(
                    "skip oversized file %s (%d > %d bytes) — not indexed",
                    rel_file,
                    size,
                    max_file_bytes,
                )
                skipped_oversize.append(rel_file)
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
        metadata={
            "total_bytes": total_bytes,
            "skipped_oversize": skipped_oversize,
            "skipped_symlink": skipped_symlink,
            "skipped_read_error": skipped_read_error,
        },
    )


__all__ = [
    "DEFAULT_EXCLUDE",
    "DEFAULT_EXCLUDE_PATHS",
    "DEFAULT_INCLUDE",
    "IngestError",
    "IngestPlan",
    "walk_local",
]
