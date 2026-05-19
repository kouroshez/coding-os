"""graph_os — the knowledge-graph subsystem of coding-os.

Sibling to thinking_os. Owns graph_nodes + graph_edges_v12 +
graph_evidence_v12 (shared SQLite DB, migration v12).

Public surface:
  GraphBackend   — Protocol that every backend implements (backend.py)
  GraphNode      — dataclass for a single node (types.py)
  GraphEdge      — dataclass for a single edge (types.py)
  EvidenceSignal — dataclass for a single contributing signal (types.py)
  SqliteBackend  — SQLite implementation (backends/sqlite_backend.py)
  get_backend    — factory that reads rag-config.yaml or env (backend.py)

Kuzu backend was retired 2026-05-18 — see backends/__init__.py.
"""

from __future__ import annotations

from .types import EvidenceSignal, GraphEdge, GraphNode
from .backend import GraphBackend, BackendUnavailable, get_backend

__all__ = [
    "EvidenceSignal",
    "GraphEdge",
    "GraphNode",
    "GraphBackend",
    "BackendUnavailable",
    "get_backend",
]
