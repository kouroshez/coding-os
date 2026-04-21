"""graph-os — typed records exchanged between extractors and backends.

PURPOSE:  Single source of truth for what a node / edge / evidence
          signal looks like, independent of the storage backend. Every
          extractor (I.2-I.7) produces these; every backend accepts
          them. Matches the schema defined in
          docs/phase-i-knowledge-graph-plan.md Section 5.
INPUT:    n/a (pure value types).
OUTPUT:   n/a.
DEPENDS:  stdlib only.
NOTES:    Frozen dataclasses so nodes/edges can be used as dict keys
          and in sets. uid is the stable identity (never the integer
          primary key), so migrations and re-indexes do not invalidate
          downstream references.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class GraphNode:
    """A single node in the knowledge graph.

    PURPOSE:  Represent one indexable entity (code symbol, doc file,
              doc heading, task, hook, rule, MCP tool, scaffold file)
              in a backend-agnostic shape.
    INPUT:    see field list — uid and kind are mandatory.
    OUTPUT:   see field list.
    NOTES:    uid is the stable identity. Format guidelines:
                code:method:path::Class.method
                doc:heading:path#slug
                task:file:docs/tasks/TASK-042-slug.md
                cos:skill:name
              kind uses the category:subkind form described in Section
              5.1 of the plan.
    """

    uid: str
    kind: str
    label: str
    file_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    signature: str | None = None
    lang: str | None = None
    doc_blob: str | None = None
    ast_hash: str | None = None
    content_hash: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # B11: wrap metadata in a read-only view so ``frozen=True`` isn't
        # silently undermined by callers mutating the backing dict. The
        # mapping view is read-only; equality/containment still work
        # exactly like a dict. Accept pre-wrapped values idempotently.
        md = self.metadata
        if isinstance(md, MappingProxyType):
            return
        backing: dict[str, Any] = dict(md) if md else {}
        object.__setattr__(self, "metadata", MappingProxyType(backing))


@dataclass(frozen=True)
class EvidenceSignal:
    """One signal that contributed to an edge's confidence.

    PURPOSE:  Decompose each edge's confidence into human-auditable
              reasons (same_scope, type_binding, lsp_overlay, ...).
    INPUT:    see field list.
    OUTPUT:   see field list.
    DEPENDS:  GraphEdge references these via EvidenceSignal rows keyed
              by edge_id (normalized, Section 5.3 of the plan).
    NOTES:    weight is the contribution this signal made (clamped to
              [0,1] at edge level; signals themselves can be any
              non-negative real before clamping).
    """

    signal_name: str
    weight: float
    note: str | None = None


@dataclass(frozen=True)
class GraphEdge:
    """A directed relation between two nodes.

    PURPOSE:  Encode "source node depends on / refers to / contains
              target node" semantics in a backend-agnostic shape.
    INPUT:    source_uid + target_uid + edge_type + extractor are
              required. evidence is a list of EvidenceSignal rows.
    OUTPUT:   see field list.
    DEPENDS:  GraphNode (via uid references), EvidenceSignal.
    NOTES:    confidence must live in [0,1]. The (source_uid,
              target_uid, edge_type, extractor) tuple is the unique
              identity (matches the UNIQUE constraint in migration v12).
              source_span is a file:line-range citation used by the
              viewer and by cos_graph_context for "where did this
              come from" traceability.
    """

    source_uid: str
    target_uid: str
    edge_type: str
    extractor: str
    confidence: float = 1.0
    source_span: str | None = None
    evidence: tuple[EvidenceSignal, ...] = ()

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"edge confidence must lie in [0,1], got {self.confidence!r}"
            )


__all__ = ["GraphNode", "GraphEdge", "EvidenceSignal"]
