"""Module-level architecture map: cos_graph_overview.

Private module of graph_os.tools.graph — import via the graph module,
never directly (the kernel imports this file at its bottom).
"""

from __future__ import annotations

import posixpath
from collections import Counter, defaultdict
from typing import Any

from ..backend import BackendUnavailable
from . import graph as _kernel
from ._graph_envelope import _clamp_int, _fail, _ok, _validate_positive_int

# Directory segments that are never part of the architecture: build output,
# dependency trees, per-agent worktrees, and test directories. Tests are
# excluded deliberately — they mirror the source tree, so leaving them in
# makes a third of a "what shape is this repo" map a duplicate of the rest.
_EXCLUDED_SEGMENTS = (
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "claude/worktrees",
    "build/",
    "dist/",
    "tests/",
    "/test_",
)

# Edge types worth drawing between modules. `contains` is excluded on purpose:
# it is the file->symbol spine, so every module would point at itself.
_OVERVIEW_EDGE_TYPES = ("imports", "calls", "extends", "implements", "references")

_NODE_SCAN_CAP = 200_000
_EDGE_SCAN_CAP = 200_000


def _module_of(file_path: str) -> str | None:
    if not file_path:
        return None
    normalised = file_path.replace("\\", "/")
    if any(seg in normalised for seg in _EXCLUDED_SEGMENTS):
        return None
    return posixpath.dirname(normalised) or "."


def _language_of(node: Any) -> str | None:
    lang = getattr(node, "lang", None) or getattr(node, "language", None)
    if lang:
        return str(lang)
    path = getattr(node, "file_path", "") or ""
    suffix = posixpath.splitext(path)[1].lstrip(".")
    return suffix or None


def cos_graph_overview(
    *,
    max_modules: int = 40,
    min_edge_weight: int = 1,
    backend: str | None = None,
) -> dict[str, Any]:
    """Aggregate files into module nodes with weighted cross-module edges (architecture map)."""
    invalid = _validate_positive_int(max_modules, "max_modules") or _validate_positive_int(
        min_edge_weight, "min_edge_weight"
    )
    if invalid is not None:
        return invalid
    max_modules, _ = _clamp_int(max_modules, min_v=1, max_v=100)

    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    nodes = be.sample_nodes(None, _NODE_SCAN_CAP)
    module_of_uid: dict[str, str] = {}
    members: Counter[str] = Counter()
    languages: dict[str, set[str]] = defaultdict(set)
    samples: dict[str, list[str]] = defaultdict(list)

    for node in nodes:
        module = _module_of(getattr(node, "file_path", "") or "")
        if module is None:
            continue
        uid = getattr(node, "uid", None)
        if not uid:
            continue
        module_of_uid[uid] = module
        members[module] += 1
        lang = _language_of(node)
        if lang:
            languages[module].add(lang)
        path = getattr(node, "file_path", "")
        if path and path not in samples[module] and len(samples[module]) < 5:
            samples[module].append(path)

    # Aggregate every cross-module edge BEFORE choosing which modules to keep.
    # Scan each edge type separately so a cap hit is attributable, and report
    # it: `calls` alone sat within 2% of a 50k cap on this repo, and
    # list_edges applies LIMIT after ordering by confidence, so an unflagged
    # overflow silently drops the weakest edges and returns a map that is
    # quietly wrong.
    all_weights: Counter[tuple[str, str, str]] = Counter()
    truncated_types: list[str] = []
    for edge_type in _OVERVIEW_EDGE_TYPES:
        try:
            total = be.count_edges(edge_type)
        except Exception:
            total = 0
        if total > _EDGE_SCAN_CAP:
            truncated_types.append(edge_type)
        for edge in be.list_edges(edge_types=[edge_type], limit=_EDGE_SCAN_CAP):
            src = module_of_uid.get(edge.source_uid)
            tgt = module_of_uid.get(edge.target_uid)
            if src is None or tgt is None or src == tgt:
                continue
            all_weights[(src, tgt, edge.edge_type)] += 1

    # Rank by connectivity, falling back to headcount only to break ties and
    # to fill the list on a graph with no edges yet. Ranking by member count
    # alone put docs/tasks first with 22,982 members and zero edges, and left
    # 80 of the top 100 modules unconnected — a directory listing, not a map.
    degree: Counter[str] = Counter()
    for (src, tgt, _), weight in all_weights.items():
        degree[src] += weight
        degree[tgt] += weight
    kept = sorted(
        members,
        key=lambda m: (-degree.get(m, 0), -members[m], m),
    )[:max_modules]
    kept_set = set(kept)

    weights: Counter[tuple[str, str, str]] = Counter(
        {
            key: weight
            for key, weight in all_weights.items()
            if key[0] in kept_set and key[1] in kept_set
        }
    )

    out_nodes = [
        {
            "uid": f"module:{module}",
            "label": module,
            "kind": "module",
            "metadata": {
                "member_count": members[module],
                "languages": sorted(languages[module]),
                "sample_files": samples[module],
                "synthetic": True,
            },
        }
        for module in kept
    ]
    out_edges = [
        {
            "source_uid": f"module:{src}",
            "target_uid": f"module:{tgt}",
            "edge_type": edge_type,
            "weight": weight,
        }
        for (src, tgt, edge_type), weight in sorted(weights.items(), key=lambda kv: -kv[1])
        if weight >= min_edge_weight
    ]

    return _ok(
        {
            "nodes": out_nodes,
            "edges": out_edges,
            "meta": {
                "layer": "graph",
                "backend": getattr(be, "backend_id", "unknown"),
                "module_count": len(out_nodes),
                "edge_count": len(out_edges),
            },
        },
        meta={
            "source": "graph_os.overview",
            "result_truncated": bool(truncated_types),
            "truncated_edge_types": truncated_types,
        },
    )
