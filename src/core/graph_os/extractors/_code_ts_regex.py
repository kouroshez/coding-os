"""Regex fallback for the TypeScript extractor — used when tree-sitter is absent.

Two independent implementations of one contract live in this extractor: the
tree-sitter walk in code_ts.py and this pattern scan. They change for different
reasons — a grammar bump versus a parse gap someone hit in the wild — so a fix
to one should never force the other through review.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from ..types import EvidenceSignal, GraphEdge, GraphNode

# Late import to avoid a cycle: code_ts imports this module for the fallback.
from .code_ts import (
    EXTRACTOR_ID,
    class_uid,
    function_uid,
    interface_uid,
    module_uid,
)
from .md_links import ExtractionResult, _normalize_path

# ---------------------------------------------------------------------------

_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*[\s\S]*?\*/")
_STRING_RE = re.compile(r"""(?P<q>['"`])(?:\\.|(?!(?P=q)).)*(?P=q)""")

# Declarations.
_IMPORT_RE = re.compile(
    r"""^\s*
    import
    \s+
    (?P<type_only>type\s+)?                       # `import type` (captured to flag type-only)
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
_SIDE_EFFECT_IMPORT_RE = re.compile(r"""^\s*import\s+['"](?P<module>[^'"]+)['"]""", re.MULTILINE)
# E7: dynamic import — `import('./mod')` and `await import('./mod')`.
# Used heavily for code-splitting / lazy routes; previously invisible.
_DYNAMIC_IMPORT_RE = re.compile(
    r"""(?<![\w$])(?:await\s+)?import\s*\(\s*['"](?P<module>[^'"]+)['"]\s*\)""",
    re.MULTILINE,
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


def _extract_imports(
    *,
    path: str,
    module_uid_: str,
    content: str,
    result: ExtractionResult,
    extractor_override: str | None = None,
) -> dict[str, str]:
    """Emit import nodes + edges and return {local_name -> module specifier}.

    TASK-121: when ``extractor_override`` is set (the caller has
    detected a successful tree-sitter parse and the user has opted in
    via `--extractor=tree-sitter`), every emitted import edge / node
    carries that ID instead of the legacy ``code_ts@v1``.  The regex
    keeps doing the extraction — the overlay parse acts as the
    "is this really TS/TSX?" gate so a successful tag swap means a
    grammar-validated source.
    """
    eid = extractor_override or EXTRACTOR_ID
    eid_signal_named = "tree_sitter_import" if extractor_override else "ts_import"
    eid_signal_side = (
        "tree_sitter_import_side_effect" if extractor_override else "ts_import_side_effect"
    )
    imported_names: dict[str, str] = {}

    for match in _IMPORT_RE.finditer(content):
        clause = match.group("clause")
        module = match.group("module")
        line = content[: match.start()].count("\n") + 1
        target_mod_uid = _resolve_module_uid(path, module)

        names = _parse_clause(clause)
        # Type-only imports (`import type {...}` or an all-`type` inline clause)
        # are erased at compile time, so they are NOT a runtime module dependency.
        value_names = [n for n in names if not n.startswith("type ")]
        type_only = bool(match.group("type_only")) or (bool(names) and not value_names)

        for name in names:
            local = name[5:].strip() if name.startswith("type ") else name
            # E3: drop {line} from UID so import-shuffle doesn't spawn
            # duplicates. Line still carried in start_line.
            imp_uid = f"code:import:{_normalize_path(path)}::{local}"
            result.nodes.append(
                GraphNode(
                    uid=imp_uid,
                    kind="code:import",
                    label=f"import {local}",
                    file_path=path,
                    start_line=line,
                    lang="ts",
                    metadata={
                        "source_module": module,
                        "imported": local,
                        "extractor": eid,
                        "type_only": type_only or name.startswith("type "),
                    },
                )
            )
            result.edges.append(
                GraphEdge(
                    source_uid=module_uid_,
                    target_uid=imp_uid,
                    edge_type="contains",
                    extractor=eid,
                    confidence=1.0,
                )
            )
            imported_names[local] = module

        # Type-only imports get a distinct, lower-confidence `imports_type` edge
        # that cos_graph_cycles excludes, instead of a phantom runtime `imports`
        # edge; value imports are unchanged (edge_type='imports', confidence 0.9).
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=target_mod_uid,
                edge_type="imports_type" if type_only else "imports",
                extractor=eid,
                confidence=0.5 if type_only else 0.9,
                source_span=f"{path}:{line}",
                evidence=(
                    EvidenceSignal(
                        "ts_type_only_import" if type_only else eid_signal_named,
                        0.5 if type_only else 0.9,
                    ),
                ),
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
                extractor=eid,
                confidence=0.85,
                source_span=f"{path}:{line}",
                evidence=(EvidenceSignal(eid_signal_side, 0.85),),
            )
        )

    # E7: dynamic imports (lazy routes / code-splitting).
    for match in _DYNAMIC_IMPORT_RE.finditer(content):
        module = match.group("module")
        line = content[: match.start()].count("\n") + 1
        target_mod_uid = _resolve_module_uid(path, module)
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=target_mod_uid,
                edge_type="imports",
                extractor=eid,
                confidence=0.7,
                source_span=f"{path}:{line}",
                evidence=(EvidenceSignal("ts_dynamic_import", 0.7),),
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
                extractor=eid,
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
            # Preserve an inline `type ` marker across the `as`-alias split, else
            # `{ type Foo as Bar }` loses it and is misread as a runtime import.
            is_type = name.startswith("type ")
            if is_type:
                name = name[5:].strip()
            if " as " in name:
                name = name.split(" as ")[-1].strip()
            if is_type:
                name = "type " + name
            names.append(name)
        return names
    if clause.startswith("*"):
        return [clause.split("as")[-1].strip()]
    return [clause]


def _resolve_module_uid(origin: str, specifier: str) -> str:
    """Resolve an import specifier to a module uid.

    Resolution precedence (matches `tsc --traceResolution`):
      1. Relative paths become repo-rooted file uids.
      2. tsconfig `compilerOptions.paths` aliases (TASK-082) — when an
         active ToolchainContext declares e.g. `@shared/*` →
         `packages/shared/src/*`, expand the wildcard and emit a
         repo-local module uid.
      3. tsconfig `compilerOptions.baseUrl` — non-relative specifiers
         that resolve under baseUrl become repo-local module uids.
      4. Otherwise treat as bare package name (`code:module:npm:...`).
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

    # tsconfig.paths / baseUrl aliasing.
    aliased = _resolve_ts_alias(specifier)
    if aliased:
        return f"code:module:{aliased}"

    return f"code:module:npm:{specifier}"


def _resolve_ts_alias(specifier: str) -> str | None:
    """Match `specifier` against the active ToolchainContext's
    tsconfig.paths + baseUrl.  Returns the rewritten POSIX module path
    (without `.ts` suffix appended; caller already handles extension)
    or None when no alias matches.
    """
    try:
        from ..toolchain import get_active
    except ImportError:
        return None
    ctx = get_active()
    if ctx is None:
        return None

    # First-fit alias scan.  Anchored prefix: `@shared/*` matches any
    # specifier starting with `@shared/`.  Exact pattern (no `*`) must
    # equal the specifier.
    for pattern, replacements in ctx.ts_paths.items():
        rewrite = _apply_ts_path(pattern, replacements, specifier)
        if rewrite is not None:
            return rewrite

    # baseUrl path: if the specifier maps onto a file under baseUrl,
    # produce that path.  baseUrl is already repo-relative POSIX.
    if ctx.ts_base_url:
        candidate = f"{ctx.ts_base_url.rstrip('/')}/{specifier}"
        return candidate

    return None


def _apply_ts_path(
    pattern: str,
    replacements: tuple[str, ...],
    specifier: str,
) -> str | None:
    """Implement `tsc`-style `*` substitution for a single paths entry."""
    if "*" in pattern:
        prefix, _, suffix = pattern.partition("*")
        if not specifier.startswith(prefix) or not specifier.endswith(suffix):
            return None
        captured = specifier[len(prefix) : len(specifier) - len(suffix) if suffix else None]
        for repl in replacements:
            if "*" not in repl:
                continue
            return repl.replace("*", captured, 1)
        # No `*` in replacements — use the first as-is.
        return replacements[0] if replacements else None
    if specifier == pattern:
        for repl in replacements:
            return repl
    return None


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
                signature=f"function {name}({match.group('generics') or ''})".replace("()", "(…)"),
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


def _format_class_signature(*, name: str, parent: str | None, implements: str | None) -> str:
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
