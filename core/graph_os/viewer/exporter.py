"""graph_os viewer exporter (I.10).

DEPENDS:  stdlib + template.py + backend.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..backend import GraphBackend
from ..types import GraphEdge, GraphNode
from .template import render


@dataclass
class ViewerExporter:
    backend: GraphBackend
    title: str = "graph_os"
    max_nodes: int = 500
    max_edges: int = 2000
    bundled: bool = False

    def collect(
        self,
        *,
        root_uid: str | None = None,
        edge_types: Sequence[str] | None = None,
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        if root_uid is not None:
            # Walk up to max_nodes via BFS.
            from ..tools.graph import _walk_bfs  # local import to avoid cycle

            nodes, edges = _walk_bfs(
                self.backend,
                root_uid=root_uid,
                direction="both",
                max_hops=3,
                confidence_min=0.0,
                edge_types=edge_types,
                visit_limit=self.max_nodes,
            )
            return nodes, edges[: self.max_edges]
        edges = self.backend.list_edges(
            edge_types=edge_types, limit=self.max_edges
        )
        uids: set[str] = set()
        for e in edges:
            uids.add(e.source_uid)
            uids.add(e.target_uid)
        nodes = [n for n in (self.backend.get_node(u) for u in uids) if n is not None]
        return nodes[: self.max_nodes], edges

    def export(
        self,
        path: str | Path,
        *,
        root_uid: str | None = None,
        edge_types: Sequence[str] | None = None,
    ) -> Path:
        nodes, edges = self.collect(root_uid=root_uid, edge_types=edge_types)
        nonce = secrets.token_urlsafe(16)
        html_out = render(
            nodes,
            edges,
            title=self.title,
            nonce=nonce,
            bundled=self.bundled,
        )
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_out, encoding="utf-8")
        return out_path


def build_view(
    backend: GraphBackend,
    out_path: str | Path,
    *,
    title: str = "graph_os",
    root_uid: str | None = None,
    edge_types: Sequence[str] | None = None,
    bundled: bool = False,
) -> Path:
    exporter = ViewerExporter(
        backend=backend, title=title, bundled=bundled,
    )
    return exporter.export(out_path, root_uid=root_uid, edge_types=edge_types)


__all__ = ["ViewerExporter", "build_view"]
