"""graph-os — task dependency extractor (I.3).

PURPOSE:  Turn a `docs/tasks/TASK-NNN-slug.md` file into GraphNodes +
          GraphEdges: `task:file` nodes + `depends_on` / `blocks` /
          `references_doc` edges. Git-derived `produces_code` edges
          live behind a separate entry point so the orchestrator (I.9)
          can batch-compute them outside the per-file write path.
INPUT:    task file path + raw content (pure extractor).
OUTPUT:   ExtractionResult (reuses md_links' shape for uniformity).
DEPENDS:  core/thinking-os/task_parser.py (existing Phase C parser).
NOTES:    Falls back gracefully when parse_task_file returns None
          (file is not a recognisable task) — emits just the task:file
          node with a parse_error entry. Dependency references survive
          TASK-19 vs TASK-195 ambiguity because we match on the
          zero-padded canonical form returned by task_parser.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path, PurePosixPath

from ..types import GraphEdge, GraphNode
from .md_links import (
    ExtractionResult,
    ParseError,
    _normalize_path,
    _promote_stubs,
    file_uid as doc_file_uid,
)

logger = logging.getLogger("graph_os.extractors.task_deps")

EXTRACTOR_ID = "task_deps@v1"

# Canonical task id: TASK-NNN (zero-padded to at least 3 digits, like
# `task_parser.extract_task_id_from_h1`).
_TASK_ID_RE = re.compile(r"TASK-(?P<num>\d+)")
_DOC_PATH_RE = re.compile(r"([A-Za-z0-9_./\-]+\.md)")


def task_uid(task_id: str) -> str:
    """Stable uid for a task node — normalised on the canonical form."""
    return f"task:file:{_canonical_task_id(task_id)}"


def _canonical_task_id(raw: str) -> str:
    match = _TASK_ID_RE.search(raw)
    if not match:
        return raw.strip()
    num = match.group("num")
    # task_parser uses zero-padded-to-3 — keep the same for edge equality.
    return f"TASK-{int(num):03d}"


# ---------------------------------------------------------------------------
# task_parser bridge
# ---------------------------------------------------------------------------


def _import_task_parser():
    try:
        import task_parser  # type: ignore
        return task_parser
    except ImportError:
        here = Path(__file__).resolve()
        thinking_os = here.parent.parent.parent / "thinking-os"
        if thinking_os.exists() and str(thinking_os) not in sys.path:
            sys.path.insert(0, str(thinking_os))
        import task_parser  # type: ignore
        return task_parser


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a task file → task node + dependency / ssot / read_first edges.

    PURPOSE:      Single pure entry point for the orchestrator.
    INPUT:        task file path + raw markdown content.
    OUTPUT:       ExtractionResult with one task:file node, dependency
                  edges, and references_doc edges.
    DEPENDENCIES: task_parser.parse_task_file.
    NOTES:        When parse_task_file returns None (the file does not
                  look like a task — missing `# TASK-NNN:` heading) we
                  still emit the task:file node in `unknown` state so
                  upstream dashboards can count it and operators can
                  see the discrepancy.
    """
    result = ExtractionResult()
    try:
        parser = _import_task_parser()
        parsed = parser.parse_task_file(content)
        normalised_path = _normalize_path(path)

        if parsed is None:
            # Not a task file — emit a minimal node so cross-references
            # still resolve.
            result.nodes.append(
                GraphNode(
                    uid=f"task:file:unknown:{normalised_path}",
                    kind="task:file",
                    label=PurePosixPath(normalised_path).name,
                    file_path=normalised_path,
                    lang="md",
                    metadata={"parse_error": "not_a_task", "extractor": EXTRACTOR_ID},
                )
            )
            result.parse_errors.append(
                ParseError(kind="not_a_task", detail=normalised_path)
            )
            return result

        task_node = GraphNode(
            uid=task_uid(parsed.task_id),
            kind="task:file",
            label=parsed.raw_title,
            file_path=normalised_path,
            lang="md",
            doc_blob=parsed.goal_text[:2000] if parsed.goal_text else None,
            content_hash=parsed.content_hash,
            metadata={
                "task_id": parsed.task_id,
                "domain": parsed.domain,
                "extractor": EXTRACTOR_ID,
            },
        )
        result.nodes.append(task_node)

        # Dependency edges — depends_on + blocks (inverse). Blocks is the
        # inverse view materialised so `_dependents` queries don't have
        # to scan every edge in the graph.
        for dep in parsed.dependencies:
            dep_uid = task_uid(dep)
            if dep_uid == task_node.uid:
                # Self-dependency — nonsensical, skip with a parse_error.
                result.parse_errors.append(
                    ParseError(kind="self_dependency", detail=parsed.task_id)
                )
                continue
            result.edges.append(
                GraphEdge(
                    source_uid=task_node.uid,
                    target_uid=dep_uid,
                    edge_type="depends_on",
                    extractor=EXTRACTOR_ID,
                    confidence=1.0,
                    source_span=f"{normalised_path}:dependencies",
                )
            )
            result.edges.append(
                GraphEdge(
                    source_uid=dep_uid,
                    target_uid=task_node.uid,
                    edge_type="blocks",
                    extractor=EXTRACTOR_ID,
                    confidence=1.0,
                    source_span=f"{normalised_path}:dependencies",
                )
            )

        # Doc references — Source of Truth + Read First sections hold
        # doc paths; emit `references_doc` edges so F1/F5 can jump
        # task → authoritative spec.
        for doc_ref in _extract_doc_paths(parsed.source_of_truth):
            result.edges.append(
                GraphEdge(
                    source_uid=task_node.uid,
                    target_uid=doc_file_uid(doc_ref),
                    edge_type="references_doc",
                    extractor=EXTRACTOR_ID,
                    confidence=0.95,
                    source_span=f"{normalised_path}:source_of_truth",
                )
            )
        for doc_ref in _extract_doc_paths(parsed.read_first):
            result.edges.append(
                GraphEdge(
                    source_uid=task_node.uid,
                    target_uid=doc_file_uid(doc_ref),
                    edge_type="references_doc",
                    extractor=EXTRACTOR_ID,
                    confidence=0.9,
                    source_span=f"{normalised_path}:read_first",
                )
            )

        _promote_stubs(result)
        return result

    except Exception as exc:  # noqa: BLE001
        logger.debug("task_deps.extract(%s) fatal: %s", path, exc)
        result.parse_errors.append(ParseError(kind="fatal", detail=str(exc)))
        return result


