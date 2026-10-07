"""graph_os — Go package-level declarations: imports, vars, consts, build tags.

Everything a Go file declares outside a func or type body. Imports the
`_go_uids` leaf only.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..resolve_go import default_package_name
from ..types import EvidenceSignal, GraphEdge, GraphNode
from ._go_uids import (
    EXTRACTOR_ID,
    _find_field,
    _node_text,
    import_uid,
    package_uid,
    variable_uid,
)
from .md_links import ExtractionResult

_BUILD_TAG_RE = re.compile(r"^//go:build\s+(?P<expr>[^\n]+)$", re.MULTILINE)


@dataclass
class GoImports:
    """A file's imports: the name each is used by, and its in-repo directory if any."""

    package_dir_for: Callable[[str], str | None]
    # In-repo directory → its `package` clause name, which need not be the folder's.
    package_name_for: Callable[[str], str] = lambda _directory: ""
    by_name: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    seen: set[str] = field(default_factory=set)


def _walk_imports(
    node: Any,
    content_bytes: bytes,
    *,
    normalised: str,
    module_uid_str: str,
    result: ExtractionResult,
    imports: GoImports,
) -> None:
    specs = [child for child in node.children if child.type == "import_spec"]
    for child in node.children:
        if child.type == "import_spec_list":
            specs.extend(sub for sub in child.children if sub.type == "import_spec")
    for spec in specs:
        _emit_import_spec(
            spec,
            content_bytes,
            module_uid_str,
            result,
            imports,
            source_span=f"{normalised}:{spec.start_point[0] + 1}",
        )


def _emit_import_spec(
    spec: Any,
    content_bytes: bytes,
    module_uid_str: str,
    result: ExtractionResult,
    imports: GoImports,
    *,
    source_span: str,
) -> None:
    name_node = _find_field(spec, "name")
    path_node = _find_field(spec, "path")
    if path_node is None:
        return
    raw_path = _node_text(path_node, content_bytes).strip().strip('"')
    if not raw_path or raw_path in imports.seen:
        return
    imports.seen.add(raw_path)
    alias = _node_text(name_node, content_bytes) if name_node is not None else ""
    is_dot = alias == "."
    is_blank = alias == "_"
    in_repo_dir = imports.package_dir_for(raw_path)
    local_name = alias if alias and not is_dot and not is_blank else ""
    if not alias:
        local_name = (
            imports.package_name_for(in_repo_dir) if in_repo_dir else ""
        ) or default_package_name(raw_path)
    if local_name:
        imports.by_name[local_name] = (raw_path, in_repo_dir)
    # An in-repo import lands on the imported package's own node; only a
    # third-party path keeps the shared `code:external:<path>` library node.
    target = package_uid(in_repo_dir) if in_repo_dir else import_uid(raw_path)
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
    if not in_repo_dir:
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
            source_span=source_span,
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
    # `var ( a = 1; b T )` wraps its specs in a var_spec_list.
    specs = [
        spec
        for child in node.children
        for spec in (child.children if child.type.endswith("_spec_list") else [child])
        if spec.type == spec_kind
    ]
    for child in specs:
        line = child.start_point[0] + 1
        for grand in child.children:
            if grand.type == "identifier":
                name = _node_text(grand, content_bytes)
                # `var _ Iface = T{}` binds nothing: the blank identifier is no variable.
                if not name or name == "_":
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
