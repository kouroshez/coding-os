"""Regex import scanning and module-specifier resolution for the TS fallback.

Comment/string stripping lives here too: it is length-preserving so the import
scan keeps accurate line numbers, and the declaration scan reuses it. Module
resolution delegates to `graph_os.resolve_ts` whenever a repo root is active.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path, PurePosixPath

from .. import resolve_ts
from ..toolchain import get_active
from ..types import EvidenceSignal, GraphEdge, GraphNode
from ._ts_uids import EXTRACTOR_ID
from .md_links import ExtractionResult, _normalize_path

# ---------------------------------------------------------------------------

# A string is skipped whole, so `'src/*'` or `"https://…"` opens no comment.
_STRING_OR_COMMENT_RE = re.compile(
    r"""'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\])*`"""
    r"""|(?P<comment>/\*[\s\S]*?\*/|//[^\n]*)"""
)
_STRING_RE = re.compile(r"""(?P<q>['"`])(?:\\.|(?!(?P=q)).)*(?P=q)""")

# Declarations.
_IMPORT_RE = re.compile(
    r"""^[ \t]*
    import
    \s+
    (?P<type_only>type\s+)?                       # `import type` (captured to flag type-only)
    (?P<clause>
        (?:[A-Za-z_$][\w$]*\s*,\s*)?               # default import before the rest
        (?:\{[^{}]*\}|\*\s+as\s+[A-Za-z_$][\w$]*)  # { a, b as c } | * as ns
      | [A-Za-z_$][\w$]*                           # default import alone
    )
    \s+from\s+
    ['"](?P<module>[^'"]+)['"]
    """,
    re.VERBOSE | re.MULTILINE,
)
_SIDE_EFFECT_IMPORT_RE = re.compile(r"""^[ \t]*import\s+['"](?P<module>[^'"]+)['"]""", re.MULTILINE)
# E7: dynamic import — `import('./mod')` and `await import('./mod')`.
# Used heavily for code-splitting / lazy routes; previously invisible.
_DYNAMIC_IMPORT_RE = re.compile(
    r"""(?<![\w$])(?:await\s+)?import\s*\(\s*['"](?P<module>[^'"]+)['"]\s*\)""",
    re.MULTILINE,
)
# CommonJS: `require('./x')` is an import, and `const { a, b: c } = require(...)`,
# `const { a } = await import(...)` or TypeScript's `import x = require(...)`
# binds names like an import clause does.
_REQUIRE_RE = re.compile(r"""(?<![\w$.])require\s*\(\s*['"](?P<module>[^'"]+)['"]\s*\)""")
_TYPE_REQUIRE_RE = re.compile(r"\bimport\s+type\s+[A-Za-z_$][\w$]*\s*=\s*$")
_REQUIRE_BINDING_RE = re.compile(
    r"""(?:\b(?:const|let|var)\s+|\bimport\s+(?P<type_only>type\s+)?)"""
    r"""(?P<binding>\{[^{}]*\}|[A-Za-z_$][\w$]*)\s*=\s*"""
    r"""(?P<call>require|(?:await\s+)?import)\s*\(\s*['"](?P<module>[^'"]+)['"]\s*\)"""
)


