"""graph_os — SQLite backend: compose FastAPI route paths across files.

A FastAPI route's path is its router's prefix, plus the prefix of every
`include_router` above it, plus the decorator's own path — and those usually sit
in three files: the routes module, a shared `router = APIRouter(prefix=...)`
module it imports, and the app that includes it. Contracts records each file's
routers, mounts and raw route paths; this pass follows the Python imports to
the router each name means, composes the chain, and renames each route node to
its full path. It recomputes every route each run — a prefix edit in one file
moves routes in others.

A Fiber route whose router is a parameter is provisional (`...@<file>`) and
names its owner function and parameter; the `passes_router` edges into that
owner — bound to it by `link_go_symbols` — carry each caller's prefix, or the
caller's own parameter when its prefix comes from further up. The route is
renamed to the first composed path; any other mount is listed on it.
"""

from __future__ import annotations

import json
from typing import Any

from ._sqlite_connection import _SqliteConnectionBase

MAX_IMPORT_HOPS = 4
MAX_MOUNT_DEPTH = 8
MAX_PASS_DEPTH = 4

_Router = tuple[str, str]
# callee uid → (caller uid, argument position, prefix, caller's own parameter)
_Passes = dict[str, list[tuple[str, int, str, int | None]]]


class _SqliteRouteLinkMixin(_SqliteConnectionBase):
    """Cross-file composition of FastAPI route paths."""

    def link_fastapi_routes(self) -> int:
        """Rename FastAPI route nodes to their full composed path; return the routes moved."""
        with self._write_lock:
            routers = self._file_metadata("fastapi_routers")
            if not routers:
                return 0
            resolver = _Resolver(self._conn, routers)
            parents: dict[_Router, tuple[_Router, str]] = {}
            for file_path, mounts in self._file_metadata("fastapi_mounts").items():
                for parent, child, prefix, _line in mounts:
                    resolved_parent = resolver.router(file_path, str(parent))
                    resolved_child = resolver.router(file_path, str(child))
                    if resolved_parent and resolved_child and resolved_parent != resolved_child:
                        parents.setdefault(resolved_child, (resolved_parent, str(prefix)))
            moved = 0
            for node_id, uid, file_path, metadata in self._fastapi_routes():
                router = resolver.router(file_path, str(metadata.get("router") or ""))
                if router is None or "route_path" not in metadata:
                    if metadata.get("provisional"):
                        # No router declaration reachable: the path stays relative.
                        self._mark_unresolved(node_id, metadata)
                    continue
                prefix = _base(router, parents, routers) + routers[router[0]][router[1]]
                moved += self._rename_route(node_id, uid, _path(prefix, metadata), metadata)
            self._conn.commit()
        return moved

    def link_fiber_routes(self) -> int:
        """Rename Fiber routes whose router another file passes in to their full path; return the routes moved."""
        with self._write_lock:
            passes = self._router_passes()
            moved = 0
            for node_id, uid, metadata in self._parameter_routes():
                route_path = str(metadata.get("route_path") or "")
                owner, parameter = str(metadata["router_owner"]), int(metadata["router_param"])
                prefixes = sorted(set(_caller_prefixes(owner, parameter, passes, 0)))
                if not prefixes:
                    continue
                full = [_fiber_join(prefix, route_path) for prefix in prefixes]
                extra = {"also_mounted_at": full[1:]} if len(full) > 1 else {}
                moved += self._rename_route(node_id, uid, full[0], {**metadata, **extra})
            self._conn.commit()
        return moved

    def _router_passes(self) -> _Passes:
        passes: _Passes = {}
        for caller, callee, note in self._conn.execute(
            "SELECT s.uid, t.uid, ev.note FROM graph_edges_v12 e "
            "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id "
            "JOIN graph_evidence_v12 ev ON ev.edge_id = e.id "
            "WHERE e.edge_type = 'passes_router' AND ev.signal_name = 'fiber_router_pass'"
        ).fetchall():
            data = json.loads(note or "{}")
            param = data.get("param")
            passes.setdefault(str(callee), []).append(
                (
                    str(caller),
                    int(data.get("index", -1)),
                    str(data.get("prefix") or ""),
                    None if param is None else int(param),
                )
            )
        return passes

    def _parameter_routes(self) -> list[tuple[int, str, dict[str, Any]]]:
        rows = self._conn.execute(
            "SELECT id, uid, metadata_json FROM graph_nodes WHERE kind = 'route' "
            "AND json_extract(metadata_json, '$.framework') = 'fiber' "
            "AND json_extract(metadata_json, '$.router_owner') IS NOT NULL"
        ).fetchall()
        return [(int(row[0]), str(row[1]), json.loads(row[2] or "{}")) for row in rows]

    def _file_metadata(self, key: str) -> dict[str, Any]:
        rows = self._conn.execute(
            "SELECT file_path, json_extract(metadata_json, ?) FROM graph_nodes "
            "WHERE uid LIKE 'code:file:%' AND json_extract(metadata_json, ?) IS NOT NULL",
            (f"$.{key}", f"$.{key}"),
        ).fetchall()
        return {str(file_path): json.loads(value) for file_path, value in rows}

    def _fastapi_routes(self) -> list[tuple[int, str, str, dict[str, Any]]]:
        rows = self._conn.execute(
            "SELECT id, uid, file_path, metadata_json FROM graph_nodes WHERE kind = 'route' "
            "AND json_extract(metadata_json, '$.framework') = 'fastapi' AND file_path IS NOT NULL"
        ).fetchall()
        return [(int(row[0]), str(row[1]), str(row[2]), json.loads(row[3] or "{}")) for row in rows]

    def _mark_unresolved(self, node_id: int, metadata: dict[str, Any]) -> None:
        if metadata.get("prefix") != "unresolved":
            self._conn.execute(
                "UPDATE graph_nodes SET metadata_json = ? WHERE id = ?",
                (json.dumps({**metadata, "prefix": "unresolved"}), node_id),
            )

    def _rename_route(self, node_id: int, uid: str, full: str, metadata: dict[str, Any]) -> int:
        method = str(metadata.get("method") or "")
        websocket = metadata.get("kind") == "websocket"
        new_uid = f"cos:route:ws:{full}" if websocket else f"cos:route:{method.upper()}:{full}"
        if new_uid == uid:
            return 0
        # Another registration already owns that path: keep both rather than merge.
        if self._conn.execute("SELECT 1 FROM graph_nodes WHERE uid = ?", (new_uid,)).fetchone():
            return 0
        label = f"fastapi:{full}" if websocket else f"{method.upper()} {full}"
        composed = {key: value for key, value in metadata.items() if key != "prefix"}
        self._conn.execute(
            "UPDATE graph_nodes SET uid = ?, label = ?, metadata_json = ? WHERE id = ?",
            (new_uid, label, json.dumps({**composed, "path": full}), node_id),
        )
        return 1


