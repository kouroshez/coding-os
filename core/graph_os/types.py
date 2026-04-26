"""graph_os — typed records exchanged between extractors and backends.

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
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class NodeKind(str, Enum):
    """Canonical node kinds for the graph_os tree / spine (S3).

    PURPOSE:  Enumerate every canonical node kind so extractors, tools,
              and the SPA agree on the vocabulary. Values are the short
              forms emitted by post-S3 extractors (e.g. ``"file"``,
              ``"method"``); legacy colon-prefixed strings
              (``"code:file"``, ``"doc:heading"``, …) are accepted via
              :func:`normalize_kind` and :meth:`NodeKind.from_any` and
              mapped back to these canonical values.
    INPUT:    n/a.
    OUTPUT:   n/a (enum members).
    DEPENDS:  stdlib Enum.
    NOTES:    Inherits ``str`` so members compare equal to their string
              values (matches existing ``GraphNode.kind: str`` usage).
              ``import_`` has a trailing underscore because ``import`` is
              a Python keyword. The DB + dataclass fields keep
              ``kind: str`` to avoid a breaking change; normalization
              runs at the extractor / migration boundary.
    """

    FOLDER = "folder"
    FILE = "file"
    MODULE = "module"
    CLASS = "class"
    METHOD = "method"
    FUNCTION = "function"
    VARIABLE = "variable"
    INTERFACE = "interface"
    IMPORT_ = "import_"
    ROUTE = "route"
    TOOL = "tool"
    MCP_TOOL = "mcp_tool"
    EVENT = "event"
    TASK = "task"
    DOC_FILE = "doc_file"
    DOC_HEADING = "doc_heading"
    DOC_FRONTMATTER = "doc_frontmatter"
    DOC_EXTERNAL = "doc_external"
    RULE = "rule"
    SKILL = "skill"
    CONTRACT = "contract"
    COMMUNITY = "community"
    HOOK = "hook"
    IDENTIFIER = "identifier"
    UNKNOWN = "unknown"

    @classmethod
    def from_any(cls, value: object) -> "NodeKind":
        """Coerce a legacy / new string to a canonical ``NodeKind``.

        Raises ``ValueError`` for empty / unrecognised inputs. Accepts
        both legacy colon-prefixed strings (``"code:function"``,
        ``"doc:heading"``, ``"task:file"``, ``"cos:mcp_tool"``, …) and
        post-S3 short forms (``"function"``, ``"doc_heading"``).
        """
        return normalize_kind(value)


# Legacy colon-prefixed strings → canonical short form. Every value in
# the RHS is a valid NodeKind member. Extractors produce legacy forms
# today; migration v16 rewrites stored rows; ``normalize_kind`` bridges
# the read path.
_LEGACY_KIND_MAP: dict[str, str] = {
    # code:*
    "code:file": "file",
    "code:module": "module",
    "code:class": "class",
    "code:method": "method",
    "code:function": "function",
    "code:variable": "variable",
    "code:interface": "interface",
    "code:import": "import_",
    "code:external": "unknown",
    # doc:*
    "doc:file": "doc_file",
    "doc:heading": "doc_heading",
    "doc:frontmatter_key": "doc_frontmatter",
    "doc:external": "doc_external",
    # task:*
    "task:file": "task",
    # cos:*
    "cos:route": "route",
    "cos:mcp_tool": "mcp_tool",
    "cos:tool": "tool",
    "cos:event": "event",
    "cos:hook": "hook",
    "cos:skill": "skill",
    "cos:rule": "rule",
    "cos:contract": "contract",
    "cos:identifier": "identifier",
    "cos:community": "community",
}


def normalize_kind(value: object) -> NodeKind:
    """Map a stored/extracted kind string to a canonical ``NodeKind``.

    PURPOSE:      Single normalizer so the tool layer, migration v16,
                  and the SPA all agree on kinds regardless of whether
                  the producer emits legacy colon-prefixed strings
                  (pre-S3) or new short forms (post-S3).
    INPUT:        any object (commonly a string) — the raw ``kind``.
    OUTPUT:       a ``NodeKind`` enum member.
    DEPENDENCIES: ``_LEGACY_KIND_MAP``.
    NOTES:        Raises ``ValueError`` when the value is empty or does
                  not match a known legacy/canonical kind. Callers that
                  want a permissive read path should catch and fall back
                  to ``NodeKind.UNKNOWN`` themselves.
    """
    if value is None:
        raise ValueError("kind cannot be None")
    raw = str(value).strip()
    if not raw:
        raise ValueError("kind cannot be empty")
    lowered = raw.lower()
    # Direct enum value match (post-S3 emission).
    try:
        return NodeKind(lowered)
    except ValueError:
        pass
    # Legacy colon-prefixed forms.
    if lowered in _LEGACY_KIND_MAP:
        return NodeKind(_LEGACY_KIND_MAP[lowered])
    # Common legacy sub-prefix fallbacks — any ``code:foo``/``doc:foo``/
    # ``cos:foo`` string we don't explicitly map surfaces as UNKNOWN
    # rather than raising, so a single stray kind doesn't poison a bulk
    # reindex. Strict callers can still catch and inspect.
    if ":" in lowered:
        raise ValueError(f"unknown kind: {raw!r}")
    raise ValueError(f"unknown kind: {raw!r}")


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


# ---------------------------------------------------------------------------
# Provenance (TASK-122)
# ---------------------------------------------------------------------------
#
# `provenance` is a single-string label for "what kind of parser produced
# this edge".  It's not stored on disk — it's derived from the existing
# `extractor` field at read time, so the migration is purely additive
# and existing rows light up with the correct value the moment a caller
# asks for it.


PROVENANCE_VALUES: tuple[str, ...] = (
    "tree-sitter",
    "ast",
    "regex",
    "lsp",
    "text-search",
    "parser",
    "unknown",
)


_EXTRACTOR_PROVENANCE: dict[str, str] = {
    "code_python@v1":     "ast",
    "code_python_ts@v1":  "tree-sitter",
    "code_ts@v1":         "regex",
    "code_ts_ts@v1":      "tree-sitter",
    "code_go@v1":         "regex",
    "code_go_ts@v1":      "tree-sitter",
    "code_shell@v1":      "regex",
    "code_yaml@v1":       "parser",
    "contracts@v1":       "regex",
    "md_links@v1":        "parser",
    "task_deps@v1":       "parser",
    "lsp_overlay@v1":     "lsp",
}


def provenance_for(extractor: str | None) -> str:
    """Return the provenance label for an extractor ID.

    PURPOSE:    Single source of truth for "what kind of parser
                produced this edge". Used by the Hub UI Inspector,
                cos_graph_query for source filtering, and the A/B
                rollout switch in `cos graph-reindex`.
    INPUT:      ``extractor`` — the GraphEdge.extractor string; may be
                None if a legacy row has no extractor recorded.
    OUTPUT:     One of PROVENANCE_VALUES. Defaults to "unknown" so a
                stray new extractor doesn't crash the consumer.
    """
    if not extractor:
        return "unknown"
    return _EXTRACTOR_PROVENANCE.get(extractor, "unknown")


__all__ = [
    "GraphNode",
    "GraphEdge",
    "EvidenceSignal",
    "NodeKind",
    "normalize_kind",
    "PROVENANCE_VALUES",
    "provenance_for",
]