def _strip_comments(content: str) -> str:
    """Remove comments but leave everything else (strings included).

    Used for import extraction — the module specifier IS a string, so
    we must keep it. Length-preserving substitution keeps line numbers
    and `source_span` offsets accurate.
    """

    def _blank(match: re.Match[str]) -> str:
        if match.group("comment") is None:
            return match.group(0)
        return "".join("\n" if c == "\n" else " " for c in match.group(0))

    return _STRING_OR_COMMENT_RE.sub(_blank, content)


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
    exported_as: dict[tuple[str, str], str] | None = None,
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
    exported_as = {} if exported_as is None else exported_as

    for match in _IMPORT_RE.finditer(content):
        clause = match.group("clause")
        module = match.group("module")
        line = content[: match.start()].count("\n") + 1
        target_mod_uid = _resolve_module_uid(path, module)

        bindings = _parse_clause(clause)
        # Type-only imports (`import type {...}` or an all-`type` inline clause)
        # are erased at compile time, so they are NOT a runtime module dependency.
        type_only = bool(match.group("type_only")) or (
            bool(bindings) and all(is_type for _, _, is_type in bindings)
        )

        for local, exported, is_type in bindings:
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
                        "resolved_module": _repo_module(target_mod_uid),
                        "imported": exported,
                        "local": local,
                        "extractor": eid,
                        "type_only": type_only or is_type,
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
            imported_names[local] = _repo_module(target_mod_uid) or module
            if exported not in (local, "*"):
                exported_as[(imported_names[local], local)] = exported

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

    for match in _REQUIRE_BINDING_RE.finditer(content):
        module = match.group("module")
        line = content[: match.start()].count("\n") + 1
        target_mod_uid = _resolve_module_uid(path, module)
        for local, exported in _require_bindings(match.group("binding")):
            result.nodes.append(
                GraphNode(
                    uid=f"code:import:{_normalize_path(path)}::{local}",
                    kind="code:import",
                    label=f"import {local}",
                    file_path=path,
                    start_line=line,
                    lang="ts",
                    metadata={
                        "source_module": module,
                        "resolved_module": _repo_module(target_mod_uid),
                        "imported": exported,
                        "local": local,
                        "extractor": eid,
                        "type_only": bool(match.group("type_only")),
                        "require": match.group("call") == "require",
                        "dynamic": match.group("call") != "require",
                    },
                )
            )
            result.edges.append(
                GraphEdge(
                    source_uid=module_uid_,
                    target_uid=f"code:import:{_normalize_path(path)}::{local}",
                    edge_type="contains",
                    extractor=eid,
                    confidence=1.0,
                )
            )
            imported_names[local] = _repo_module(target_mod_uid) or module
            if exported not in (local, "*"):
                exported_as[(imported_names[local], local)] = exported
    required: set[str] = set()
    for match in _REQUIRE_RE.finditer(content):
        module = match.group("module")
        if module in required:
            continue
        required.add(module)
        # `import type x = require('./a')` names a type, erased at compile time.
        type_only = bool(
            _TYPE_REQUIRE_RE.search(content, max(0, match.start() - 80), match.start())
        )
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=_resolve_module_uid(path, module),
                edge_type="imports_type" if type_only else "imports",
                extractor=eid,
                confidence=0.5 if type_only else 0.85,
                source_span=f"{path}:{content[: match.start()].count(chr(10)) + 1}",
                evidence=(
                    EvidenceSignal(
                        "ts_type_only_import" if type_only else "ts_require",
                        0.5 if type_only else 0.85,
                    ),
                ),
            )
        )

    # E7: dynamic imports (lazy routes / code-splitting).
    for match in _DYNAMIC_IMPORT_RE.finditer(content):
        module = match.group("module")
        line = content[: match.start()].count("\n") + 1
        target_mod_uid = _resolve_module_uid(path, module)
        in_type = _in_type_position(content, match)
        result.edges.append(
            GraphEdge(
                source_uid=module_uid_,
                target_uid=target_mod_uid,
                edge_type="imports_type" if in_type else "imports",
                extractor=eid,
                confidence=0.5 if in_type else 0.7,
                source_span=f"{path}:{line}",
                evidence=(
                    EvidenceSignal(
                        "ts_type_import" if in_type else "ts_dynamic_import",
                        0.5 if in_type else 0.7,
                    ),
                ),
            )
        )

    return imported_names


def link_platform_twins(module_uid_: str, result: ExtractionResult) -> None:
    """Add an edge to each platform twin (`Map.android.tsx`) of a file the module imports."""
    # Metro and react-native-web pick `Map.ios.tsx` / `Map.android.tsx` / `Map.web.tsx`
    # per platform, so `./Map` depends on every variant the folder holds.
    root = _active_root()
    if root is None:
        return
    for edge in list(result.edges):
        repo_file = _repo_module(edge.target_uid) if edge.source_uid == module_uid_ else ""
        if not repo_file or edge.edge_type not in ("imports", "imports_type", "re_exports"):
            continue
        for twin in resolve_ts.platform_twins(root, repo_file):
            result.edges.append(
                replace(
                    edge,
                    target_uid=f"code:module:{twin}",
                    evidence=(EvidenceSignal("ts_platform_twin", edge.confidence),),
                )
            )


