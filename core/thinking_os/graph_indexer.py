"""graph_os indexing harness (Phase I.10 — full-hybrid indexing lifecycle)."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence


_CORE_DIR = Path(__file__).resolve().parent.parent
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

logger = logging.getLogger("coding_os.graph_indexer")


_EXTRACTOR_SUFFIXES = (".py", ".ts", ".tsx", ".sh", ".yaml", ".yml", ".md", ".go")


def _extractor_suffixes() -> tuple[str, ...]:
    return _EXTRACTOR_SUFFIXES


def _load_graph_os():
    """Late import so tests can monkey-patch sys.path before import."""
    from graph_os.backends.sqlite_backend import SqliteBackend  # noqa: PLC0415
    from graph_os.extractors import (  # noqa: PLC0415
        code_python,
        code_shell,
        code_ts,
        code_yaml,
        contracts,
        md_links,
        task_deps,
    )
    from graph_os.ingest import walk_local  # noqa: PLC0415

    return {
        "SqliteBackend": SqliteBackend,
        "walk_local": walk_local,
        "extractors": {
            ".py": [code_python.extract, contracts.extract],
            ".ts": [code_ts.extract, contracts.extract],
            ".tsx": [code_ts.extract, contracts.extract],
            ".sh": [code_shell.extract],
            ".yaml": [code_yaml.extract],
            ".yml": [code_yaml.extract],
            ".go": [contracts.extract],
        },
        "md_links": md_links.extract,
        "task_deps": task_deps.extract,
    }


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class IndexReport:
    """Per-run summary. Same shape for bulk, incremental, and background."""

    project_root: str
    backend: str
    files_seen: int = 0
    files_indexed: int = 0
    files_skipped_unchanged: int = 0
    files_skipped_unsupported: int = 0
    files_errored: int = 0
    nodes_upserted: int = 0
    edges_upserted: int = 0
    duration_ms: int = 0
    errors: list[str] = field(default_factory=list)
    mode: str = "bulk"  # bulk | incremental | background

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Content-hash tracking
# ---------------------------------------------------------------------------


def _is_unchanged(backend: Any, rel_path: str, content_hash: str) -> bool:
    """Return True if any code:file / doc:file node for this path already
    carries the same content_hash. Skipping is then safe.
    """
    if not content_hash:
        return False
    # Also check any task:file node whose `file_path` metadata matches —
    # task_deps emits `task:file:TASK-NNN` uids so the path-keyed probes
    # above miss them. Fall back to a light SELECT on file_path when a
    # content_hash match exists for this exact path.
    for uid in (f"code:file:{rel_path}", f"doc:file:{rel_path}"):
        node = backend.get_node(uid)
        if node is not None and node.content_hash == content_hash:
            return True
    # Generic path match (for task:file and friends) — cheap indexed query.
    try:
        row = backend._conn.execute(  # type: ignore[attr-defined]
            "SELECT content_hash FROM graph_nodes WHERE file_path = ? "
            "AND content_hash IS NOT NULL LIMIT 1",
            (rel_path,),
        ).fetchone()
    except Exception as exc:  # noqa: BLE001
        logger.debug("path-match hash probe failed: %s", exc)
        return False
    return bool(row and row[0] == content_hash)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _extractors_for(rel_path: str, reg: dict[str, Any]) -> list:
    suffix = _suffix(rel_path)
    if suffix == ".md":
        if "/tasks/" in rel_path or rel_path.startswith("tasks/"):
            return [reg["task_deps"], reg["md_links"]]
        return [reg["md_links"]]
    return list(reg["extractors"].get(suffix, []))


def _suffix(path: str) -> str:
    idx = path.rfind(".")
    return path[idx:].lower() if idx >= 0 else ""


def _safe_relpath(file_path: Path, project_root: Path) -> str:
    try:
        return str(file_path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        return str(file_path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def index_single_file(
    *,
    backend: Any,
    project_root: Path,
    file_path: Path,
    force: bool = False,
) -> IndexReport:
    """Single-file incremental — PostToolUse hook's target."""
    started = time.monotonic()
    rel_path = _safe_relpath(file_path, project_root)
    report = IndexReport(
        project_root=str(project_root),
        backend=getattr(backend, "backend_id", "sqlite"),
        mode="incremental",
    )

    reg = _load_graph_os()
    extractors = _extractors_for(rel_path, reg)
    if not extractors:
        report.files_seen = 1
        report.files_skipped_unsupported = 1
        report.duration_ms = int((time.monotonic() - started) * 1000)
        return report

    report.files_seen = 1
    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        report.files_errored = 1
        report.errors.append(f"read {rel_path}: {type(exc).__name__}")
        report.duration_ms = int((time.monotonic() - started) * 1000)
        return report

    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    if not force and _is_unchanged(backend, rel_path, content_hash):
        report.files_skipped_unchanged = 1
        report.duration_ms = int((time.monotonic() - started) * 1000)
        return report

    nodes_total = 0
    edges_total = 0
    for extractor in extractors:
        try:
            result = extractor(rel_path, content)
            n, e = backend.bulk_upsert(result.nodes, result.edges)
            nodes_total += n
            edges_total += e
        except Exception as exc:  # noqa: BLE001
            report.files_errored = 1
            report.errors.append(
                f"extract {rel_path} via {extractor.__module__}: "
                f"{type(exc).__name__}: {exc}"
            )
    if report.files_errored == 0:
        report.files_indexed = 1
    report.nodes_upserted = nodes_total
    report.edges_upserted = edges_total
    report.duration_ms = int((time.monotonic() - started) * 1000)
    return report


