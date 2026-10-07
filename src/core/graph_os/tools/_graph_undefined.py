"""Undefined names: cos_graph_undefined, and the list cos_graph_detect_changes reports.

Private module of graph_os.tools.graph — import via the graph module,
never directly (the kernel imports this file at its bottom).

Python and TS / JS files carry the names they use but never bind on their module
node (extractors/_undefined_names.py). Go needs the whole package, so it is read
here: a bare call the linker could not bind, to a name no file of that package
defines, is a function nobody wrote or a package nobody imported. A TS import the
linker could not bind, of a name its in-repo target file defines nowhere, is an
export that was renamed or removed (`reason: "not_exported"`). A shell call no
sourced library answered, to a name in the repo's own `prefix_` function family
that no command on PATH carries, is a function renamed or removed. A Go module
imported but never required, or required but never imported, comes from
_graph_undefined_gomod (`undeclared_module` / `unused_requirement`).
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Any

from ..backend import BackendUnavailable
from . import graph as _kernel
from ._graph_envelope import _clamp_int, _fail, _ok, _validate_positive_int
from ._graph_undefined_deps import dependency_gaps
from ._graph_undefined_gomod import _go_module_gaps

_GO_STUB = "code:external:gopkg:"
_SHELL_STUB = "code:external:shfn:"
_BARREL_DEPTH = 6


def undefined_names(conn: Any, files: Sequence[str] | None = None) -> list[dict[str, Any]]:
    wanted = set(files) if files is not None else None
    found = (
        _recorded(conn, wanted)
        + _go_unbound_calls(conn, wanted)
        + _go_unimported(conn, wanted)
        + _ts_broken_imports(conn, wanted)
        + _py_broken_imports(conn, wanted)
        + _sh_unbound_calls(conn, wanted)
        + _go_module_gaps(conn, wanted)
        + dependency_gaps(conn, wanted)
    )
    return sorted(found, key=lambda item: (item["file"], item["line"] or 0, item["name"]))


def _recorded(conn: Any, wanted: set[str] | None) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT file_path, lang, metadata_json FROM graph_nodes WHERE uid LIKE 'code:module:%' "
        "AND file_path IS NOT NULL AND json_array_length(metadata_json, '$.undefined') > 0"
    ).fetchall()
    ambient: set[str] | None = None
    found = []
    for file_path, lang, metadata_json in rows:
        if wanted is not None and file_path not in wanted:
            continue
        for name, line in json.loads(metadata_json).get("undefined", []):
            if lang != "py":
                # `declare function track()` in any .d.ts is a global.
                if ambient is None:
                    ambient = _ambient_names(conn)
                if name in ambient:
                    continue
            found.append(
                {"file": file_path, "line": line, "name": name, "lang": lang, "reason": "undefined"}
            )
    return found


def _ambient_names(conn: Any) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT DISTINCT label FROM graph_nodes WHERE file_path LIKE '%.d.ts' AND label IS NOT NULL"
        ).fetchall()
    }


def _ts_broken_imports(conn: Any, wanted: set[str] | None) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT n.file_path, n.start_line, n.metadata_json FROM graph_nodes n "
        "WHERE n.kind = 'import_' AND n.lang = 'ts' AND n.file_path IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM graph_edges_v12 e WHERE e.source_id = n.id "
        "AND e.extractor = 'import_linker@v1')"
    ).fetchall()
    defines: dict[tuple[str, str], bool] = {}
    found = []
    for file_path, line, metadata_json in rows:
        if wanted is not None and file_path not in wanted:
            continue
        metadata = json.loads(metadata_json or "{}")
        module, name = (
            str(metadata.get("resolved_module") or ""),
            str(metadata.get("imported") or ""),
        )
        if not module or name in ("", "*", "default"):
            continue
        if (module, name) not in defines:
            defines[(module, name)] = _may_define(conn, module, name)
        if not defines[(module, name)]:
            found.append(
                {
                    "file": file_path,
                    "line": line,
                    "name": name,
                    "lang": "ts",
                    "reason": "not_exported",
                    "module": module,
                }
            )
    return found


def _py_broken_imports(conn: Any, wanted: set[str] | None) -> list[dict[str, Any]]:
    # `from app.deps import removed_fn` once deps.py no longer defines it: an
    # ImportError at run time that nothing reported.
    rows = conn.execute(
        "SELECT n.file_path, n.start_line, n.metadata_json FROM graph_nodes n "
        "WHERE n.kind = 'import_' AND COALESCE(n.lang, 'py') = 'py' AND n.file_path LIKE '%.py' "
        "AND NOT EXISTS (SELECT 1 FROM graph_edges_v12 e WHERE e.source_id = n.id "
        "AND e.extractor = 'import_linker@v1')"
    ).fetchall()
    defines: dict[tuple[str, str], bool] = {}
    found = []
    for file_path, line, metadata_json in rows:
        if wanted is not None and file_path not in wanted:
            continue
        metadata = json.loads(metadata_json or "{}")
        module = str(metadata.get("resolved_module") or metadata.get("source_module") or "")
        name = str(metadata.get("imported") or "")
        if not module or not name or metadata.get("wildcard"):
            continue
        if (module, name) not in defines:
            defines[(module, name)] = _py_may_define(conn, module, name)
        if not defines[(module, name)]:
            found.append(
                {
                    "file": file_path,
                    "line": line,
                    "name": name,
                    "lang": "py",
                    "reason": "not_exported",
                    "module": module,
                }
            )
    return found


def _py_may_define(conn: Any, module: str, name: str) -> bool:
    # Unindexed (a library), a submodule, a definition or a re-exporting import,
    # a star import or a module `__getattr__`: not provably missing.
    row = conn.execute(
        "SELECT file_path FROM graph_nodes WHERE uid = ? AND file_path IS NOT NULL",
        (f"code:module:{module}",),
    ).fetchone()
    if row is None:
        return True
    module_file = str(row[0])
    if conn.execute(
        "SELECT 1 FROM graph_nodes WHERE uid = ? OR uid = ?",
        (f"code:module:{module}.{name}", f"code:import:{module_file}::{name}"),
    ).fetchone():
        return True
    if conn.execute(
        "SELECT 1 FROM graph_nodes WHERE file_path = ? AND label IN (?, '__getattr__') "
        "AND kind != 'import_' LIMIT 1",
        (module_file, name),
    ).fetchone():
        return True
    return (
        conn.execute(
            "SELECT 1 FROM graph_nodes WHERE file_path = ? AND kind = 'import_' "
            "AND json_extract(metadata_json, '$.wildcard') = 1 LIMIT 1",
            (module_file,),
        ).fetchone()
        is not None
    )


def _may_define(conn: Any, module: str, name: str, depth: int = 0) -> bool:
    # Unindexed, CommonJS, or defining the name (as a value and a type is still
    # defined) or re-exporting it, directly or through `export *`: not provably broken.
    if depth > _BARREL_DEPTH:
        return True
    module_row = conn.execute(
        "SELECT json_extract(metadata_json, '$.commonjs') FROM graph_nodes WHERE uid = ?",
        (f"code:module:{module}",),
    ).fetchone()
    if module_row is None or module_row[0]:
        return True
    if conn.execute(
        "SELECT 1 FROM graph_nodes WHERE (file_path = ? AND label = ?) OR uid = ? LIMIT 1",
        (module, name, f"code:import:{module}::{name}"),
    ).fetchone():
        return True
    targets = conn.execute(
        "SELECT DISTINCT t.uid, t.file_path FROM graph_edges_v12 e "
        "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id "
        "WHERE e.edge_type = 're_exports' AND s.file_path = ?",
        (module,),
    ).fetchall()
    # A barrel re-exporting a library cannot be checked here.
    return any(
        target_file is None or _may_define(conn, str(target_file), name, depth + 1)
        for _, target_file in targets
    )


def _sh_unbound_calls(conn: Any, wanted: set[str] | None) -> list[dict[str, Any]]:
    # Any command looks like a function call, so only a name in a family the
    # repo's own functions use (`log_`, `cos_`) and absent from PATH counts.
    rows = conn.execute(
        "SELECT DISTINCT src.file_path, stub.uid, e.source_span FROM graph_edges_v12 e "
        "JOIN graph_nodes stub ON stub.id = e.target_id "
        "JOIN graph_nodes src ON src.id = e.source_id "
        f"WHERE e.edge_type = 'calls' AND stub.uid LIKE '{_SHELL_STUB}%' "
        "AND src.file_path IS NOT NULL"
    ).fetchall()
    if not rows:
        return []
    # A name two libraries define stays unbound as ambiguous; it is not missing.
    defined = {
        str(label)
        for (label,) in conn.execute(
            "SELECT DISTINCT label FROM graph_nodes WHERE lang = 'sh' AND kind = 'function'"
        ).fetchall()
    }
    families = {_family(label) for label in defined}
    found = []
    for file_path, uid, span in rows:
        name = str(uid)[len(_SHELL_STUB) :]
        if wanted is not None and file_path not in wanted:
            continue
        if name in defined or _family(name) not in families - {""}:
            continue
        if shutil.which(name) is not None:
            continue
        line = str(span or "").rpartition(":")[2]
        found.append(
            {
                "file": file_path,
                "line": int(line) if line.isdigit() else None,
                "name": name,
                "lang": "sh",
                "reason": "undefined",
            }
        )
    return found


def _family(name: str) -> str:
    head, separator, _ = name.lstrip("_").partition("_")
    return head if separator else ""


def _go_unbound_calls(conn: Any, wanted: set[str] | None) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT DISTINCT src.file_path, stub.uid, e.source_span FROM graph_edges_v12 e "
        "JOIN graph_nodes stub ON stub.id = e.target_id "
        "JOIN graph_nodes src ON src.id = e.source_id "
        f"WHERE e.edge_type = 'calls' AND stub.uid LIKE '{_GO_STUB}%' "
        "AND src.file_path IS NOT NULL"
    ).fetchall()
    # `import . "pkg"` brings in names no index of this package can see.
    dot_importers = {
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT src.file_path FROM graph_edges_v12 e "
            "JOIN graph_evidence_v12 ev ON ev.edge_id = e.id "
            "JOIN graph_nodes src ON src.id = e.source_id "
            "WHERE ev.signal_name = 'go_dot_import'"
        ).fetchall()
    }
    defined: dict[str, set[str]] = {}
    found = []
    for file_path, uid, span in rows:
        directory, _, name = str(uid)[len(_GO_STUB) :].rpartition(":")
        # `Type.method` may come from an embedded type; only a bare name is certain.
        if "." in name or file_path in dot_importers:
            continue
        if wanted is not None and file_path not in wanted:
            continue
        if directory not in defined:
            defined[directory] = _go_labels(conn, directory)
        labels = defined[directory]
        if labels and name not in labels:
            line = str(span or "").rpartition(":")[2]
            found.append(
                {
                    "file": file_path,
                    "line": int(line) if line.isdigit() else None,
                    "name": name,
                    "lang": "go",
                    "reason": "undefined",
                }
            )
    return found


def _go_unimported(conn: Any, wanted: set[str] | None) -> list[dict[str, Any]]:
    # A selector call on a name no import, local or declaration in the package
    # explains: `strings.ToUpper()` with the import forgotten.
    rows = conn.execute(
        "SELECT file_path, json_extract(metadata_json, '$.go_unimported') FROM graph_nodes "
        "WHERE lang = 'go' AND uid LIKE 'code:module:%' AND file_path IS NOT NULL "
        "AND json_extract(metadata_json, '$.go_unimported') IS NOT NULL"
    ).fetchall()
    defined: dict[str, set[str]] = {}
    found = []
    for file_path, candidates in rows:
        if wanted is not None and file_path not in wanted:
            continue
        directory = PurePosixPath(str(file_path)).parent.as_posix()
        if directory not in defined:
            defined[directory] = _go_labels(conn, directory)
        for name, line in json.loads(candidates):
            if name not in defined[directory]:
                found.append(
                    {
                        "file": file_path,
                        "line": line,
                        "name": name,
                        "lang": "go",
                        "reason": "not_imported",
                    }
                )
    return found


def _go_labels(conn: Any, directory: str) -> set[str]:
    prefix = "" if directory == "." else f"{directory}/"
    return {
        str(label)
        for label, file_path in conn.execute(
            "SELECT label, file_path FROM graph_nodes WHERE lang = 'go' AND file_path LIKE ?",
            (f"{prefix}%",),
        ).fetchall()
        if PurePosixPath(str(file_path)).parent.as_posix() == directory
    }


def cos_graph_undefined(
    *,
    scope: str = "",
    top: int = 100,
    backend: str | None = None,
) -> dict[str, Any]:
    """List names the code uses but never defines or imports (a forgotten import)."""
    err = _validate_positive_int(top, "top")
    if err:
        return err
    top, _ = _clamp_int(top, min_v=1, max_v=1000)
    scope = scope.strip().strip("/").removeprefix("./")
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    conn = getattr(be, "_conn", None)
    if conn is None:
        return _fail("unavailable", "undefined-name scan requires the sqlite backend")
    found = [
        item
        for item in undefined_names(conn)
        if not scope or item["file"] == scope or item["file"].startswith(f"{scope}/")
    ]
    return _ok(
        {"undefined": found[:top], "total_count": len(found)},
        meta={
            "backend": be.backend_id,
            "scope": scope,
            "files": len({item["file"] for item in found}),
            "result_truncated": len(found) > top,
        },
    )
