"""graph_os — Go uid grammar, tree-sitter node primitives and type-edge emitter.

Leaf module: owns the uid shapes, the receiver/test-name normalisers, the
node-text accessors every walker shares, and the one function that turns a Go
type name into a resolved or stubbed edge. Imports no walker sibling.
"""

from __future__ import annotations

from typing import Any

from ..types import EvidenceSignal, GraphEdge
from .md_links import ExtractionResult, _normalize_path

# Bound by assignment rather than `import ... as`, so importers of this leaf get
# an explicitly exported name instead of an implicit re-export.
try:
    from .. import tree_sitter_overlay

    _ts_overlay = tree_sitter_overlay
    _TS_AVAILABLE = _ts_overlay.is_available()
except ImportError:
    _ts_overlay = None  # type: ignore[assignment]
    _TS_AVAILABLE = False


EXTRACTOR_ID = "code_go@v2"


def file_uid(path: str) -> str:
    return f"code:file:{_normalize_path(path)}"


def module_uid(path: str) -> str:
    return f"code:module:{_normalize_path(path)}"


def func_uid(path: str, name: str) -> str:
    return f"code:function:{_normalize_path(path)}::{name}"


def method_uid(path: str, recv_type: str, name: str) -> str:
    return f"code:method:{_normalize_path(path)}::{recv_type}.{name}"


def class_uid(path: str, name: str) -> str:
    return f"code:class:{_normalize_path(path)}::{name}"


def variable_uid(path: str, name: str) -> str:
    return f"code:variable:{_normalize_path(path)}::{name}"


def package_uid(name: str) -> str:
    return f"code:package:go:{name}"


def import_uid(target_pkg: str) -> str:
    return f"code:external:{target_pkg}"


def _parse_receiver(recv: str) -> str:
    """Extract canonical type from a Go method receiver.

    Examples:
        ``s *Server``       → ``Server``
        ``r Reader``        → ``Reader``
        ``*Server``         → ``Server``
        ``s *T[int]``       → ``T``     (strip type parameters)
        ``c *Container[K, V]`` → ``Container``
    """
    if not recv:
        return ""
    raw = recv.strip()
    # Drop the type-parameter list first — `[K, V]` contains a space that
    # would otherwise break the whitespace split and leave a "V]" remnant.
    if "[" in raw:
        raw = raw[: raw.index("[")]
    parts = raw.split()
    return (parts[-1] if parts else raw).lstrip("*")


_TEST_KIND_MAP = {
    "Test": "test",
    "Benchmark": "benchmark",
    "Example": "example",
    "Fuzz": "fuzz",
}


def _classify_test_func(name: str, file_path: str) -> str | None:
    """Return one of {test, benchmark, example, fuzz, test_main} or None."""
    if not file_path.endswith("_test.go"):
        return None
    if name == "TestMain":
        return "test_main"
    for prefix, kind in _TEST_KIND_MAP.items():
        if name.startswith(prefix) and (
            len(name) == len(prefix) or name[len(prefix)].isupper() or name[len(prefix)] == "_"
        ):
            return kind
    return None


def _node_text(node: Any, content_bytes: bytes) -> str:
    if _ts_overlay is None:
        return ""
    return _ts_overlay.node_text(node, content_bytes)


def _find_child(node: Any, ntype: str) -> Any | None:
    for child in node.children:
        if child.type == ntype:
            return child
    return None


def _find_field(node: Any, field_name: str) -> Any | None:
    try:
        return node.child_by_field_name(field_name)
    except Exception:
        return None


_GO_BUILTIN_TYPES = {
    "bool",
    "byte",
    "complex64",
    "complex128",
    "error",
    "float32",
    "float64",
    "int",
    "int8",
    "int16",
    "int32",
    "int64",
    "rune",
    "string",
    "uint",
    "uint8",
    "uint16",
    "uint32",
    "uint64",
    "uintptr",
    "any",
    "comparable",
    "map",
    "chan",
    "interface",
    "struct",
    "func",
}


def _is_generic_type_param(label: str) -> bool:
    """A single capital letter (T, K, V) is most likely a generic param, not a type."""
    return len(label) == 1 and label.isupper()


def _walk_type_text(node: Any, content_bytes: bytes) -> str:
    """Return the surface text of a type node (stripped of pointer/slice markers)."""
    return _node_text(node, content_bytes).strip()


def _guess_type_kind(type_node: Any) -> str:
    if type_node is None:
        return "type"
    return {
        "struct_type": "struct",
        "interface_type": "interface",
        "function_type": "function_type",
        "channel_type": "channel",
        "map_type": "map",
        "slice_type": "slice",
        "array_type": "array",
        "pointer_type": "pointer",
    }.get(type_node.type, "type")


def _emit_type_relation(
    *,
    source_uid: str,
    target_label: str,
    edge_type: str,
    path: str,
    extractor_id: str,
    result: ExtractionResult,
    confidence: float = 0.8,
    evidence_signal: str | None = None,
) -> None:
    target_label = target_label.strip().lstrip("*").lstrip("&")
    if not target_label or target_label in _GO_BUILTIN_TYPES:
        return
    bare = target_label.split("[", 1)[0]
    bare = bare.lstrip("*").lstrip("[]").strip()
    if not bare or bare in _GO_BUILTIN_TYPES or _is_generic_type_param(bare):
        return
    # Skip slice/array/map/chan/func/interface{}/struct{} type expressions.
    if bare.startswith(("[", "(", "{", "<-")) or bare in {"chan", "<-chan"}:
        return
    if "." in bare:
        target = f"code:external:{bare}"
    else:
        target = class_uid(path, bare)
    evidence = (EvidenceSignal(evidence_signal, confidence),) if evidence_signal else ()
    result.edges.append(
        GraphEdge(
            source_uid=source_uid,
            target_uid=target,
            edge_type=edge_type,
            extractor=extractor_id,
            confidence=confidence,
            evidence=evidence,
        )
    )