# ---------------------------------------------------------------------------
# produces_code — git-derived; out of the per-file write path.
# ---------------------------------------------------------------------------


def produces_code_edges(
    *,
    task_id: str,
    modified_files: list[str],
) -> list[GraphEdge]:
    """Emit `produces_code` edges for files a task touched.

    PURPOSE:      The orchestrator runs a git-log scan per task file to
                  collect the set of source files modified while the
                  task marker was active. This helper converts that
                  list to edges. Kept pure + synchronous so tests and
                  the background role both drive the same code path.
    INPUT:        canonical task id + list of repo-relative file paths.
    OUTPUT:       list of GraphEdges (one per unique file).
    NOTES:        Confidence 0.85 — git-log heuristic, not deterministic
                  (agents could commit outside the task window). The
                  orchestrator may downweight further when there is
                  noise.
    """
    canonical = _canonical_task_id(task_id)
    seen: set[str] = set()
    edges: list[GraphEdge] = []
    for raw in modified_files:
        path = _normalize_path(raw.strip())
        if not path or path in seen:
            continue
        seen.add(path)
        edges.append(
            GraphEdge(
                source_uid=task_uid(canonical),
                target_uid=_target_uid_for_file(path),
                edge_type="produces_code",
                extractor=EXTRACTOR_ID,
                confidence=0.85,
                source_span=f"git-log:{canonical}",
            )
        )
    return edges


def _target_uid_for_file(path: str) -> str:
    """Infer the canonical uid for a produced artifact path.

    Docs land on doc:file:..., code files get code:file:... — later
    slices (I.4+) reuse the same uid so `produces_code` edges connect
    to the real Python / TS nodes.
    """
    if path.endswith(".md"):
        return f"doc:file:{path}"
    return f"code:file:{path}"


# ---------------------------------------------------------------------------
# Doc path helpers
# ---------------------------------------------------------------------------


def _extract_doc_paths(bullets: list[str]) -> list[str]:
    """Pull `docs/...md` paths out of task-section bullets."""
    paths: list[str] = []
    seen: set[str] = set()
    for item in bullets:
        for match in _DOC_PATH_RE.finditer(item):
            candidate = _normalize_path(match.group(1))
            if candidate in seen:
                continue
            seen.add(candidate)
            paths.append(candidate)
    return paths


__all__ = [
    "EXTRACTOR_ID",
    "extract",
    "produces_code_edges",
    "task_uid",
]
