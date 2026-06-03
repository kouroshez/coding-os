"""graph_os — Go source file extractor (tree-sitter-go primary, regex fallback).

Coverage targets Python parity for the Go ecosystem:

  Node kinds emitted
    - code:file              one per .go file
    - code:module            one per file (Go package)
    - code:package           one per file (declared `package <name>`)
    - code:function          top-level funcs, including init() and TestXxx/etc.
    - code:method            receiver-bound funcs `func (r *T) M()`
    - code:class             struct + interface + alias + generic type defs
    - code:variable          var-block and const-block specs
    - code:external          imports + cross-module qualified calls

  Edge kinds emitted
    - contains               file → module → {func, method, type, var, const}
    - imports                module → code:external:<import-path>
    - inherits_from          struct → embedded-field, interface → embedded-iface
    - field_of_type          struct → external/local field type
    - has_param_type         func/method → external/local param type
    - returns_type           func/method → external/local return type
    - constructs             func/method → composite literal target type
    - is_decorated_by        file → code:external:build-tag:<expr>
    - calls                  module → code:external:<recv.method> (qualified)
    - handles_test           module → code:external:test:<func-name>

  Go specifics handled
    - generics: `func F[T any](…)` and `type Container[T any] struct{}` ;
      the receiver normaliser strips `[T]` so methods on `*C[T]` resolve.
    - pointer vs value receivers — both fold into the same method uid.
    - init() funcs flagged with metadata.init=true.
    - test funcs: TestXxx / BenchmarkXxx / ExampleXxx / FuzzXxx / TestMain
      annotated with metadata.test_kind so contracts can route them.
    - build tags: `//go:build linux,!cgo` becomes is_decorated_by edges.
    - blank, dot and aliased imports keep their alias in evidence.
    - embedded fields (anonymous struct fields) emit inherits_from edges.
    - embedded interfaces (method-less type_elem inside an interface)
      also emit inherits_from edges.
    - dotted call detection unchanged (regex pass).

Spec: docs/playbooks/polyglot-extractor-roadmap.md §4.3 (Epic C1).
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import PurePosixPath
from typing import Any

from ..types import EvidenceSignal, GraphEdge, GraphNode
from .md_links import (
    ExtractionResult,
    _normalize_path,
    _promote_stubs,
    emit_contains_spine,
)

try:
    from .. import tree_sitter_overlay as _ts_overlay

    _TS_AVAILABLE = _ts_overlay.is_available()
except ImportError:
    _ts_overlay = None  # type: ignore[assignment]
    _TS_AVAILABLE = False

logger = logging.getLogger("graph_os.extractors.code_go")
EXTRACTOR_ID = "code_go@v2"


# ---------------------------------------------------------------------------
# Regex fallback (only when tree-sitter unavailable). Conservative — matches
# the v1 capability set so v2 never loses information when grammar missing.
# ---------------------------------------------------------------------------

_PACKAGE_RE = re.compile(r"^\s*package\s+(?P<name>[A-Za-z_][\w]*)\s*$", re.MULTILINE)
_FUNC_RE = re.compile(
    r"""^\s*
        func\s+
        (?:\((?P<recv>[^)]*)\)\s+)?
        (?P<name>[A-Za-z_][\w]*)
        (?:\[[^\]]*\])?
        \s*\(
    """,
    re.VERBOSE | re.MULTILINE,
)
_TYPE_RE = re.compile(
    r"""^\s*
        type\s+
        (?P<name>[A-Za-z_][\w]*)
        (?:\[[^\]]*\])?
        \s+
        (?P<kind>struct|interface|=|[A-Za-z_])
    """,
    re.VERBOSE | re.MULTILINE,
)
_IMPORT_SINGLE_RE = re.compile(
    r'^\s*import\s+(?:(?P<alias>[A-Za-z_]\w*|\.|_)\s+)?"(?P<path>[^"]+)"\s*$',
    re.MULTILINE,
)
_IMPORT_BLOCK_RE = re.compile(r"^\s*import\s+\(\s*(?P<body>[^)]*?)\s*\)", re.MULTILINE | re.DOTALL)
_IMPORT_LINE_RE = re.compile(
    r'^\s*(?:(?P<alias>[A-Za-z_]\w*|\.|_)\s+)?"(?P<path>[^"]+)"', re.MULTILINE
)
_CALL_RE = re.compile(r"\b(?P<lhs>[A-Za-z_][\w]*)\.(?P<name>[A-Z][\w]*)\s*\(")
_BUILD_TAG_RE = re.compile(r"^//go:build\s+(?P<expr>[^\n]+)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# UID helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Receiver + name helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Tree-sitter walker
# ---------------------------------------------------------------------------


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


def _emit_func_node(
    name: str,
    line: int,
    *,
    path: str,
    normalised: str,
    receiver_type: str,
    is_init: bool,
    test_kind: str | None,
    has_generics: bool,
    module_uid_str: str,
    result: ExtractionResult,
    seen: set[str],
) -> str | None:
    if receiver_type:
        uid = method_uid(path, receiver_type, name)
        kind = "code:method"
        label = f"{receiver_type}.{name}"
    else:
        uid = func_uid(path, name)
        kind = "code:function"
        label = name
    if uid in seen:
        return None
    seen.add(uid)

    metadata: dict[str, Any] = {
        "extractor": EXTRACTOR_ID,
        "receiver": receiver_type or "",
    }
    if is_init:
        metadata["init"] = True
    if test_kind:
        metadata["test_kind"] = test_kind
    if has_generics:
        metadata["generic"] = True

    result.nodes.append(
        GraphNode(
            uid=uid,
            kind=kind,
            label=label,
            file_path=normalised,
            start_line=line,
            lang="go",
            metadata=metadata,
        )
    )
    result.edges.append(
        GraphEdge(
            source_uid=module_uid_str,
            target_uid=uid,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )
    return uid


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


def _walk_function_decl(
    node: Any,
    content_bytes: bytes,
    *,
    path: str,
    normalised: str,
    module_uid_str: str,
    result: ExtractionResult,
    seen: set[str],
) -> None:
    name_node = _find_field(node, "name")
    if name_node is None:
        return
    name = _node_text(name_node, content_bytes)
    type_params = _find_field(node, "type_parameters")
    params_node = _find_field(node, "parameters")
    result_node = _find_field(node, "result")
    line = node.start_point[0] + 1
    is_init = name == "init"
    test_kind = _classify_test_func(name, normalised)
    uid = _emit_func_node(
        name=name,
        line=line,
        path=path,
        normalised=normalised,
        receiver_type="",
        is_init=is_init,
        test_kind=test_kind,
        has_generics=type_params is not None,
        module_uid_str=module_uid_str,
        result=result,
        seen=seen,
    )
    if uid is None:
        return
    _emit_param_and_return_edges(
        uid,
        params_node,
        result_node,
        content_bytes,
        path=path,
        result=result,
    )
    if test_kind:
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_str,
                target_uid=f"code:external:test:{name}",
                edge_type="handles_test",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
                evidence=(EvidenceSignal(test_kind, 1.0),),
            )
        )


def _walk_method_decl(
    node: Any,
    content_bytes: bytes,
    *,
    path: str,
    normalised: str,
    module_uid_str: str,
    result: ExtractionResult,
    seen: set[str],
) -> None:
    receiver_node = _find_field(node, "receiver")
    name_node = _find_field(node, "name")
    if name_node is None:
        return
    name = _node_text(name_node, content_bytes)
    receiver_text = _node_text(receiver_node, content_bytes) if receiver_node else ""
    receiver_text = receiver_text.strip("()")
    receiver_type = _parse_receiver(receiver_text)
    params_node = _find_field(node, "parameters")
    result_node = _find_field(node, "result")
    line = node.start_point[0] + 1
    uid = _emit_func_node(
        name=name,
        line=line,
        path=path,
        normalised=normalised,
        receiver_type=receiver_type,
        is_init=False,
        test_kind=None,
        has_generics="[" in receiver_text,
        module_uid_str=module_uid_str,
        result=result,
        seen=seen,
    )
    if uid is None:
        return
    if receiver_type:
        result.edges.append(
            GraphEdge(
                source_uid=class_uid(path, receiver_type),
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=0.9,
                evidence=(EvidenceSignal("method_receiver", 0.9),),
            )
        )
    _emit_param_and_return_edges(
        uid,
        params_node,
        result_node,
        content_bytes,
        path=path,
        result=result,
    )


def _emit_param_and_return_edges(
    func_uid_str: str,
    params_node: Any,
    result_node: Any,
    content_bytes: bytes,
    *,
    path: str,
    result: ExtractionResult,
) -> None:
    if params_node is not None:
        for child in params_node.children:
            if child.type in ("parameter_declaration", "variadic_parameter_declaration"):
                type_field = _find_field(child, "type")
                if type_field is not None:
                    _emit_type_relation(
                        source_uid=func_uid_str,
                        target_label=_walk_type_text(type_field, content_bytes),
                        edge_type="has_param_type",
                        path=path,
                        extractor_id=EXTRACTOR_ID,
                        result=result,
                        confidence=0.85,
                        evidence_signal="go_param",
                    )
    if result_node is not None:
        if result_node.type == "parameter_list":
            for child in result_node.children:
                if child.type in ("parameter_declaration", "variadic_parameter_declaration"):
                    type_field = _find_field(child, "type")
                    if type_field is not None:
                        _emit_type_relation(
                            source_uid=func_uid_str,
                            target_label=_walk_type_text(type_field, content_bytes),
                            edge_type="returns_type",
                            path=path,
                            extractor_id=EXTRACTOR_ID,
                            result=result,
                            confidence=0.85,
                            evidence_signal="go_return",
                        )
        else:
            _emit_type_relation(
                source_uid=func_uid_str,
                target_label=_walk_type_text(result_node, content_bytes),
                edge_type="returns_type",
                path=path,
                extractor_id=EXTRACTOR_ID,
                result=result,
                confidence=0.85,
                evidence_signal="go_return",
            )


def _walk_type_decl(
    node: Any,
    content_bytes: bytes,
    *,
    path: str,
    normalised: str,
    module_uid_str: str,
    result: ExtractionResult,
    seen: set[str],
) -> None:
    for child in node.children:
        if child.type not in ("type_spec", "type_alias"):
            continue
        name_node = _find_field(child, "name")
        type_node = _find_field(child, "type")
        if name_node is None:
            continue
        name = _node_text(name_node, content_bytes)
        uid = class_uid(path, name)
        if uid in seen:
            continue
        seen.add(uid)
        type_params = _find_field(child, "type_parameters")
        line = child.start_point[0] + 1
        go_kind = "alias" if child.type == "type_alias" else _guess_type_kind(type_node)
        metadata: dict[str, Any] = {
            "extractor": EXTRACTOR_ID,
            "go_kind": go_kind,
        }
        if type_params is not None:
            metadata["generic"] = True
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:class",
                label=name,
                file_path=normalised,
                start_line=line,
                lang="go",
                metadata=metadata,
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_str,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )
        if type_node is not None:
            if type_node.type == "struct_type":
                _emit_struct_relations(uid, type_node, content_bytes, path=path, result=result)
            elif type_node.type == "interface_type":
                _emit_interface_relations(uid, type_node, content_bytes, path=path, result=result)
            elif child.type == "type_alias":
                # alias to another named type
                _emit_type_relation(
                    source_uid=uid,
                    target_label=_walk_type_text(type_node, content_bytes),
                    edge_type="inherits_from",
                    path=path,
                    extractor_id=EXTRACTOR_ID,
                    result=result,
                    confidence=0.95,
                    evidence_signal="go_alias",
                )


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


def _emit_struct_relations(
    type_uid: str,
    struct_node: Any,
    content_bytes: bytes,
    *,
    path: str,
    result: ExtractionResult,
) -> None:
    field_list = _find_child(struct_node, "field_declaration_list")
    if field_list is None:
        return
    for field in field_list.children:
        if field.type != "field_declaration":
            continue
        type_field = _find_field(field, "type")
        name_field = _find_field(field, "name")
        if type_field is None:
            continue
        if name_field is None:
            # Embedded field — type only, no name.
            _emit_type_relation(
                source_uid=type_uid,
                target_label=_walk_type_text(type_field, content_bytes),
                edge_type="inherits_from",
                path=path,
                extractor_id=EXTRACTOR_ID,
                result=result,
                confidence=0.95,
                evidence_signal="go_embedded_field",
            )
        else:
            _emit_type_relation(
                source_uid=type_uid,
                target_label=_walk_type_text(type_field, content_bytes),
                edge_type="field_of_type",
                path=path,
                extractor_id=EXTRACTOR_ID,
                result=result,
                confidence=0.85,
                evidence_signal="go_struct_field",
            )


def _emit_interface_relations(
    type_uid: str,
    iface_node: Any,
    content_bytes: bytes,
    *,
    path: str,
    result: ExtractionResult,
) -> None:
    for child in iface_node.children:
        # method_elem — method signature inside the interface.
        # type_elem  — embedded type or type constraint (Go 1.18+).
        if child.type == "type_elem":
            for grand in child.children:
                txt = _walk_type_text(grand, content_bytes)
                if not txt or txt in {"|", "~"}:
                    continue
                _emit_type_relation(
                    source_uid=type_uid,
                    target_label=txt,
                    edge_type="inherits_from",
                    path=path,
                    extractor_id=EXTRACTOR_ID,
                    result=result,
                    confidence=0.9,
                    evidence_signal="go_iface_embed",
                )


def _walk_imports(
    node: Any,
    content_bytes: bytes,
    *,
    module_uid_str: str,
    file_uid_str: str,
    result: ExtractionResult,
    seen_imports: set[str],
) -> None:
    for child in node.children:
        if child.type == "import_spec":
            _emit_import_spec(
                child, content_bytes, module_uid_str, file_uid_str, result, seen_imports
            )
        elif child.type == "import_spec_list":
            for sub in child.children:
                if sub.type == "import_spec":
                    _emit_import_spec(
                        sub, content_bytes, module_uid_str, file_uid_str, result, seen_imports
                    )


def _emit_import_spec(
    spec: Any,
    content_bytes: bytes,
    module_uid_str: str,
    file_uid_str: str,
    result: ExtractionResult,
    seen_imports: set[str],
) -> None:
    name_node = _find_field(spec, "name")
    path_node = _find_field(spec, "path")
    if path_node is None:
        return
    raw_path = _node_text(path_node, content_bytes).strip().strip('"')
    if not raw_path or raw_path in seen_imports:
        return
    seen_imports.add(raw_path)
    alias = _node_text(name_node, content_bytes) if name_node is not None else ""
    is_dot = alias == "."
    is_blank = alias == "_"
    target = import_uid(raw_path)
    metadata: dict[str, Any] = {
        "extractor": EXTRACTOR_ID,
        "external_kind": "go_import",
    }
    if alias and not is_dot and not is_blank:
        metadata["alias"] = alias
    if is_dot:
        metadata["dot_import"] = True
    if is_blank:
        metadata["blank_import"] = True
    result.nodes.append(
        GraphNode(
            uid=target,
            kind="code:external",
            label=raw_path,
            lang="go",
            metadata=metadata,
        )
    )
    result.edges.append(
        GraphEdge(
            source_uid=module_uid_str,
            target_uid=target,
            edge_type="imports",
            extractor=EXTRACTOR_ID,
            confidence=0.95,
            evidence=(
                EvidenceSignal(
                    "go_dot_import"
                    if is_dot
                    else "go_blank_import"
                    if is_blank
                    else "go_aliased_import"
                    if alias
                    else "go_import",
                    0.95,
                ),
            ),
        )
    )


def _walk_var_const(
    node: Any,
    content_bytes: bytes,
    *,
    path: str,
    normalised: str,
    module_uid_str: str,
    result: ExtractionResult,
    seen: set[str],
    is_const: bool,
) -> None:
    spec_kind = "const_spec" if is_const else "var_spec"
    for child in node.children:
        if child.type != spec_kind:
            continue
        line = child.start_point[0] + 1
        for grand in child.children:
            if grand.type == "identifier":
                name = _node_text(grand, content_bytes)
                if not name:
                    continue
                uid = variable_uid(path, name)
                if uid in seen:
                    continue
                seen.add(uid)
                result.nodes.append(
                    GraphNode(
                        uid=uid,
                        kind="code:variable",
                        label=name,
                        file_path=normalised,
                        start_line=line,
                        lang="go",
                        metadata={
                            "extractor": EXTRACTOR_ID,
                            "go_kind": "const" if is_const else "var",
                        },
                    )
                )
                result.edges.append(
                    GraphEdge(
                        source_uid=module_uid_str,
                        target_uid=uid,
                        edge_type="contains",
                        extractor=EXTRACTOR_ID,
                        confidence=1.0,
                    )
                )


def _walk_build_tags(
    content: str,
    *,
    file_uid_str: str,
    result: ExtractionResult,
) -> None:
    for match in _BUILD_TAG_RE.finditer(content):
        expr = match.group("expr").strip()
        if not expr:
            continue
        target = f"code:external:build-tag:{expr}"
        result.nodes.append(
            GraphNode(
                uid=target,
                kind="code:external",
                label=expr,
                lang="go",
                metadata={"extractor": EXTRACTOR_ID, "external_kind": "go_build_tag"},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=file_uid_str,
                target_uid=target,
                edge_type="is_decorated_by",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
                evidence=(EvidenceSignal("go_build_tag", 1.0),),
            )
        )


def _walk_calls_regex(
    content: str,
    *,
    module_uid_str: str,
    result: ExtractionResult,
) -> None:
    seen: set[str] = set()
    for match in _CALL_RE.finditer(content):
        lhs = match.group("lhs")
        name = match.group("name")
        target = f"code:external:{lhs}.{name}"
        if target in seen:
            continue
        seen.add(target)
        result.nodes.append(
            GraphNode(
                uid=target,
                kind="code:external",
                label=f"{lhs}.{name}",
                lang="go",
                metadata={"extractor": EXTRACTOR_ID, "external_kind": "go_call"},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_str,
                target_uid=target,
                edge_type="calls",
                extractor=EXTRACTOR_ID,
                confidence=0.5,
            )
        )


def _walk_composite_constructs(
    node: Any,
    content_bytes: bytes,
    *,
    path: str,
    module_uid_str: str,
    result: ExtractionResult,
) -> None:
    type_node = _find_field(node, "type")
    if type_node is None:
        return
    target_label = _walk_type_text(type_node, content_bytes)
    _emit_type_relation(
        source_uid=module_uid_str,
        target_label=target_label,
        edge_type="constructs",
        path=path,
        extractor_id=EXTRACTOR_ID,
        result=result,
        confidence=0.7,
        evidence_signal="go_composite_literal",
    )


# ---------------------------------------------------------------------------
# Top-level walker
# ---------------------------------------------------------------------------


def _walk_ts(
    root: Any,
    content_bytes: bytes,
    *,
    path: str,
    normalised: str,
    module_uid_str: str,
    file_uid_str: str,
    result: ExtractionResult,
) -> tuple[str, int]:
    """Walk a tree-sitter-go AST. Returns (package_name, error_count)."""
    seen_funcs: set[str] = set()
    seen_types: set[str] = set()
    seen_vars: set[str] = set()
    seen_imports: set[str] = set()
    pkg_name = ""
    err_count = 0

    stack = [root]
    while stack:
        node = stack.pop()
        ntype = node.type
        if ntype == "ERROR":
            err_count += 1
            stack.extend(reversed(list(node.children)))
            continue
        if ntype == "package_clause":
            for ident in node.children:
                if ident.type == "package_identifier":
                    pkg_name = _node_text(ident, content_bytes)
                    break
        elif ntype == "function_declaration":
            _walk_function_decl(
                node,
                content_bytes,
                path=path,
                normalised=normalised,
                module_uid_str=module_uid_str,
                result=result,
                seen=seen_funcs,
            )
        elif ntype == "method_declaration":
            _walk_method_decl(
                node,
                content_bytes,
                path=path,
                normalised=normalised,
                module_uid_str=module_uid_str,
                result=result,
                seen=seen_funcs,
            )
        elif ntype == "type_declaration":
            _walk_type_decl(
                node,
                content_bytes,
                path=path,
                normalised=normalised,
                module_uid_str=module_uid_str,
                result=result,
                seen=seen_types,
            )
        elif ntype == "import_declaration":
            _walk_imports(
                node,
                content_bytes,
                module_uid_str=module_uid_str,
                file_uid_str=file_uid_str,
                result=result,
                seen_imports=seen_imports,
            )
        elif ntype == "var_declaration":
            _walk_var_const(
                node,
                content_bytes,
                path=path,
                normalised=normalised,
                module_uid_str=module_uid_str,
                result=result,
                seen=seen_vars,
                is_const=False,
            )
        elif ntype == "const_declaration":
            _walk_var_const(
                node,
                content_bytes,
                path=path,
                normalised=normalised,
                module_uid_str=module_uid_str,
                result=result,
                seen=seen_vars,
                is_const=True,
            )
        elif ntype == "composite_literal":
            _walk_composite_constructs(
                node,
                content_bytes,
                path=path,
                module_uid_str=module_uid_str,
                result=result,
            )
        stack.extend(reversed(list(node.children)))
    return pkg_name, err_count


# ---------------------------------------------------------------------------
# Regex fallback walker
# ---------------------------------------------------------------------------


def _walk_regex(
    content: str,
    *,
    path: str,
    normalised: str,
    module_uid_str: str,
    file_uid_str: str,
    result: ExtractionResult,
) -> str:
    pkg_match = _PACKAGE_RE.search(content)
    pkg_name = pkg_match.group("name") if pkg_match else PurePosixPath(normalised).stem

    seen_funcs: set[str] = set()
    seen_types: set[str] = set()
    seen_imports: set[str] = set()

    for match in _FUNC_RE.finditer(content):
        name = match.group("name")
        recv = match.group("recv") or ""
        receiver_type = _parse_receiver(recv)
        line = content.count("\n", 0, match.start()) + 1
        _emit_func_node(
            name=name,
            line=line,
            path=path,
            normalised=normalised,
            receiver_type=receiver_type,
            is_init=(name == "init" and not receiver_type),
            test_kind=_classify_test_func(name, normalised),
            has_generics=False,
            module_uid_str=module_uid_str,
            result=result,
            seen=seen_funcs,
        )

    for match in _TYPE_RE.finditer(content):
        name = match.group("name")
        uid = class_uid(path, name)
        if uid in seen_types:
            continue
        seen_types.add(uid)
        line = content.count("\n", 0, match.start()) + 1
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:class",
                label=name,
                file_path=normalised,
                start_line=line,
                lang="go",
                metadata={"extractor": EXTRACTOR_ID, "go_kind": match.group("kind") or "type"},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_str,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )

    for match in _IMPORT_SINGLE_RE.finditer(content):
        _emit_regex_import(
            match.group("path"),
            match.group("alias") or "",
            module_uid_str,
            result,
            seen_imports,
        )
    for block in _IMPORT_BLOCK_RE.finditer(content):
        body = block.group("body") or ""
        for line_match in _IMPORT_LINE_RE.finditer(body):
            _emit_regex_import(
                line_match.group("path"),
                line_match.group("alias") or "",
                module_uid_str,
                result,
                seen_imports,
            )

    _walk_calls_regex(content, module_uid_str=module_uid_str, result=result)
    return pkg_name


def _emit_regex_import(
    raw_path: str,
    alias: str,
    module_uid_str: str,
    result: ExtractionResult,
    seen_imports: set[str],
) -> None:
    if not raw_path or raw_path in seen_imports:
        return
    seen_imports.add(raw_path)
    target = import_uid(raw_path)
    is_dot = alias == "."
    is_blank = alias == "_"
    metadata: dict[str, Any] = {
        "extractor": EXTRACTOR_ID,
        "external_kind": "go_import",
    }
    if alias and not is_dot and not is_blank:
        metadata["alias"] = alias
    if is_dot:
        metadata["dot_import"] = True
    if is_blank:
        metadata["blank_import"] = True
    result.nodes.append(
        GraphNode(
            uid=target,
            kind="code:external",
            label=raw_path,
            lang="go",
            metadata=metadata,
        )
    )
    result.edges.append(
        GraphEdge(
            source_uid=module_uid_str,
            target_uid=target,
            edge_type="imports",
            extractor=EXTRACTOR_ID,
            confidence=0.95,
        )
    )


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a Go source file → nodes + edges."""
    result = ExtractionResult()
    normalised = _normalize_path(path)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    file_uid_str = file_uid(path)
    module_uid_str = module_uid(path)

    # Cheap pkg_name probe via regex; tree-sitter overrides if it finds one.
    _pkg_match = _PACKAGE_RE.search(content)
    pkg_name = _pkg_match.group("name") if _pkg_match else ""
    used_ts = False
    if _TS_AVAILABLE and _ts_overlay is not None:
        parsed = _ts_overlay.parse("go", content)
        if parsed is not None:
            used_ts = True
            pkg_name, err_count = _walk_ts(
                parsed.root,
                content.encode("utf-8"),
                path=path,
                normalised=normalised,
                module_uid_str=module_uid_str,
                file_uid_str=file_uid_str,
                result=result,
            )
            if err_count:
                from .md_links import ParseError

                result.parse_errors.append(
                    ParseError(
                        kind="tree_sitter_error",
                        detail=f"tree-sitter recorded {err_count} ERROR node(s)",
                    )
                )

    if not used_ts:
        pkg_name = _walk_regex(
            content,
            path=path,
            normalised=normalised,
            module_uid_str=module_uid_str,
            file_uid_str=file_uid_str,
            result=result,
        )

    if not pkg_name:
        pkg_name = PurePosixPath(normalised).stem

    # File node created last with full metadata (GraphNode is frozen).
    file_node = GraphNode(
        uid=file_uid_str,
        kind="code:file",
        label=PurePosixPath(normalised).name,
        file_path=normalised,
        lang="go",
        content_hash=content_hash,
        metadata={"extractor": EXTRACTOR_ID, "package": pkg_name},
    )
    # Prepend so the file node leads its descendants in emission order.
    result.nodes.insert(0, file_node)

    module_node = GraphNode(
        uid=module_uid_str,
        kind="code:module",
        label=pkg_name,
        file_path=normalised,
        lang="go",
        metadata={"extractor": EXTRACTOR_ID, "package": pkg_name},
    )
    result.nodes.append(module_node)
    result.edges.append(
        GraphEdge(
            source_uid=file_uid_str,
            target_uid=module_uid_str,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )

    # Package node (shared across files of the same package).
    pkg_node_uid = package_uid(pkg_name)
    result.nodes.append(
        GraphNode(
            uid=pkg_node_uid,
            kind="code:package",
            label=pkg_name,
            lang="go",
            metadata={"extractor": EXTRACTOR_ID},
        )
    )
    result.edges.append(
        GraphEdge(
            source_uid=pkg_node_uid,
            target_uid=module_uid_str,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )

    _walk_build_tags(content, file_uid_str=file_uid_str, result=result)

    # When tree-sitter is unavailable, also emit the simple regex-call edges
    # (covered inside _walk_regex). When tree-sitter ran, still emit
    # qualified calls because the AST walker is structural-only.
    if used_ts:
        _walk_calls_regex(content, module_uid_str=module_uid_str, result=result)

    emit_contains_spine(
        file_path=path,
        file_uid_=file_uid_str,
        result=result,
        extractor_id=EXTRACTOR_ID,
    )
    _promote_stubs(result)
    return result


__all__ = [
    "EXTRACTOR_ID",
    "class_uid",
    "extract",
    "file_uid",
    "func_uid",
    "import_uid",
    "method_uid",
    "module_uid",
    "package_uid",
    "variable_uid",
]
