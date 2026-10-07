"""npm and Python dependency gaps for cos_graph_undefined: an import no manifest declares, a dependency nothing imports.

A JS/TS file answers to its nearest package.json, plus the workspace root's
(hoisted) and every workspace package. Node built-ins, `astro:`/`virtual:`
modules and path aliases (`@/`, `~`, `#`) are no packages; an import resolved
into a workspace package's folder uses that package. Only runtime
`dependencies` can be unused — dev tooling runs from scripts and configs, which
import nothing — and a package used only by name (an Expo config plugin in
app.json, a CLI in a script) still reads unused. A Python import is third-party when it is neither the
standard library nor a repo module; its distribution must be declared in
pyproject.toml (names compared normalised: `python-dotenv` → `python_dotenv`).
A declared distribution is never called unused: its import name is a guess
in that direction, and plugins and CLIs import nothing.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any

_NODE_BUILTINS = frozenset(
    {
        "assert", "async_hooks", "buffer", "child_process", "cluster", "console", "constants",
        "crypto", "dgram", "diagnostics_channel", "dns", "domain", "events", "fs", "http",
        "http2", "https", "inspector", "module", "net", "os", "path", "perf_hooks", "process",
        "punycode", "querystring", "readline", "repl", "stream", "string_decoder", "sys",
        "timers", "tls", "trace_events", "tty", "url", "util", "v8", "vm", "wasi",
        "worker_threads", "zlib",
    }
)  # fmt: skip
# Distributions whose import name differs, beyond `-` → `_`.
_PYTHON_IMPORT_NAMES = {
    "pyyaml": "yaml",
    "python_dotenv": "dotenv",
    "beautifulsoup4": "bs4",
    "pillow": "PIL",
    "scikit_learn": "sklearn",
    "opencv_python": "cv2",
    "pyjwt": "jwt",
    "python_dateutil": "dateutil",
    "attrs": "attr",
    "protobuf": "google",
    "pymupdf": "fitz",
    "python_multipart": "multipart",
}


def dependency_gaps(conn: Any, wanted: set[str] | None) -> list[dict[str, Any]]:
    return _npm_gaps(conn, wanted) + _python_gaps(conn, wanted)


def _npm_gaps(conn: Any, wanted: set[str] | None) -> list[dict[str, Any]]:
    manifests = _npm_manifests(conn)
    if not manifests:
        return []
    # Workspace package name → its folder: an import resolved into that folder uses it.
    workspace = {
        str(uid)[len("npm:package:") :]: PurePosixPath(str(manifest)).parent.as_posix()
        for manifest, uid in conn.execute(
            "SELECT s.file_path, t.uid FROM graph_edges_v12 e "
            "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id "
            "WHERE e.edge_type = 'declares' AND t.uid LIKE 'npm:package:%' AND s.file_path IS NOT NULL"
        ).fetchall()
    }
    root = manifests.get(".", {})
    found: list[dict[str, Any]] = []
    used: dict[str, set[str]] = {directory: set() for directory in manifests}
    for file_path, target_path in conn.execute(
        "SELECT s.file_path, t.file_path FROM graph_edges_v12 e "
        "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id "
        "WHERE e.edge_type IN ('imports', 'imports_type') AND t.uid LIKE 'code:module:%' "
        "AND s.file_path IS NOT NULL AND t.file_path IS NOT NULL AND s.file_path != t.file_path"
    ).fetchall():
        for name, folder in workspace.items():
            if _under(str(target_path), folder) and not _under(str(file_path), folder):
                for directory in _ancestors(str(file_path), manifests):
                    used[directory].add(name)
    for file_path, specifier, span in conn.execute(
        "SELECT s.file_path, t.uid, e.source_span FROM graph_edges_v12 e "
        "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id "
        "WHERE e.edge_type IN ('imports', 'imports_type') AND t.uid LIKE 'code:module:npm:%' "
        "AND s.file_path IS NOT NULL"
    ).fetchall():
        package = _npm_package(str(specifier)[len("code:module:npm:") :])
        manifest = _nearest(str(file_path), manifests)
        if package is None or manifest is None:
            continue
        for directory in _ancestors(str(file_path), manifests):
            used[directory].add(package)
        declared = manifests[manifest].keys() | root.keys() | workspace.keys()
        if package not in declared and (wanted is None or file_path in wanted):
            found.append(_gap(str(file_path), span, package, "undeclared_dependency", "npm"))
    for directory, deps in manifests.items():
        manifest_file = "package.json" if directory == "." else f"{directory}/package.json"
        if wanted is not None and manifest_file not in wanted:
            continue
        for package, kind in deps.items():
            runtime = kind == "dependencies" and not package.startswith("@types/")
            if runtime and package not in used[directory]:
                found.append(_gap(manifest_file, None, package, "unused_dependency", "npm"))
    return found


def _npm_manifests(conn: Any) -> dict[str, dict[str, str]]:
    manifests: dict[str, dict[str, str]] = {}
    for file_path, uid, kind in conn.execute(
        "SELECT s.file_path, t.uid, ev.signal_name FROM graph_edges_v12 e "
        "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id "
        "JOIN graph_evidence_v12 ev ON ev.edge_id = e.id "
        "WHERE e.edge_type = 'imports' AND t.uid LIKE 'npm:package:%' "
        "AND s.file_path LIKE '%package.json'"
    ).fetchall():
        directory = PurePosixPath(str(file_path)).parent.as_posix()
        manifests.setdefault(directory, {})[str(uid)[len("npm:package:") :]] = str(kind)
    return manifests


def _npm_package(specifier: str) -> str | None:
    if specifier.startswith(("@/", "~", "#", "virtual:", ".", "/")):
        return None
    head = specifier.removeprefix("node:").split("/")[0].split(":")[0]
    if specifier.startswith("node:") or head in _NODE_BUILTINS:
        return None
    if specifier.startswith("@"):
        parts = specifier.split("/")
        return "/".join(parts[:2]) if len(parts) > 1 else None
    return head or None


def _python_gaps(conn: Any, wanted: set[str] | None) -> list[dict[str, Any]]:
    declared = {
        _python_import_name(str(row[0])[len("pypi:package:") :])
        for row in conn.execute(
            "SELECT DISTINCT t.uid FROM graph_edges_v12 e JOIN graph_nodes t ON t.id = e.target_id "
            "WHERE e.edge_type = 'imports' AND t.uid LIKE 'pypi:package:%'"
        ).fetchall()
    }
    if not declared:
        return []
    local = _python_roots(conn)
    found: list[dict[str, Any]] = []
    for file_path, uid, span in conn.execute(
        "SELECT s.file_path, t.uid, e.source_span FROM graph_edges_v12 e "
        "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id "
        "WHERE e.edge_type = 'imports' AND s.uid LIKE 'code:module:%' AND s.lang = 'py' "
        "AND t.uid LIKE 'code:module:%' AND t.file_path IS NULL"
    ).fetchall():
        top = str(uid)[len("code:module:") :].split(".")[0]
        third_party = top and not top.startswith("_") and top not in sys.stdlib_module_names
        undeclared = third_party and top not in local and top.lower() not in declared
        if undeclared and (wanted is None or file_path in wanted):
            found.append(_gap(str(file_path), span, top, "undeclared_dependency", "py"))
    return found


def _python_roots(conn: Any) -> set[str]:
    # Every name a path hack can make importable: each package directory and module stem.
    names: set[str] = set()
    for (file_path,) in conn.execute(
        "SELECT file_path FROM graph_nodes WHERE uid LIKE 'code:module:%' AND lang = 'py' "
        "AND file_path IS NOT NULL"
    ).fetchall():
        parts = PurePosixPath(str(file_path)).with_suffix("").parts
        names.update(part for part in parts if part != "__init__")
    return names


def _python_import_name(distribution: str) -> str:
    normalised = distribution.lower().replace("-", "_").replace(".", "_")
    return _PYTHON_IMPORT_NAMES.get(normalised, normalised).lower()


def _under(path: str, folder: str) -> bool:
    return folder == "." or path == folder or path.startswith(f"{folder}/")


def _nearest(file_path: str, manifests: dict[str, Any]) -> str | None:
    return next(iter(_ancestors(file_path, manifests)), None)


def _ancestors(file_path: str, manifests: dict[str, Any]) -> Iterable[str]:
    directory = PurePosixPath(file_path).parent
    while True:
        key = directory.as_posix()
        if key in manifests:
            yield key
        if key == ".":
            return
        directory = directory.parent


def _gap(file_path: str, span: Any, name: str, reason: str, lang: str) -> dict[str, Any]:
    line = str(span or "").rpartition(":")[2]
    return {
        "file": file_path,
        "line": int(line) if line.isdigit() else None,
        "name": name,
        "lang": lang,
        "reason": reason,
    }
