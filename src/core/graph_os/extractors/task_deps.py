"""graph_os — task dependency extractor (I.3).

DEPENDS:  core/thinking_os/task_parser.py (existing Phase C parser).
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
    emit_contains_spine,
    file_uid as doc_file_uid,
)

logger = logging.getLogger("graph_os.extractors.task_deps")

EXTRACTOR_ID = "task_deps@v1"

# Canonical task id: TASK-NNN (zero-padded to at least 3 digits, like
# `task_parser.extract_task_id_from_h1`).
_TASK_ID_RE = re.compile(r"TASK-(?P<num>\d+)")
_DOC_PATH_RE = re.compile(r"([A-Za-z0-9_./\-]+\.md)")
_SCOPE_PATH_RE = re.compile(
    r"([A-Za-z0-9_./\-]+\.(?:py|ts|tsx|js|jsx|sh|yaml|yml|go|rs|java|md|json|toml))"
)


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
        thinking_os = here.parent.parent.parent / "thinking_os"
        if thinking_os.exists() and str(thinking_os) not in sys.path:
            sys.path.insert(0, str(thinking_os))
        import task_parser  # type: ignore

        return task_parser


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a task file → task node + dependency / ssot / read_first edges."""
    result = ExtractionResult()
    try:
        parser = _import_task_parser()
        parsed = parser.parse_task_file(content)
        normalised_path = _normalize_path(path)

        if parsed is None:
            # Not a task file — emit a minimal node so cross-references
            # still resolve.
            unknown_uid = f"task:file:unknown:{normalised_path}"
            result.nodes.append(
                GraphNode(
                    uid=unknown_uid,
                    kind="task:file",
                    label=PurePosixPath(normalised_path).name,
                    file_path=normalised_path,
                    lang="md",
                    metadata={"parse_error": "not_a_task", "extractor": EXTRACTOR_ID},
                )
            )
            result.parse_errors.append(ParseError(kind="not_a_task", detail=normalised_path))
            # S3: spine still attaches so unknown task files show up
            # under their folder in the tree-view.
            emit_contains_spine(
                file_path=path,
                file_uid_=unknown_uid,
                result=result,
                extractor_id=EXTRACTOR_ID,
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
        # doc paths; emit `references_doc` edges so Researcher/Implementer can jump
        # task → authoritative spec.
        for doc_ref in _extract_doc_paths(parsed.source_of_truth, normalised_path):
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
        for doc_ref in _extract_doc_paths(parsed.read_first, normalised_path):
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

        for scope_path in _extract_scope_paths(parsed.scope_in):
            kind_for_target = "produces_doc" if scope_path.endswith(".md") else "produces_code"
            result.edges.append(
                GraphEdge(
                    source_uid=task_node.uid,
                    target_uid=_target_uid_for_file(scope_path),
                    edge_type=kind_for_target,
                    extractor=EXTRACTOR_ID,
                    confidence=0.9,
                    source_span=f"{normalised_path}:scope_in",
                )
            )

        # S3: Folder→...→File spine anchored at the task uid so tree-
        # view can render tasks under their folder parent.
        emit_contains_spine(
            file_path=path,
            file_uid_=task_node.uid,
            result=result,
            extractor_id=EXTRACTOR_ID,
        )

        _promote_stubs(result)
        return result

    except Exception as exc:
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
    """Emit `produces_code` edges for files a task touched."""
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


def _resolve_doc_ref(origin_path: str, ref: str) -> str | None:
    """Resolve a doc ref (possibly `../`-relative) against the task file
    dir to a clean repo-rooted path.

    Returns None when the ref is malformed (escapes repo root, or holds a
    backtick / whitespace) so the caller can drop it instead of minting a
    `doc:file:../…` stub that orphans on every reindex (R4 X7 residual).
    """
    ref = ref.strip().strip("`").strip()
    if not ref or "`" in ref or any(c.isspace() for c in ref):
        return None
    if "../" not in ref and "./" not in ref:
        return _normalize_path(ref)
    from posixpath import dirname

    origin_dir = dirname(_normalize_path(origin_path))
    parts: list[str] = []
    escaped = False
    for part in f"{origin_dir}/{ref}".split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            else:
                escaped = True  # ref points above repo root → malformed
            continue
        parts.append(part)
    if escaped:
        return None
    return "/".join(parts)


def _extract_doc_paths(bullets: list[str], origin_path: str = "") -> list[str]:
    """Pull `docs/...md` paths out of task-section bullets."""
    paths: list[str] = []
    seen: set[str] = set()
    for item in bullets:
        for match in _DOC_PATH_RE.finditer(item):
            candidate = _resolve_doc_ref(origin_path, match.group(1))
            if candidate is None or candidate in seen:
                continue
            seen.add(candidate)
            paths.append(candidate)
    return paths


def _extract_scope_paths(bullets: list[str]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for item in bullets:
        for match in _SCOPE_PATH_RE.finditer(item):
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
