"""Shared extractor primitives — the leaf every extractor depends on.

Imports nothing from its own package, so any extractor can depend on it
without risking the import cycle that a shared base would otherwise create.
Holds the result container, path normalisation, the folder→file `contains`
spine, and stub promotion for edge targets nobody owns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ..types import GraphEdge, GraphNode

EXTRACTOR_ID = "md_links@v1"


@dataclass(frozen=True)
class ParseError:
    """Non-fatal extractor warning (e.g. malformed frontmatter)."""

    kind: str
    detail: str
    line: int | None = None


@dataclass
class ExtractionResult:
    """Nodes, edges, parse_errors returned from extract()."""

    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    parse_errors: list[ParseError] = field(default_factory=list)


def _normalize_path(path: str) -> str:
    """Forward-slash, no trailing slash — stable across platforms."""
    return str(PurePosixPath(path.replace("\\", "/")))


def folder_uid(path: str) -> str:
    """Stable uid for a repo-rooted folder.

    Empty / ``.`` / ``/`` path collapse to the synthetic repo root uid.
    Matches the convention used by the backend's bulk_upsert — so
    parallel extractors emit the SAME uid for the same folder and the
    upsert de-duplicates.
    """
    normalised = _normalize_path(path)
    if normalised in ("", ".", "/"):
        return "folder:."
    return f"folder:{normalised}"


def emit_contains_spine(
    *,
    file_path: str,
    file_uid_: str,
    result: ExtractionResult,
    extractor_id: str,
) -> None:
    """Append folder nodes + Folder→Folder → Folder→File ``contains`` edges."""
    normalised = _normalize_path(file_path)
    if not normalised or normalised in (".", "/"):
        return

    # Walk up the directory chain → list of (uid, label, parent_uid).
    parts = [p for p in normalised.split("/") if p]
    if not parts:
        return
    # Drop the filename — we only want directory segments.
    directory_parts = parts[:-1]

    # Always emit the repo root folder (parent of every top-level dir).
    # uid stays `folder:.` for stability across rebuilds and idempotency;
    # the label is the PROJECT NAME (cwd directory name — extraction runs
    # from the project root by convention) so the spine anchors on
    # something a human recognises ("coding-os"), not the technical
    # "repo-root" placeholder (TASK-406). uid is the contract, label is
    # presentation.
    try:
        project_label = Path.cwd().name or "repo-root"
    except OSError:
        project_label = "repo-root"
    root_uid = folder_uid(".")
    root_node = GraphNode(
        uid=root_uid,
        kind="folder",
        label=project_label,
        file_path=None,
        metadata={"extractor": extractor_id, "repo_root": True},
    )
    result.nodes.append(root_node)

    # Emit one folder node per directory segment, and a contains edge
    # from its parent. Parent of first segment is the repo root.
    previous_uid = root_uid
    accumulated: list[str] = []
    for segment in directory_parts:
        accumulated.append(segment)
        this_path = "/".join(accumulated)
        this_uid = folder_uid(this_path)
        result.nodes.append(
            GraphNode(
                uid=this_uid,
                kind="folder",
                label=segment,
                file_path=this_path,
                metadata={"extractor": extractor_id},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=previous_uid,
                target_uid=this_uid,
                edge_type="contains",
                extractor=extractor_id,
                confidence=1.0,
            )
        )
        previous_uid = this_uid

    # Finally the deepest folder → file edge.
    result.edges.append(
        GraphEdge(
            source_uid=previous_uid,
            target_uid=file_uid_,
            edge_type="contains",
            extractor=extractor_id,
            confidence=1.0,
        )
    )


def _promote_stubs(result: ExtractionResult) -> None:
    """Emit a minimal stub node for every edge target we do not own."""
    known = {n.uid for n in result.nodes}
    seen_extra: set[str] = set()
    for edge in result.edges:
        for uid in (edge.source_uid, edge.target_uid):
            if uid in known or uid in seen_extra:
                continue
            seen_extra.add(uid)
            result.nodes.append(_stub_for_uid(uid))


def _stub_for_uid(uid: str) -> GraphNode:
    if uid.startswith("folder:"):
        path = uid[len("folder:") :]
        label = PurePosixPath(path).name if path not in ("", ".") else "."
        return GraphNode(
            uid=uid,
            kind="folder",
            label=label or path or ".",
            file_path=path if path not in ("", ".") else None,
            metadata={"stub": True, "extractor": EXTRACTOR_ID},
        )
    if uid.startswith("doc:file:"):
        rest = uid[len("doc:file:") :]
        path, _, anchor = rest.partition("#")
        label = PurePosixPath(path).name if path else anchor
        return GraphNode(
            uid=uid,
            kind="doc:file",
            label=label or uid,
            file_path=path or None,
            lang="md",
            metadata={"stub": True, "extractor": EXTRACTOR_ID},
        )
    if uid.startswith("doc:heading:"):
        return GraphNode(
            uid=uid,
            kind="doc:heading",
            label=uid.split("#", 1)[-1] or uid,
            lang="md",
            metadata={"stub": True, "extractor": EXTRACTOR_ID},
        )
    if uid.startswith("doc:external:"):
        return GraphNode(
            uid=uid,
            kind="doc:external",
            label=uid[len("doc:external:") :],
            metadata={"stub": True, "extractor": EXTRACTOR_ID},
        )
    # Infer kind from any standard `<kind>:<sub>:...` prefix so cross-
    # extractor edge targets (code symbols, mcp tools, routes, tasks)
    # keep the correct kind when synthesised as stubs. Falls through to
    # doc:external only when the prefix is genuinely unknown.
    head, sep, rest = uid.partition(":")
    if sep and head in {"code", "doc", "cos", "task"}:
        sub, sep2, tail = rest.partition(":")
        if sep2:
            kind = f"{head}:{sub}"
            label = tail.split("::", 1)[-1] or tail or uid
            return GraphNode(
                uid=uid,
                kind=kind,
                label=label,
                metadata={"stub": True, "extractor": EXTRACTOR_ID},
            )
    return GraphNode(
        uid=uid,
        kind="doc:external",
        label=uid,
        metadata={"stub": True, "extractor": EXTRACTOR_ID},
    )