_TYPEOF_RE = re.compile(r"typeof\s*$")
_MEMBER_AFTER_RE = re.compile(r"\s*\.\s*([A-Za-z_$][\w$]*)")
_PROMISE_MEMBERS = frozenset({"then", "catch", "finally"})


def _in_type_position(content: str, match: re.Match[str]) -> bool:
    # `typeof import('./x')` and `import('./x').Props` name a type and are
    # erased; `import('./x').then(...)` loads the module at runtime.
    if _TYPEOF_RE.search(content, max(0, match.start() - 16), match.start()):
        return True
    member = _MEMBER_AFTER_RE.match(content, match.end())
    return member is not None and member.group(1) not in _PROMISE_MEMBERS


def _require_bindings(binding: str) -> list[tuple[str, str]]:
    """`(local, exported)` per name a `require` binds; a whole module binds `*`."""
    binding = binding.strip()
    if not binding.startswith("{"):
        return [(binding, "*")]
    names = []
    for part in binding[1:-1].split(","):
        name = part.split("=", 1)[0].strip()
        if not name or name.startswith("..."):
            continue
        exported, _, local = name.partition(":")
        names.append((local.strip() or exported.strip(), exported.strip()))
    return names


_NAMESPACE_RE = re.compile(r"\*\s+as\s+([A-Za-z_$][\w$]*)")


def _parse_clause(clause: str) -> list[tuple[str, str, bool]]:
    """`(local, exported, type_only)` per binding; a default import exports `default`."""
    clause = clause.strip()
    bindings: list[tuple[str, str, bool]] = []
    if not clause.startswith(("{", "*")):
        default, _, clause = clause.partition(",")
        bindings.append((default.strip(), "default", False))
        clause = clause.strip()
    namespace = _NAMESPACE_RE.match(clause)
    if namespace:
        bindings.append((namespace.group(1), "*", False))
    elif clause.startswith("{"):
        for part in clause[1:-1].split(","):
            name = part.strip()
            if not name:
                continue
            # An inline `type ` marker survives the `as` split, or
            # `{ type Foo as Bar }` is misread as a runtime import.
            is_type = name.startswith("type ")
            exported, _, local = (name[5:] if is_type else name).partition(" as ")
            bindings.append((local.strip() or exported.strip(), exported.strip(), is_type))
    return bindings


def point_at_exported_names(
    result: ExtractionResult, exported_as: dict[tuple[str, str], str]
) -> None:
    # Calls and JSX name what the importer bound (`b` in `{ a as b }`, `Card`
    # for a default import); the linker looks the exported name up.
    if not exported_as:
        return
    for index, edge in enumerate(result.edges):
        module, _, local = edge.target_uid.removeprefix("code:external:").rpartition(":")
        exported = (
            exported_as.get((module, local))
            if edge.target_uid.startswith("code:external:")
            else None
        )
        if exported is not None:
            result.edges[index] = replace(edge, target_uid=f"code:external:{module}:{exported}")


def _resolve_module_uid(origin: str, specifier: str) -> str:
    """Resolve an import specifier to a module uid.

    With an active repo root the specifier resolves the way TypeScript would
    (`resolve_ts`), so an existing file yields its own module uid. A `paths`
    alias or relative path that names no file keeps an in-repo uid, which
    tells a broken import apart from a third-party package.
    """
    root = _active_root()
    if root is not None:
        resolved = resolve_ts.resolve(origin, specifier, root)
        resolved = resolved or resolve_ts.alias_target(origin, specifier, root)
        if resolved:
            return f"code:module:{resolved}"
    if specifier.startswith("."):
        return f"code:module:{_guess_relative(origin, specifier)}"
    return f"code:module:npm:{specifier}"


def _active_root() -> Path | None:
    context = get_active()
    return Path(context.repo_root) if context is not None and context.repo_root else None


def _guess_relative(origin: str, specifier: str) -> str:
    parts: list[str] = []
    for part in (PurePosixPath(origin).parent / specifier).as_posix().split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    resolved = "/".join(parts)
    # No root to probe: assume `.ts`, the extractor's own file convention.
    return resolved if "." in PurePosixPath(resolved).name else f"{resolved}.ts"


def _repo_module(module_uid: str) -> str:
    key = module_uid.removeprefix("code:module:")
    return "" if key.startswith("npm:") else key
