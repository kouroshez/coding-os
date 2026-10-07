"""graph_os — SQLite backend: bind `self.m()`, `cls.m()` and `super().m()` to the base that defines `m`.

The extractor resolves a call on `self` or `cls` against the enclosing class
only; one naming an inherited method stays on a shared
`code:external:unresolved:self.m` (`cls.m`, `super.m`) stub, because the base
may live in another file. Once every file's `inherits_from` edges are linked,
the caller's class is walked base by base — left to right, nearest first, a
breadth-first stand-in for the MRO — and the edge moves to the first class that
defines `m`; `super()` starts at the bases, `self` and `cls` at the class. The
stub is shared by every caller of that name, so the edge is rebound and the
stub left alone; a name no class in the chain defines keeps its stub.
"""

from __future__ import annotations

from ._sqlite_connection import _SqliteConnectionBase

INHERITED_CONFIDENCE = 0.85
_STUB_PREFIX = "code:external:unresolved:"
_RECEIVERS = ("self", "cls", "super")
_MAX_CLASSES = 64
_MAX_NESTING = 4


class _SqlitePythonInheritLinkMixin(_SqliteConnectionBase):
    """Cross-file binding for calls that name an inherited method."""

    def link_python_inherited_calls(self, *, file_path: str | None = None) -> int:
        """Rebind inherited `self`/`cls`/`super` calls to the defining class; return how many moved."""
        if file_path is not None and not file_path.endswith(".py"):
            return 0
        with self._write_lock:
            bound = 0
            for edge_id, caller_id, receiver, name in self._inherited_call_rows(file_path):
                target = self._inherited_method(caller_id, name, skip_own=receiver == "super")
                if target is None:
                    continue
                moved = self._conn.execute(
                    "UPDATE OR IGNORE graph_edges_v12 SET target_id = ?, confidence = ? "
                    "WHERE id = ?",
                    (target, INHERITED_CONFIDENCE, edge_id),
                ).rowcount
                if not moved:
                    # The caller already has this exact edge from another call site.
                    self._conn.execute("DELETE FROM graph_edges_v12 WHERE id = ?", (edge_id,))
                bound += 1
            self._conn.commit()
        return bound

    def _inherited_call_rows(self, file_path: str | None) -> list[tuple[int, int, str, str]]:
        sql = (
            "SELECT e.id, e.source_id, t.uid FROM graph_edges_v12 e "
            "JOIN graph_nodes t ON t.id = e.target_id "
            "JOIN graph_nodes s ON s.id = e.source_id "
            "WHERE t.uid >= ? AND t.uid < ? AND e.edge_type IN ('calls', 'awaits')"
        )
        params: tuple[str, ...] = (_STUB_PREFIX, _STUB_PREFIX[:-1] + ";")
        if file_path:
            sql += " AND s.file_path = ?"
            params += (file_path,)
        rows = []
        for edge_id, caller_id, stub_uid in self._conn.execute(sql, params):
            receiver, dot, name = str(stub_uid)[len(_STUB_PREFIX) :].partition(".")
            if receiver in _RECEIVERS and dot and name.isidentifier():
                rows.append((int(edge_id), int(caller_id), receiver, name))
        return rows

    def _inherited_method(self, caller_id: int, name: str, *, skip_own: bool) -> int | None:
        own = self._enclosing_class(caller_id)
        if own is None:
            return None
        queue = self._bases(own) if skip_own else [own]
        seen = set(queue)
        while queue and len(seen) <= _MAX_CLASSES:
            current = queue.pop(0)
            method = self._conn.execute(
                "SELECT m.id FROM graph_edges_v12 e JOIN graph_nodes m ON m.id = e.target_id "
                "WHERE e.source_id = ? AND e.edge_type = 'contains' "
                "AND m.kind IN ('method', 'function') AND m.label = ? LIMIT 1",
                (current, name),
            ).fetchone()
            if method is not None:
                return int(method[0])
            for base in self._bases(current):
                if base not in seen:
                    seen.add(base)
                    queue.append(base)
        return None

    def _enclosing_class(self, node_id: int) -> int | None:
        current = node_id
        for _ in range(_MAX_NESTING):
            parent = self._conn.execute(
                "SELECT p.id, p.kind FROM graph_edges_v12 e JOIN graph_nodes p ON p.id = e.source_id "
                "WHERE e.target_id = ? AND e.edge_type = 'contains' "
                "AND p.kind IN ('class', 'method', 'function') LIMIT 1",
                (current,),
            ).fetchone()
            if parent is None:
                return None
            if parent[1] == "class":
                return int(parent[0])
            current = int(parent[0])
        return None

    def _bases(self, class_id: int) -> list[int]:
        return [
            int(row[0])
            for row in self._conn.execute(
                "SELECT e.target_id FROM graph_edges_v12 e JOIN graph_nodes b ON b.id = e.target_id "
                "WHERE e.source_id = ? AND e.edge_type = 'inherits_from' AND b.kind = 'class' "
                "ORDER BY e.id",
                (class_id,),
            )
        ]