class _Resolver:
    def __init__(self, conn: Any, routers: dict[str, dict[str, str]]) -> None:
        self._conn = conn
        self._routers = routers
        self._imports: dict[str, dict[str, tuple[str, str]]] = {}
        self._modules: dict[str, str | None] = {}

    def router(self, file_path: str, expression: str) -> _Router | None:
        head, _, attribute = expression.partition(".")
        if attribute:
            module_file = self._imported_module(file_path, head)
            return self._named(module_file, attribute, 0) if module_file else None
        return self._named(file_path, head, 0)

    def _named(self, file_path: str, name: str, hops: int) -> _Router | None:
        if name in self._routers.get(file_path, {}):
            return file_path, name
        imported = self._file_imports(file_path).get(name)
        if imported is None or hops >= MAX_IMPORT_HOPS:
            return None
        module, original = imported
        module_file = self._module_file(module)
        return self._named(module_file, original, hops + 1) if module_file else None

    def _imported_module(self, file_path: str, alias: str) -> str | None:
        imported = self._file_imports(file_path).get(alias)
        if imported is None:
            return None
        module, original = imported
        # `from app.routers import users` names a module; `import app.users` a path.
        return self._module_file(f"{module}.{original}") or self._module_file(module)

    def _file_imports(self, file_path: str) -> dict[str, tuple[str, str]]:
        if file_path not in self._imports:
            rows = self._conn.execute(
                "SELECT uid, metadata_json FROM graph_nodes WHERE kind = 'import_' "
                "AND file_path = ?",
                (file_path,),
            ).fetchall()
            table: dict[str, tuple[str, str]] = {}
            for uid, metadata_json in rows:
                metadata = json.loads(metadata_json or "{}")
                module = str(metadata.get("resolved_module") or "")
                if module:
                    local = str(uid).rpartition("::")[2]
                    table[local] = (module, str(metadata.get("imported") or ""))
            self._imports[file_path] = table
        return self._imports[file_path]

    def _module_file(self, dotted: str) -> str | None:
        if dotted not in self._modules:
            row = self._conn.execute(
                "SELECT file_path FROM graph_nodes WHERE uid = ? AND file_path IS NOT NULL",
                (f"code:module:{dotted}",),
            ).fetchone()
            self._modules[dotted] = str(row[0]) if row else None
        return self._modules[dotted]


def _base(
    router: _Router,
    parents: dict[_Router, tuple[_Router, str]],
    routers: dict[str, dict[str, str]],
) -> str:
    segments: list[str] = []
    current = router
    for _ in range(MAX_MOUNT_DEPTH):
        if current not in parents:
            break
        parent, prefix = parents[current]
        segments.append(routers[parent[0]][parent[1]] + prefix)
        current = parent
    return "".join(reversed(segments))


def _path(prefix: str, metadata: dict[str, Any]) -> str:
    joined = prefix + str(metadata.get("route_path") or "")
    return joined if joined.startswith("/") else f"/{joined}"


def _caller_prefixes(owner: str, parameter: int, passes: _Passes, depth: int) -> list[str]:
    found: list[str] = []
    for caller, index, prefix, caller_parameter in passes.get(owner, []):
        if index != parameter:
            continue
        if caller_parameter is None:
            found.append(prefix)
        elif depth < MAX_PASS_DEPTH:
            outer = _caller_prefixes(caller, caller_parameter, passes, depth + 1)
            found += [_fiber_join(above, prefix) for above in outer]
    return found


def _fiber_join(*parts: str) -> str:
    joined = "/".join(part.strip("/") for part in parts if part.strip("/"))
    return f"/{joined}"
