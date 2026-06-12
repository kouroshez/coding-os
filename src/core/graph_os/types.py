"""graph_os — typed records exchanged between extractors and backends.

DEPENDS:  stdlib only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any


class NodeKind(str, Enum):
    """Canonical node kinds for the graph_os tree / spine (S3).

    DEPENDS:  stdlib Enum.
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
    def from_any(cls, value: object) -> NodeKind:
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
    # Go package-grouping node (one per `package <name>`) — a module-tier
    # namespace, mapped to `module` so it gets a legend slot and
    # `normalize_kind` never raises on the stored row (TASK-409).
    "code:package": "module",
    # `code:external:*` UIDs are unresolved cross-module references —
    # builtin types, dynamic attribute accesses, third-party imports
    # the extractor couldn't pin to a real definition. They're not
    # "unknown" (which the canvas treats as a true mystery), they're
    # bonafide identifiers without resolution. Mapping to `identifier`
    # gets them their own legend slot + colour and lets the noise
    # filter on the export side hide them when needed.
    "code:external": "identifier",
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
    """Map a stored/extracted kind string to a canonical ``NodeKind``."""
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
    """A single node in the knowledge graph."""

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

    DEPENDS:  GraphEdge references these via EvidenceSignal rows keyed
              by edge_id (normalized, Section 5.3 of the plan).
    """

    signal_name: str
    weight: float
    note: str | None = None


@dataclass(frozen=True)
class GraphEdge:
    """A directed relation between two nodes.

    DEPENDS:  GraphNode (via uid references), EvidenceSignal.
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
            raise ValueError(f"edge confidence must lie in [0,1], got {self.confidence!r}")


# ---------------------------------------------------------------------------
# Provenance
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
    "code_python@v1": "ast",
    "code_python_ts@v1": "tree-sitter",
    "code_ts@v1": "regex",
    "code_ts_ts@v1": "tree-sitter",
    "code_go@v1": "regex",
    "code_go_ts@v1": "tree-sitter",
    "code_php@v1": "tree-sitter",
    "code_shell@v1": "regex",
    "code_yaml@v1": "parser",
    "contracts@v1": "regex",
    "md_links@v1": "parser",
    "task_deps@v1": "parser",
}


def provenance_for(extractor: str | None) -> str:
    """Return the provenance label for an extractor ID."""
    if not extractor:
        return "unknown"
    return _EXTRACTOR_PROVENANCE.get(extractor, "unknown")


__all__ = [
    "PROVENANCE_VALUES",
    "EvidenceSignal",
    "GraphEdge",
    "GraphNode",
    "NodeKind",
    "normalize_kind",
    "provenance_for",
]
