"""graph_os — go.mod extractor: the module a tree builds and the modules it requires.

`module <path>` is recorded on the file node (`metadata.go_module`), as are the
`tool` directives (Go 1.24), which make a module required without an import,
and the `ignore` directives (Go 1.25), whose directories the go tool skips.
Every `require`, a single line or a block entry, is a `requires` edge from the
go.mod file to `code:external:<module>`, the node the Go imports of that module
and of its sub-packages already reach; the version and `// indirect` ride on
the evidence. Any other file named `*.mod` is not Go's and yields a bare file node.

A module directory holding Go code the walk never indexes (`build/`, `dist/`, a
gitignored tree) is listed in `metadata.go_unindexed_dirs`: no import there is
in the graph, so a require it alone uses cannot be called unused. `vendor/`,
`testdata/` and `_` / `.` directories are not listed; the Go tool ignores them.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ..ingest.base import is_excluded, is_gitignored
from ..toolchain import get_active
from ..types import EvidenceSignal, GraphEdge, GraphNode
from ._extract_base import _promote_stubs, emit_contains_spine
from .md_links import ExtractionResult, _normalize_path

EXTRACTOR_ID = "code_gomod@v1"

_BLOCK_START_RE = re.compile(r"^(?P<directive>\w+)\s*\($")
_DIRECTIVE_RE = re.compile(r"^(?P<directive>\w+)\s+(?P<rest>.+)$")
_GO_IGNORED_DIRS = frozenset({"vendor", "testdata"})
_MAX_UNINDEXED = 20


@dataclass
class _Requirement:
    module: str
    version: str
    indirect: bool
    line: int


@dataclass
class _GoMod:
    module_path: str = ""
    tools: list[str] = field(default_factory=list)
    ignores: list[str] = field(default_factory=list)
    requires: list[_Requirement] = field(default_factory=list)


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a go.mod file → its file node and one `requires` edge per required module."""
    result = ExtractionResult()
    normalised = _normalize_path(path)
    file_uid = f"code:file:{normalised}"
    go_mod = _parse(content) if PurePosixPath(normalised).name == "go.mod" else _GoMod()
    metadata: dict[str, object] = {"extractor": EXTRACTOR_ID}
    if go_mod.module_path:
        metadata["go_module"] = go_mod.module_path
    if go_mod.tools:
        metadata["go_tools"] = go_mod.tools
    if go_mod.ignores:
        metadata["go_ignore"] = go_mod.ignores
    if go_mod.module_path and (unindexed := _unindexed_go_dirs(normalised)):
        metadata["go_unindexed_dirs"] = unindexed
    result.nodes.append(
        GraphNode(
            uid=file_uid,
            kind="code:file",
            label=PurePosixPath(normalised).name,
            file_path=normalised,
            lang="gomod",
            metadata=metadata,
        )
    )
    for requirement in go_mod.requires:
        signal = "go_require_indirect" if requirement.indirect else "go_require"
        result.edges.append(
            GraphEdge(
                source_uid=file_uid,
                target_uid=f"code:external:{requirement.module}",
                edge_type="requires",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
                source_span=f"{normalised}:{requirement.line}",
                evidence=(EvidenceSignal(signal, 1.0, note=requirement.version),),
            )
        )
    emit_contains_spine(
        file_path=path, file_uid_=file_uid, result=result, extractor_id=EXTRACTOR_ID
    )
    _promote_stubs(result)
    return result


def _parse(content: str) -> _GoMod:
    go_mod = _GoMod()
    block = ""
    for number, raw in enumerate(content.splitlines(), start=1):
        code, _, comment = raw.partition("//")
        line = code.strip()
        if block and line == ")":
            block = ""
            continue
        if block:
            directive, rest = block, line
        elif start := _BLOCK_START_RE.match(line):
            block = start.group("directive")
            continue
        elif single := _DIRECTIVE_RE.match(line):
            directive, rest = single.group("directive"), single.group("rest")
        else:
            continue
        words = rest.split()
        if not words:
            continue
        target = words[0].strip('"')
        if directive == "module":
            go_mod.module_path = target
        elif directive == "tool":
            go_mod.tools.append(target)
        elif directive == "ignore":
            go_mod.ignores.append(target)
        elif directive == "require":
            version = words[1] if len(words) > 1 else ""
            go_mod.requires.append(
                _Requirement(target, version, comment.strip() == "indirect", number)
            )
    return go_mod


def _unindexed_go_dirs(go_mod: str) -> list[str]:
    context = get_active()
    if context is None or not context.repo_root:
        return []
    root = Path(context.repo_root)
    found: list[str] = []
    for directory, subdirectories, _files in os.walk(root / PurePosixPath(go_mod).parent):
        kept = []
        for name in sorted(subdirectories):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            probe = f"{relative}/probe.go"
            if (
                name in _GO_IGNORED_DIRS
                or name.startswith(("_", "."))
                or (path / "go.mod").exists()
            ):
                continue
            if is_excluded(probe) or is_gitignored(root, probe):
                if any(path.rglob("*.go")):
                    found.append(relative)
                continue
            kept.append(name)
        subdirectories[:] = kept
        if len(found) >= _MAX_UNINDEXED:
            break
    return found[:_MAX_UNINDEXED]
