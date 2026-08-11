"""RAG source configuration and file-walking for the document index.

Owns which files are in scope: the config loader, the walk over each declared
source, exclusion handling, and the reverse lookup that maps one changed file
back to the source config governing it.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("coding_os.doc_indexer")


def load_rag_config(config_path: Path) -> dict:
    """Load and validate the RAG indexer config.

    Defers yaml import so the indexer module is importable in environments
    without pyyaml (e.g. minimal hook environments).

    Args:
        config_path: Path to rag-config.yaml.

    Returns:
        Parsed config dict with `sources` and `exclude` keys.

    Raises:
        FileNotFoundError: if config file missing.
        ValueError: if config schema is invalid.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"RAG config not found: {config_path}")
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "pyyaml is required to load rag-config.yaml — install via pip install pyyaml"
        ) from exc

    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    sources = config.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError(f"rag-config sources must be a list, got {type(sources).__name__}")

    excludes = config.get("exclude", [])
    if not isinstance(excludes, list):
        raise ValueError(f"rag-config exclude must be a list, got {type(excludes).__name__}")

    return {"sources": sources, "exclude": excludes}


def walk_sources(
    sources: list[dict],
    project_root: Path,
    global_excludes: list[str],
) -> list[tuple[Path, dict]]:
    """Walk the configured source paths and return all markdown files with metadata.

    Args:
        sources: List of source config dicts (each with `path`, `type`, optional
                 `exclude`, `priority`, `chunk_size`).
        project_root: Project root the paths are relative to.
        global_excludes: Project-level exclude paths from config.

    Returns:
        List of (file_path, source_config) tuples for every markdown file
        matched by a source and not blocked by an exclude.
    """
    results: list[tuple[Path, dict]] = []
    global_exclude_paths = {(project_root / e).resolve() for e in global_excludes}

    for source in sources:
        rel_path = source.get("path")
        if not rel_path:
            continue
        source_root = (project_root / rel_path).resolve()
        if not source_root.exists():
            logger.debug("Source path missing, skipping: %s", source_root)
            continue

        local_excludes = source.get("exclude", []) or []
        local_exclude_paths = {(source_root / e).resolve() for e in local_excludes}

        if source_root.is_file():
            candidates = [source_root]
        else:
            candidates = sorted(source_root.rglob("*.md"))

        for candidate in candidates:
            if not candidate.is_file() or candidate.suffix != ".md":
                continue
            # Skip if matched by any exclude
            if _is_excluded(candidate, global_exclude_paths | local_exclude_paths):
                continue
            results.append((candidate, source))

    return results


def _is_excluded(file_path: Path, exclude_paths: set[Path]) -> bool:
    """Check whether file_path is inside any of the excluded paths."""
    resolved = file_path.resolve()
    for excluded in exclude_paths:
        try:
            resolved.relative_to(excluded)
            return True
        except ValueError:
            continue
        if resolved == excluded:
            return True
    return False


def _match_source_config(
    file_path: Path,
    sources: list[dict],
    project_root: Path,
    global_excludes: list[str],
) -> dict | None:
    """Return the source_config dict whose scope covers `file_path`, or None."""
    if not file_path.exists():
        return None
    resolved = file_path.resolve()
    project_root_resolved = project_root.resolve()

    try:
        resolved.relative_to(project_root_resolved)
    except ValueError:
        return None

    global_exclude_paths = {(project_root_resolved / e).resolve() for e in global_excludes}
    if _is_excluded(resolved, global_exclude_paths):
        return None

    # Pick the most-specific source (longest matching path) so e.g.
    # docs/architecture/adr/*.md wins over docs/architecture/*.md.
    best: tuple[int, dict] | None = None
    for source in sources:
        rel_path = source.get("path")
        if not rel_path:
            continue
        source_root = (project_root_resolved / rel_path).resolve()
        try:
            resolved.relative_to(source_root)
        except ValueError:
            continue
        local_excludes = source.get("exclude", []) or []
        local_exclude_paths = {(source_root / e).resolve() for e in local_excludes}
        if _is_excluded(resolved, local_exclude_paths):
            continue
        specificity = len(source_root.parts)
        if best is None or specificity > best[0]:
            best = (specificity, source)
    return best[1] if best else None
