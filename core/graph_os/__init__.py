"""graph-os — the knowledge-graph subsystem of coding-os.

Sibling to thinking-os. Owns graph_nodes + graph_edges_v12 +
graph_evidence_v12 (shared SQLite DB, migration v12) and the optional
Kuzu store for graph-native workloads.

Public surface (I.0):
  GraphBackend   — Protocol that every backend implements (backend.py)
  GraphNode      — dataclass for a single node (types.py)
  GraphEdge      — dataclass for a single edge (types.py)
  EvidenceSignal — dataclass for a single contributing signal (types.py)
  SqliteBackend  — SQLite implementation (backends/sqlite_backend.py)
  KuzuBackend    — Kuzu implementation (backends/kuzu_backend.py)
  get_backend    — factory that reads rag-config.yaml or env (backend.py)

I.0 scope is storage + protocol + parity tests. Extractors (code,
docs, tasks, contracts), MCP tools, orchestrator, and the viewer ship
in later slices (see docs/phase-i-knowledge-graph-plan.md Section 19).
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
