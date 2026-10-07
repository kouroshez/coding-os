"""graph_os — SQLite backend: bind `self.m()`, `cls.m()` and `super().m()` to the base that defines `m`.

The extractor resolves a call on `self` or `cls` against the enclosing class
only; one naming an inherited method stays on a shared
`code:external:unresolved:self.m` (`cls.m`, `super.m`) stub, because the base
may live in another file. Once every file's `inherits_from` edges are linked,
the caller's class is walked in Python's method resolution order (C3, from the
linked bases in declaration order) and the first class that defines `m` gets a
call edge of its own; `super()` starts after the class, `self` and `cls` at it.
The stub edge is left as the extractor wrote it, so each run drops every edge
this pass made and derives them again: an override added to a base, or a method
removed, moves the call on the next `.py` edit anywhere.
"""

from __future__ import annotations

import time

from ._sqlite_connection import _SqliteConnectionBase

INHERITED_CONFIDENCE = 0.85
INHERITED_EXTRACTOR = "py_inherited@v1"
_STUB_PREFIX = "code:external:unresolved:"
_RECEIVERS = ("self", "cls", "super")
_MAX_CLASSES = 64
_MAX_NESTING = 4


class _SqlitePythonInheritLinkMixin(_SqliteConnectionBase):
    """Cross-file binding for calls that name an inherited method."""

    def link_python_inherited_calls(self, *, file_path: str | None = None) -> int:
        """Derive a call edge to the defining class for each inherited `self`/`cls`/`super` call; return how many."""
        if file_path is not None and not file_path.endswith(".py"):
            return 0
        with self._write_lock:
            self._conn.execute(
                "DELETE FROM graph_edges_v12 WHERE extractor = ?", (INHERITED_EXTRACTOR,)
            )
            orders: dict[int, list[int]] = {}
            now = int(time.time())
            derived = 0
            for caller_id, edge_type, span, receiver, name in self._inherited_call_rows():
                own = self._enclosing_class(caller_id)
                if own is None:
                    continue
                if own not in orders:
                    orders[own] = self._linearize(own, {}, frozenset())[:_MAX_CLASSES]
                order = orders[own][1:] if receiver == "super" else orders[own]
                target = self._first_definition(order, name)
                if target is None:
                    continue
                derived += self._conn.execute(
                    "INSERT OR IGNORE INTO graph_edges_v12 (source_id, target_id, edge_type, "
                    "confidence, extractor, source_span, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        caller_id,
                        target,
                        edge_type,
                        INHERITED_CONFIDENCE,
                        INHERITED_EXTRACTOR,
                        span,
                        now,
                        now,
                    ),
                ).rowcount
            self._conn.commit()
        return derived

    def _inherited_call_rows(self) -> list[tuple[int, str, str | None, str, str]]:
        rows = []
        for caller_id, edge_type, span, stub_uid in self._conn.execute(
            "SELECT e.source_id, e.edge_type, e.source_span, t.uid FROM graph_edges_v12 e "
            "JOIN graph_nodes t ON t.id = e.target_id "
            "WHERE t.uid >= ? AND t.uid < ? AND e.edge_type IN ('calls', 'awaits')",
            (_STUB_PREFIX, _STUB_PREFIX[:-1] + ";"),
        ):
            receiver, dot, name = str(stub_uid)[len(_STUB_PREFIX) :].partition(".")
            if receiver in _RECEIVERS and dot and name.isidentifier():
                rows.append((int(caller_id), str(edge_type), span, receiver, name))
        return rows

    def _first_definition(self, order: list[int], name: str) -> int | None:
        for class_id in order:
            method = self._conn.execute(
                "SELECT m.id FROM graph_edges_v12 e JOIN graph_nodes m ON m.id = e.target_id "
                "WHERE e.source_id = ? AND e.edge_type = 'contains' "
                "AND m.kind IN ('method', 'function') AND m.label = ? LIMIT 1",
                (class_id, name),
            ).fetchone()
            if method is not None:
                return int(method[0])
        return None

    def _linearize(
        self, class_id: int, memo: dict[int, list[int]], visiting: frozenset[int]
    ) -> list[int]:
        if class_id in memo:
            return memo[class_id]
        if class_id in visiting or len(visiting) >= _MAX_CLASSES:
            return [class_id]
        bases = self._bases(class_id)
        inner = visiting | {class_id}
        lines = [self._linearize(base, memo, inner) for base in bases]
        order = [class_id, *_c3_merge([*lines, bases])]
        memo[class_id] = order
        return order

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


def _c3_merge(sequences: list[list[int]]) -> list[int]:
    pending = [list(sequence) for sequence in sequences if sequence]
    merged: list[int] = []
    while pending:
        head = next(
            (
                sequence[0]
                for sequence in pending
                if not any(sequence[0] in other[1:] for other in pending)
            ),
            None,
        )
        if head is None:
            # Python refuses an inconsistent hierarchy; keep the rest in order.
            merged += [cls for sequence in pending for cls in sequence if cls not in merged]
            return merged
        merged.append(head)
        pending = [[cls for cls in sequence if cls != head] for sequence in pending]
        pending = [sequence for sequence in pending if sequence]
    return merged