def index_project(
    *,
    backend: Any,
    project_root: Path,
    force: bool = False,
    max_files: int = 50_000,
    include_suffixes: Sequence[str] | None = None,
    file_filter: Any = None,
    progress: Any = None,
) -> IndexReport:
    """Full walk — CLI `cos graph-reindex` + background reindex."""
    started = time.monotonic()
    reg = _load_graph_os()
    plan = reg["walk_local"](project_root, max_files=max_files)

    report = IndexReport(
        project_root=str(project_root),
        backend=getattr(backend, "backend_id", "sqlite"),
        mode="bulk",
    )

    include = tuple(s.lower() for s in (include_suffixes or _EXTRACTOR_SUFFIXES))

    for file_path in plan.files:
        report.files_seen += 1
        if progress is not None:
            try:
                progress(report.files_seen, len(plan.files))
            except Exception as exc:  # noqa: BLE001
                logger.debug("progress callback raised: %s", exc)

        rel = _safe_relpath(file_path, project_root)
        if file_filter is not None and not file_filter(rel):
            report.files_skipped_unsupported += 1
            continue
        if _suffix(rel) not in include:
            report.files_skipped_unsupported += 1
            continue

        extractors = _extractors_for(rel, reg)
        if not extractors:
            report.files_skipped_unsupported += 1
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            report.files_errored += 1
            report.errors.append(f"read {rel}: {type(exc).__name__}")
            continue

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        if not force and _is_unchanged(backend, rel, content_hash):
            report.files_skipped_unchanged += 1
            continue

        indexed_this_file = False
        for extractor in extractors:
            try:
                result = extractor(rel, content)
                n, e = backend.bulk_upsert(result.nodes, result.edges)
                report.nodes_upserted += n
                report.edges_upserted += e
                indexed_this_file = True
            except Exception as exc:  # noqa: BLE001
                report.files_errored += 1
                report.errors.append(
                    f"extract {rel} via {extractor.__module__}: "
                    f"{type(exc).__name__}: {exc}"
                )
        if indexed_this_file:
            report.files_indexed += 1

    report.duration_ms = int((time.monotonic() - started) * 1000)
    return report


# ---------------------------------------------------------------------------
# Backend construction
# ---------------------------------------------------------------------------


def open_backend(db_path: str | Path) -> Any:
    """Open the configured GraphBackend against `db_path`. SQLite-first."""
    reg = _load_graph_os()
    from db import init_db  # type: ignore  # noqa: PLC0415

    db_p = Path(db_path)
    db_p.parent.mkdir(parents=True, exist_ok=True)
    conn = init_db(str(db_p))
    return reg["SqliteBackend"](conn=conn)


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--file", default=None, help="Single file (incremental).")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-files", type=int, default=50_000)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    if not project_root.exists():
        print(f"ERROR: project root not found: {project_root}", file=sys.stderr)
        return 2

    backend = open_backend(args.db)
    try:
        if args.file:
            report = index_single_file(
                backend=backend,
                project_root=project_root,
                file_path=Path(args.file).resolve(),
                force=args.force,
            )
        else:
            progress = None
            if not args.quiet:
                def _progress(seen: int, total: int) -> None:
                    if seen % 50 == 0 or seen == total:
                        print(
                            f"[graph-reindex] {seen}/{total}",
                            file=sys.stderr,
                        )

                progress = _progress
            report = index_project(
                backend=backend,
                project_root=project_root,
                force=args.force,
                max_files=args.max_files,
                progress=progress,
            )
        print(json.dumps(report.to_dict(), indent=2, default=str))
        return 0 if not report.errors else 1
    finally:
        try:
            backend.close()
        except Exception as exc:  # noqa: BLE001
            logger.debug("backend close suppressed: %s", exc)


if __name__ == "__main__":
    raise SystemExit(main())
