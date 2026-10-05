"""Undefined names: cos_graph_undefined, and the list cos_graph_detect_changes reports.

Private module of graph_os.tools.graph — import via the graph module,
never directly (the kernel imports this file at its bottom).

Python and TS / JS files carry the names they use but never bind on their module
node (extractors/_undefined_names.py). Go needs the whole package, so it is read
here: a bare call the linker could not bind, to a name no file of that package
defines, is a function nobody wrote or a package nobody imported.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Any

from ..backend import BackendUnavailable
from . import graph as _kernel
from ._graph_envelope import _clamp_int, _fail, _ok, _validate_positive_int

_GO_STUB = "code:external:gopkg:"


def undefined_names(conn: Any, files: Sequence[str] | None = None) -> list[dict[str, Any]]:
    wanted = set(files) if files is not None else None
    found = _recorded(conn, wanted) + _go_unbound_calls(conn, wanted)
    return sorted(found, key=lambda item: (item["file"], item["line"] or 0, item["name"]))


def _recorded(conn: Any, wanted: set[str] | None) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT file_path, lang, metadata_json FROM graph_nodes WHERE uid LIKE 'code:module:%' "
        "AND file_path IS NOT NULL AND json_array_length(metadata_json, '$.undefined') > 0"
    ).fetchall()
    found = []
    for file_path, lang, metadata_json in rows:
        if wanted is not None and file_path not in wanted:
            continue
        for name, line in json.loads(metadata_json).get("undefined", []):
            found.append({"file": file_path, "line": line, "name": name, "lang": lang})
    return found


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
