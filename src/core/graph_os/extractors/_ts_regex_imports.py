"""Regex import scanning and module-specifier resolution for the TS fallback.

Comment/string stripping lives here too: it is length-preserving so the import
scan keeps accurate line numbers, and the declaration scan reuses it. Module
resolution follows `tsc --traceResolution` precedence — relative path, then
tsconfig `paths` aliases, then `baseUrl`, then bare package name.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from ..types import EvidenceSignal, GraphEdge, GraphNode
from ._ts_uids import EXTRACTOR_ID
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
