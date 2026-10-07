"""graph_os — what a TS/JS barrel re-exports, and under which name.

`export { a as b } from './m'`, `export * from './m'` and `import { a } from
'./m'; export { a as b }` make the barrel re-export './m' (`re_exports`). The
names go on the barrel's module node — `reexported_as`: exported name → [repo
file, its name there] — so the linker follows `b` to `a`, a rename no symbol of
the barrel shows. `export type …`, or a clause of `type` names only, re-exports
a type erased at run time (`ts_type_reexport`), which no import cycle runs through.
"""

from __future__ import annotations

import re

from ..types import EvidenceSignal, GraphEdge
from ._ts_regex_imports import _parse_clause, _repo_module, _resolve_module_uid
from .md_links import ExtractionResult

VALUE_CONFIDENCE = 0.9
TYPE_CONFIDENCE = 0.5

_EXPORT_FROM_RE = re.compile(
    r"""^[ \t]*export\s+(?P<type_only>type\s+)?(?:\*(?:\s+as\s+[\w$]+)?|(?P<names>\{[^{}]*\}))"""
    r"""\s+from\s+['"](?P<module>[^'"]+)['"]""",
    re.MULTILINE,
)
_EXPORT_CLAUSE_RE = re.compile(
    r"""^[ \t]*export\s+(?P<type_only>type\s+)?\{(?P<names>[^{}]*)\}\s*(?:;|$)""", re.MULTILINE
)


def extract_reexports(
    *, path: str, module_uid_: str, content: str, result: ExtractionResult, extractor: str
) -> dict[str, list[str]]:
    """Emit the barrel's `re_exports` edges; return {exported name: [repo file, name there]}."""
    renamed: dict[str, list[str]] = {}
    found: dict[str, tuple[int, bool]] = {}
    for match in _EXPORT_FROM_RE.finditer(content):
        target = _resolve_module_uid(path, match.group("module"))
        clause = _parse_clause(match.group("names") or "{}")
        type_only = bool(match.group("type_only")) or (
            bool(clause) and all(is_type for _, _, is_type in clause)
        )
        _note(found, target, _line(content, match), type_only)
        for exported, original, _ in clause:
            if _repo_module(target):
                renamed[exported] = [_repo_module(target), original]
    imports = _imports(result, path)
    for match in _EXPORT_CLAUSE_RE.finditer(content):
        # `export { local as exported }`: the clause reads the other way round from an import.
        clause = [
            (local, exported, is_type)
            for exported, local, is_type in _parse_clause("{" + match.group("names") + "}")
            if local in imports
        ]
        for source in sorted({imports[local][0] for local, _, _ in clause}):
            # A name brought in by `import type` stays a type when re-exported.
            type_only = bool(match.group("type_only")) or all(
                is_type or imports[local][2]
                for local, _, is_type in clause
                if imports[local][0] == source
            )
            _note(found, f"code:module:{source}", _line(content, match), type_only)
        for local, exported, _ in clause:
            renamed[exported] = list(imports[local][:2])
    for target, (line, type_only) in found.items():
        _reexport(result, module_uid_, target, line, path, extractor, type_only)
    return renamed


def _note(found: dict[str, tuple[int, bool]], target: str, line: int, type_only: bool) -> None:
    # Both re-exports of one module share an edge key; the value one runs, so it wins.
    if target not in found or (found[target][1] and not type_only):
        found[target] = (line, type_only)


def _imports(result: ExtractionResult, path: str) -> dict[str, tuple[str, str, bool]]:
    return {
        str(node.metadata["local"]): (
            str(node.metadata["resolved_module"]),
            str(node.metadata.get("imported") or node.metadata["local"]),
            bool(node.metadata.get("type_only")),
        )
        for node in result.nodes
        if node.kind == "code:import"
        and node.file_path == path
        and node.metadata.get("resolved_module")
        and node.metadata.get("local")
    }


def _reexport(
    result: ExtractionResult,
    source: str,
    target: str,
    line: int,
    path: str,
    extractor: str,
    type_only: bool,
) -> None:
    confidence = TYPE_CONFIDENCE if type_only else VALUE_CONFIDENCE
    result.edges.append(
        GraphEdge(
            source_uid=source,
            target_uid=target,
            edge_type="re_exports",
            extractor=extractor,
            confidence=confidence,
            source_span=f"{path}:{line}",
            evidence=(
                EvidenceSignal("ts_type_reexport" if type_only else "ts_reexport", confidence),
            ),
        )
    )


def _line(content: str, match: re.Match[str]) -> int:
    return content.count("\n", 0, match.start()) + 1
