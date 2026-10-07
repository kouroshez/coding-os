"""go.mod gaps for cos_graph_undefined: an import no go.mod requires, a require nothing imports.

Each Go file answers to its nearest go.mod. An import whose first path element
has a dot is third-party; it must fall under a module that go.mod requires or
under a module of the workspace, or the build fails with "no required module
provides package". A direct require (not `// indirect`) that no file under the
go.mod imports, at the module or below it, and no `tool` directive names, is
what `go mod tidy` would drop. Files in testdata/ and `_` / `.` directories are
not built and count for neither, and a go.mod whose tree holds Go code the walk
skips (`go_unindexed_dirs`) reports no unused require: its users may be there.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any


@dataclass(frozen=True)
class _GoModule:
    go_mod: str
    module_path: str
    tools: tuple[str, ...]
    partial: bool
    ignores: tuple[str, ...]


_GoMods = dict[str, _GoModule]


def _go_module_gaps(conn: Any, wanted: set[str] | None) -> list[dict[str, Any]]:
    go_mods = _go_mods(conn)
    if not go_mods:
        return []
    workspace = [module.module_path for module in go_mods.values()]
    requires = _go_requires(conn)
    imported = _go_imports(conn, go_mods)
    found = []
    for module_info in go_mods.values():
        go_mod, module_path = module_info.go_mod, module_info.module_path
        required = requires.get(go_mod, [])
        declared = [*workspace, *(module for module, _, _ in required)]
        for file_path, path, line in imported.get(go_mod, []):
            third_party = "." in path.split("/")[0]
            if third_party and not _under(path, declared) and _wanted(file_path, wanted):
                found.append(_gap(file_path, line, path, "undeclared_module", go_mod))
        used = [path for _, path, _ in imported.get(go_mod, [])] + list(module_info.tools)
        for module, indirect, line in required:
            unused = (
                not module_info.partial
                and not indirect
                and module != module_path
                and not any(_under(path, [module]) for path in used)
            )
            if unused and _wanted(go_mod, wanted):
                found.append(_gap(go_mod, line, module, "unused_requirement", go_mod))
    return found


def _go_mods(conn: Any) -> _GoMods:
    go_mods: _GoMods = {}
    for file_path, metadata_json in conn.execute(
        "SELECT file_path, metadata_json FROM graph_nodes "
        "WHERE kind = 'file' AND lang = 'gomod' AND file_path IS NOT NULL"
    ).fetchall():
        metadata = json.loads(metadata_json or "{}")
        if metadata.get("go_module"):
            directory = PurePosixPath(str(file_path)).parent.as_posix()
            tools = tuple(metadata.get("go_tools") or ())
            go_mods[directory] = _GoModule(
                str(file_path),
                str(metadata["go_module"]),
                tools,
                bool(metadata.get("go_unindexed_dirs")),
                tuple(metadata.get("go_ignore") or ()),
            )
    return go_mods


def _go_requires(conn: Any) -> dict[str, list[tuple[str, bool, int | None]]]:
    requires: dict[str, list[tuple[str, bool, int | None]]] = {}
    for go_mod, uid, span, signal in conn.execute(
        "SELECT s.file_path, t.uid, e.source_span, ev.signal_name FROM graph_edges_v12 e "
        "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id "
        "LEFT JOIN graph_evidence_v12 ev ON ev.edge_id = e.id "
        "WHERE e.edge_type = 'requires' AND e.extractor = 'code_gomod@v1'"
    ).fetchall():
        module = str(uid).removeprefix("code:external:")
        requires.setdefault(str(go_mod), []).append(
            (module, signal == "go_require_indirect", _line(span))
        )
    return requires


def _go_imports(conn: Any, go_mods: _GoMods) -> dict[str, list[tuple[str, str, int | None]]]:
    imported: dict[str, list[tuple[str, str, int | None]]] = {}
    for file_path, uid, span in conn.execute(
        "SELECT src.file_path, t.uid, e.source_span FROM graph_edges_v12 e "
        "JOIN graph_nodes src ON src.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id "
        "WHERE e.edge_type = 'imports' AND src.lang = 'go' AND src.file_path IS NOT NULL "
        "AND t.uid LIKE 'code:external:%'"
    ).fetchall():
        owner = _nearest_go_mod(str(file_path), go_mods)
        if owner is not None and not _go_ignores(str(file_path), owner):
            path = str(uid).removeprefix("code:external:")
            imported.setdefault(owner.go_mod, []).append((str(file_path), path, _line(span)))
    return imported


def _nearest_go_mod(file_path: str, go_mods: _GoMods) -> _GoModule | None:
    for directory in PurePosixPath(file_path).parents:
        if directory.as_posix() in go_mods:
            return go_mods[directory.as_posix()]
    return None


def _go_ignores(file_path: str, owner: _GoModule) -> bool:
    # The go tool skips testdata/, `_` and `.` directories, and the go.mod's
    # `ignore` paths: `./x` from the module root, `x` at any depth.
    directories = PurePosixPath(file_path).parts[:-1]
    if any(part == "testdata" or part.startswith(("_", ".")) for part in directories):
        return True
    root = PurePosixPath(owner.go_mod).parent
    inside = "/" + PurePosixPath(file_path).parent.relative_to(root).as_posix() + "/"
    for ignored in owner.ignores:
        if ignored.startswith("./"):
            if inside.startswith("/" + ignored[2:].strip("/") + "/"):
                return True
        elif "/" + ignored.strip("/") + "/" in inside:
            return True
    return False


def _wanted(file_path: str, wanted: set[str] | None) -> bool:
    return wanted is None or file_path in wanted


def _under(path: str, modules: Sequence[str]) -> bool:
    return any(path == module or path.startswith(f"{module}/") for module in modules)


def _line(span: Any) -> int | None:
    tail = str(span or "").rpartition(":")[2]
    return int(tail) if tail.isdigit() else None


def _gap(file_path: str, line: int | None, name: str, reason: str, go_mod: str) -> dict[str, Any]:
    return {
        "file": file_path,
        "line": line,
        "name": name,
        "lang": "go",
        "reason": reason,
        "module": go_mod,
    }
