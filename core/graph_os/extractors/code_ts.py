"""graph-os — TypeScript / TSX extractor (I.6).

PURPOSE:  Turn a `.ts` / `.tsx` module into GraphNodes + GraphEdges
          (imports, classes, interfaces, functions, methods, exports,
          React components) using a regex-based scanner as the
          deterministic baseline. Tree-sitter + tsserver overlays
          raise confidence in later slices — see plan §7.4.
INPUT:    file path + raw source text.
OUTPUT:   ExtractionResult (same shape as md_links / code_python).
DEPENDS:  stdlib regex only.
NOTES:    The regex scanner is deliberately conservative: it catches
          top-level declarations, imports (including `import type`),
          and call-sites that resolve through the imported local name.
          Inline JSX is tracked only as a React-component callsite
          (`<Button/>` ⇒ `constructs Button`). Comments and strings
          are stripped before the scan so `// import ...` does not
          leak into the graph.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import PurePosixPath

from ..types import EvidenceSignal, GraphEdge, GraphNode
from .md_links import (
    ExtractionResult,
    ParseError,
    _normalize_path,
    _promote_stubs,
)

logger = logging.getLogger("graph_os.extractors.code_ts")

EXTRACTOR_ID = "code_ts@v1"

# ---------------------------------------------------------------------------
# Comment / string stripping — simple but enough for a scanner.
# ---------------------------------------------------------------------------

_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*[\s\S]*?\*/")
_STRING_RE = re.compile(r"""(?P<q>['"`])(?:\\.|(?!(?P=q)).)*(?P=q)""")

# Declarations.
_IMPORT_RE = re.compile(
    r"""^\s*
    import
    \s+
    (?:type\s+)?                                  # `import type`
    (?P<clause>
        \{[^{}]*\}                                 # { a, b as c }
      | [A-Za-z_$][\w$]*                           # default import
      | \*\s+as\s+[A-Za-z_$][\w$]*                 # * as ns
    )
    (?:\s*,\s*\{[^{}]*\})?
    \s+from\s+
    ['"](?P<module>[^'"]+)['"]
    """,
    re.VERBOSE | re.MULTILINE,
)
_SIDE_EFFECT_IMPORT_RE = re.compile(
    r"""^\s*import\s+['"](?P<module>[^'"]+)['"]""", re.MULTILINE
)
_EXPORT_FROM_RE = re.compile(
    r"""^\s*export\s+(?:\*|\{[^{}]*\})\s+from\s+['"](?P<module>[^'"]+)['"]""",
    re.MULTILINE,
)

_CLASS_RE = re.compile(
    r"""^\s*(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+
        (?P<name>[A-Za-z_$][\w$]*)
        (?:\s+extends\s+(?P<parent>[A-Za-z_$][\w$.]*))?
        (?:\s+implements\s+(?P<implements>[^{]+?))?
        \s*\{
    """,
    re.VERBOSE | re.MULTILINE,
)
_INTERFACE_RE = re.compile(
    r"""^\s*(?:export\s+)?interface\s+
        (?P<name>[A-Za-z_$][\w$]*)
        (?:\s+extends\s+(?P<parents>[^{]+?))?
        \s*\{
    """,
    re.VERBOSE | re.MULTILINE,
)
_FUNCTION_RE = re.compile(
    r"""^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+
        (?P<name>[A-Za-z_$][\w$]*)
        (?P<generics><[^>]*>)?
        \s*\(
    """,
    re.VERBOSE | re.MULTILINE,
)
_ARROW_RE = re.compile(
    r"""^\s*(?:export\s+(?:default\s+)?)?
        (?:const|let|var)\s+
        (?P<name>[A-Za-z_$][\w$]*)
        \s*(?::[^=]+)?\s*=\s*
        (?:async\s+)?
        (?:<[^>]*>)?
        \s*\(
    """,
    re.VERBOSE | re.MULTILINE,
)
_METHOD_RE = re.compile(
    r"""^\s*(?:public|protected|private|readonly|async|static|\s)*\s*
        (?P<name>[A-Za-z_$][\w$]*)
        (?P<generics><[^>]*>)?
        \s*\(
    """,
    re.VERBOSE | re.MULTILINE,
)

# Call-site scanner — looks for `name(` and `name.something(`.
_CALL_RE = re.compile(
    r"""(?<![.\w$])
        (?P<target>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)
        \s*\(
    """,
    re.VERBOSE,
)
# JSX component usage — uppercase tag => React component.
_JSX_COMPONENT_RE = re.compile(r"<(?P<name>[A-Z][A-Za-z0-9_]*)\b")

# Decorator — lands on the *next* decl.
_DECORATOR_RE = re.compile(
    r"""^\s*@(?P<target>[A-Za-z_$][\w$.]*)
        (?:\s*\([^)]*\))?\s*$
    """,
    re.VERBOSE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# uid helpers
# ---------------------------------------------------------------------------


def file_uid(path: str) -> str:
    return f"code:file:{_normalize_path(path)}"


def module_uid(path: str) -> str:
    # TS modules identify by file path — no package system by default.
    return f"code:module:{_normalize_path(path)}"


def class_uid(path: str, name: str) -> str:
    return f"code:class:{_normalize_path(path)}::{name}"


def interface_uid(path: str, name: str) -> str:
    return f"code:interface:{_normalize_path(path)}::{name}"


def function_uid(path: str, name: str) -> str:
    return f"code:function:{_normalize_path(path)}::{name}"


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a TS / TSX file → nodes + edges.

    PURPOSE:      Per-file write path invoked by the orchestrator. Uses
                  tree-sitter when the grammar is installed (Phase
                  I.6b); falls back to the regex scanner otherwise so
                  the dogfood build still works when the graph-os
                  extra is skipped.
    INPUT:        file path + raw source.
    OUTPUT:       ExtractionResult.
    DEPENDENCIES: stdlib + optional tree-sitter-typescript.
    NOTES:        Returns the file node even when parsing fails so
                  downstream queries can surface the presence of the
                  file.
    """
    # Tree-sitter overlay pass (I.6b) — runs first to enrich AST-level
    # metadata. Regex scan below continues unchanged so results stay
    # backwards-compatible when the grammar is absent.
    try:
        from ..tree_sitter_overlay import parse as _ts_parse  # noqa: WPS433

        lang_id = "tsx" if path.endswith(".tsx") else "typescript"
        _ts_overlay = _ts_parse(lang_id, content)
    except ImportError:
        _ts_overlay = None
    result = ExtractionResult()
    normalised = _normalize_path(path)
    lang = "tsx" if normalised.endswith(".tsx") else "ts"
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    file_node = GraphNode(
        uid=file_uid(path),
        kind="code:file",
        label=PurePosixPath(normalised).name,
        file_path=normalised,
        lang=lang,
        content_hash=content_hash,
        metadata={"extractor": EXTRACTOR_ID},
    )
    result.nodes.append(file_node)

    try:
        import_scan = _strip_comments(content)
        decl_scan = _strip_comments_and_strings(content)
    except Exception as exc:  # noqa: BLE001
        result.parse_errors.append(ParseError(kind="fatal", detail=str(exc)))
        _promote_stubs(result)
        return result

    overlay_meta: dict[str, object] = {}
    if _ts_overlay is not None:
        overlay_meta["ts_ast_nodes"] = _count_ts_nodes(_ts_overlay.root)
        overlay_meta["ts_language"] = _ts_overlay.language_id
    module = GraphNode(
        uid=module_uid(path),
        kind="code:module",
        label=PurePosixPath(normalised).stem,
        file_path=normalised,
        lang=lang,
        metadata={"extractor": EXTRACTOR_ID, **overlay_meta},
    )
    result.nodes.append(module)
    result.edges.append(
        GraphEdge(
            source_uid=file_node.uid,
            target_uid=module.uid,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )

    imported_names = _extract_imports(
        path=normalised, module_uid_=module.uid, content=import_scan, result=result
    )
    local_names: dict[str, str] = {}
    _extract_classes(
        path=normalised,
        module_uid_=module.uid,
        lang=lang,
        content=decl_scan,
        result=result,
        local_names=local_names,
    )
    _extract_interfaces(
        path=normalised,
        module_uid_=module.uid,
        lang=lang,
        content=decl_scan,
        result=result,
        local_names=local_names,
    )
    _extract_functions(
        path=normalised,
        module_uid_=module.uid,
        lang=lang,
        content=decl_scan,
        result=result,
        local_names=local_names,
    )
    _extract_arrow_fns(
        path=normalised,
        module_uid_=module.uid,
        lang=lang,
        content=decl_scan,
        result=result,
        local_names=local_names,
    )
    _extract_calls(
        path=normalised,
        content=decl_scan,
        imported_names=imported_names,
        local_names=local_names,
        result=result,
    )
    if lang == "tsx":
        _extract_jsx_components(
            path=normalised,
            content=decl_scan,
            imported_names=imported_names,
            local_names=local_names,
            result=result,
        )

    _promote_stubs(result)
    return result


# ---------------------------------------------------------------------------
# Comment / string stripping
# ---------------------------------------------------------------------------


def _strip_comments(content: str) -> str:
    """Remove comments but leave everything else (strings included).

    Used for import extraction — the module specifier IS a string, so
    we must keep it. Length-preserving substitution keeps line numbers
    and `source_span` offsets accurate.
    """

    def _blk(match: re.Match[str]) -> str:
        return "".join("\n" if c == "\n" else " " for c in match.group(0))

    out = _BLOCK_COMMENT_RE.sub(_blk, content)
    out = _LINE_COMMENT_RE.sub(lambda m: " " * len(m.group(0)), out)
    return out


def _strip_comments_and_strings(content: str) -> str:
    """Remove comments AND blank the interior of string / template literals.

    Used for decl + call-site scanning. Keeping quotes (length-
    preserving) means regexes that look for `foo(` won't match inside
    `'foo(\"x\");'`.
    """

    def _str(match: re.Match[str]) -> str:
        raw = match.group(0)
        if len(raw) < 2:
            return raw
        return raw[0] + " " * (len(raw) - 2) + raw[-1]

    out = _strip_comments(content)
    out = _STRING_RE.sub(_str, out)
    return out


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------


def _extract_imports(
    *,
    path: str,
    module_uid_: str,
    content: str,
    result: ExtractionResult,
) -> dict[str, str]:
    """Emit import nodes + edges and return {local_name -> module specifier}."""
    imported_names: dict[str, str] = {}

    for match in _IMPORT_RE.finditer(content):
        clause = match.group("clause")
        module = match.group("module")
        line = content[: match.start()].count("\n") + 1
        target_mod_uid = _resolve_module_uid(path, module)

        for name in _parse_clause(clause):
            imp_uid = (
                f"code:import:{_normalize_path(path)}::{line}:{name}"
            )
            result.nodes.append(
                GraphNode(
                    uid=imp_uid,
                    kind="code:import",
                    label=f"import {name}",
                    file_path=path,
                    start_line=line,
                    lang="ts",
                    metadata={
                        "source_module": module,
                        "imported": name,
                        "extractor": EXTRACTOR_ID,
                    },
                )
            )
            result.edges.append(
                GraphEdge(
                    source_uid=module_uid_,
                    target_uid=imp_uid,
                    edge_type="contains",
                    extractor=EXTRACTOR_ID,
                    confidence=1.0,
                )
            )
            imported_names[name] = module

        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=target_mod_uid,
                edge_type="imports",
                extractor=EXTRACTOR_ID,
                confidence=0.9,
                source_span=f"{path}:{line}",
                evidence=(EvidenceSignal("ts_import", 0.9),),
            )
        )

    for match in _SIDE_EFFECT_IMPORT_RE.finditer(content):
        module = match.group("module")
        line = content[: match.start()].count("\n") + 1
        target_mod_uid = _resolve_module_uid(path, module)
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=target_mod_uid,
                edge_type="imports",
                extractor=EXTRACTOR_ID,
                confidence=0.85,
                source_span=f"{path}:{line}",
                evidence=(EvidenceSignal("ts_import_side_effect", 0.85),),
            )
        )

    for match in _EXPORT_FROM_RE.finditer(content):
        module = match.group("module")
        line = content[: match.start()].count("\n") + 1
        target_mod_uid = _resolve_module_uid(path, module)
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=target_mod_uid,
                edge_type="re_exports",
                extractor=EXTRACTOR_ID,
                confidence=0.9,
                source_span=f"{path}:{line}",
            )
        )

    return imported_names


def _parse_clause(clause: str) -> list[str]:
    clause = clause.strip()
    if clause.startswith("{"):
        inner = clause[1:-1]
        names = []
        for part in inner.split(","):
            name = part.strip()
            if not name:
                continue
            # Drop `as alias` — keep local name.
            if " as " in name:
                name = name.split(" as ")[-1].strip()
            names.append(name)
        return names
    if clause.startswith("*"):
        return [clause.split("as")[-1].strip()]
    return [clause]


def _resolve_module_uid(origin: str, specifier: str) -> str:
    """Resolve an import specifier to a module uid.

    Relative paths become repo-rooted file uids; bare specifiers are
    treated as package names (tracked but not filesystem-resolved
    here — the TS overlay does that in I.6b).
    """
    if specifier.startswith("."):
        origin_dir = PurePosixPath(origin).parent
        candidate = (origin_dir / specifier).as_posix()
        parts: list[str] = []
        for part in candidate.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if parts:
                    parts.pop()
                continue
            parts.append(part)
        resolved = "/".join(parts)
        # Add `.ts` if no extension was given so the uid lines up with
        # the actual file node the TS extractor would emit.
        if "." not in PurePosixPath(resolved).name:
            resolved += ".ts"
        return f"code:module:{resolved}"
    return f"code:module:npm:{specifier}"


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------


def _extract_classes(
    *,
    path: str,
    module_uid_: str,
    lang: str,
    content: str,
    result: ExtractionResult,
    local_names: dict[str, str],
) -> None:
    for match in _CLASS_RE.finditer(content):
        name = match.group("name")
        line = content[: match.start()].count("\n") + 1
        uid = class_uid(path, name)
        signature = _format_class_signature(
            name=name, parent=match.group("parent"), implements=match.group("implements")
        )
        decorators = _collect_preceding_decorators(content, match.start())
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:class",
                label=name,
                file_path=path,
                start_line=line,
                signature=signature,
                lang=lang,
                metadata={
                    "extractor": EXTRACTOR_ID,
                    "decorators": list(decorators),
                },
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
                source_span=f"{path}:{line}",
            )
        )
        if match.group("parent"):
            result.edges.append(
                GraphEdge(
                    source_uid=uid,
                    target_uid=f"code:external:{match.group('parent')}",
                    edge_type="inherits_from",
                    extractor=EXTRACTOR_ID,
                    confidence=0.7,
                    evidence=(EvidenceSignal("ts_extends", 0.7),),
                )
            )
        if match.group("implements"):
            for iface in _split_implements(match.group("implements")):
                result.edges.append(
                    GraphEdge(
                        source_uid=uid,
                        target_uid=f"code:external:{iface}",
                        edge_type="implements",
                        extractor=EXTRACTOR_ID,
                        confidence=0.6,
                    )
                )
        for decorator in decorators:
            result.edges.append(
                GraphEdge(
                    source_uid=uid,
                    target_uid=f"code:external:{decorator}",
                    edge_type="is_decorated_by",
                    extractor=EXTRACTOR_ID,
                    confidence=0.7,
                )
            )


def _extract_interfaces(
    *,
    path: str,
    module_uid_: str,
    lang: str,
    content: str,
    result: ExtractionResult,
    local_names: dict[str, str],
) -> None:
    for match in _INTERFACE_RE.finditer(content):
        name = match.group("name")
        line = content[: match.start()].count("\n") + 1
        uid = interface_uid(path, name)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:interface",
                label=name,
                file_path=path,
                start_line=line,
                lang=lang,
                signature=f"interface {name}",
                metadata={"extractor": EXTRACTOR_ID},
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )
        parents_raw = match.group("parents") or ""
        for parent in _split_implements(parents_raw):
            result.edges.append(
                GraphEdge(
                    source_uid=uid,
                    target_uid=f"code:external:{parent}",
                    edge_type="extends",
                    extractor=EXTRACTOR_ID,
                    confidence=0.7,
                )
            )


def _extract_functions(
    *,
    path: str,
    module_uid_: str,
    lang: str,
    content: str,
    result: ExtractionResult,
    local_names: dict[str, str],
) -> None:
    for match in _FUNCTION_RE.finditer(content):
        name = match.group("name")
        line = content[: match.start()].count("\n") + 1
        uid = function_uid(path, name)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:function",
                label=name,
                file_path=path,
                start_line=line,
                signature=f"function {name}({match.group('generics') or ''})".replace(
                    "()", "(…)"
                ),
                lang=lang,
                metadata={"extractor": EXTRACTOR_ID},
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )


def _extract_arrow_fns(
    *,
    path: str,
    module_uid_: str,
    lang: str,
    content: str,
    result: ExtractionResult,
    local_names: dict[str, str],
) -> None:
    for match in _ARROW_RE.finditer(content):
        name = match.group("name")
        if name in local_names:
            continue
        line = content[: match.start()].count("\n") + 1
        uid = function_uid(path, name)
        result.nodes.append(
            GraphNode(
                uid=uid,
                kind="code:function",
                label=name,
                file_path=path,
                start_line=line,
                signature=f"const {name} = (…) =>",
                lang=lang,
                metadata={"arrow": True, "extractor": EXTRACTOR_ID},
            )
        )
        local_names[name] = uid
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )


# ---------------------------------------------------------------------------
# Call-sites
# ---------------------------------------------------------------------------


_TS_KEYWORDS = frozenset(
    {
        "if",
        "for",
        "while",
        "switch",
        "return",
        "new",
        "catch",
        "function",
        "typeof",
        "await",
        "import",
        "export",
        "throw",
        "yield",
    }
)


def _extract_calls(
    *,
    path: str,
    content: str,
    imported_names: dict[str, str],
    local_names: dict[str, str],
    result: ExtractionResult,
) -> None:
    """Emit call / constructs edges sourced at the module level.

    Per plan §7.2 the baseline scanner records call-sites against the
    enclosing module (not the function) because regex alone cannot
    reliably determine function boundaries. The LSP overlay re-homes
    these edges to the exact caller.
    """
    module = module_uid(path)
    for match in _CALL_RE.finditer(content):
        target = match.group("target")
        root = target.split(".")[0]
        if root in _TS_KEYWORDS:
            continue
        line = content[: match.start()].count("\n") + 1
        is_ctor = target.split(".")[-1][:1].isupper()

        if target in local_names:
            resolved = local_names[target]
            confidence = 0.5
            signal = EvidenceSignal("same_scope", 0.5)
        elif root in imported_names:
            specifier = imported_names[root]
            tail = ".".join(target.split(".")[1:]) or root
            resolved = f"code:external:{specifier}:{tail}"
            confidence = 0.4
            signal = EvidenceSignal("explicit_import", 0.4, note=specifier)
        else:
            resolved = f"code:external:unresolved:{target}"
            confidence = 0.3
            signal = EvidenceSignal("unresolved_call", 0.3)

        result.edges.append(
            GraphEdge(
                source_uid=module,
                target_uid=resolved,
                edge_type="constructs" if is_ctor else "calls",
                extractor=EXTRACTOR_ID,
                confidence=confidence,
                source_span=f"{path}:{line}",
                evidence=(signal,),
            )
        )


def _extract_jsx_components(
    *,
    path: str,
    content: str,
    imported_names: dict[str, str],
    local_names: dict[str, str],
    result: ExtractionResult,
) -> None:
    module = module_uid(path)
    seen: set[str] = set()
    for match in _JSX_COMPONENT_RE.finditer(content):
        name = match.group("name")
        if name in seen:
            continue
        seen.add(name)
        line = content[: match.start()].count("\n") + 1
        if name in local_names:
            resolved = local_names[name]
            confidence = 0.8
        elif name in imported_names:
            resolved = f"code:external:{imported_names[name]}:{name}"
            confidence = 0.7
        else:
            resolved = f"code:external:unresolved:{name}"
            confidence = 0.4
        result.edges.append(
            GraphEdge(
                source_uid=module,
                target_uid=resolved,
                edge_type="constructs",
                extractor=EXTRACTOR_ID,
                confidence=confidence,
                source_span=f"{path}:{line}",
                evidence=(EvidenceSignal("jsx_component", 0.8),),
            )
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_preceding_decorators(content: str, idx: int) -> tuple[str, ...]:
    """Walk backwards from `idx` and return decorators attached to the decl."""
    # Scan at most 5 lines upward.
    upper = max(content.rfind("\n", 0, idx), 0)
    # Find the start of that line.
    line_start = content.rfind("\n", 0, upper)
    line_start = line_start + 1 if line_start >= 0 else 0
    block = content[line_start:idx]
    decorators: list[str] = []
    for match in _DECORATOR_RE.finditer(block):
        decorators.append(match.group("target"))
    return tuple(decorators)


def _format_class_signature(
    *, name: str, parent: str | None, implements: str | None
) -> str:
    parts = [f"class {name}"]
    if parent:
        parts.append(f"extends {parent}")
    if implements:
        ifaces = ", ".join(_split_implements(implements))
        if ifaces:
            parts.append(f"implements {ifaces}")
    return " ".join(parts)


def _count_ts_nodes(root) -> int:
    """Count AST nodes for tree-sitter overlay health-check metric."""
    if root is None:
        return 0
    stack = [root]
    total = 0
    while stack:
        node = stack.pop()
        total += 1
        stack.extend(node.children)
    return total


def _split_implements(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


__all__ = [
    "EXTRACTOR_ID",
    "extract",
    "file_uid",
    "module_uid",
    "class_uid",
    "interface_uid",
    "function_uid",
]
