"""graph_os — SQLite backend: give a Go type an `implements` edge to each interface it satisfies.

Go satisfies interfaces structurally, so the edge is computed, not read: a
concrete type implements an in-repo interface when it has every method the
interface lists, by name and `[parameters, results]` arity. A type's methods are
the ones it contains — those declared in another file of its package included,
once `link_go_symbols` has hung them off the type — plus the ones its embedded
types promote; an interface adds the methods of the interfaces it embeds. An
interface embedding one the graph cannot see (`io.Reader`), or a constraint
(`~int | float64`), has an unknown method set and is skipped rather than
guessed. Parameter and result types are not compared, so the edge is 0.8.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from ._sqlite_connection import _SqliteConnectionBase

IMPLEMENTS_EXTRACTOR = "go_implements@v1"
IMPLEMENTS_CONFIDENCE = 0.8
_ERROR_ARITY = (0, 1)

Arity = tuple[int, int] | None


@dataclass
class _GoType:
    go_kind: str
    type_set: bool = False
    embeds_error: bool = False
    methods: dict[str, Arity] = field(default_factory=dict)
    embeds: list[int] = field(default_factory=list)
    embeds_unseen: bool = False


class _SqliteGoImplementsMixin(_SqliteConnectionBase):
    """Structural interface satisfaction for Go."""

    def link_go_implements(self, *, file_path: str | None = None) -> int:
        """Recompute every Go `implements` edge; return how many there are."""
        if file_path is not None and not file_path.endswith(".go"):
            return 0
        with self._write_lock:
            pairs = _implementations(self._go_types())
            self._conn.execute(
                "DELETE FROM graph_edges_v12 WHERE extractor = ?", (IMPLEMENTS_EXTRACTOR,)
            )
            now = int(time.time())
            self._conn.executemany(
                "INSERT OR IGNORE INTO graph_edges_v12 (source_id, target_id, edge_type, "
                "confidence, extractor, source_span, created_at, updated_at) "
                "VALUES (?, ?, 'implements', ?, ?, NULL, ?, ?)",
                [
                    (source, target, IMPLEMENTS_CONFIDENCE, IMPLEMENTS_EXTRACTOR, now, now)
                    for source, target in pairs
                ],
            )
            self._conn.commit()
        return len(pairs)

    def _go_types(self) -> dict[int, _GoType]:
        types = {
            int(row_id): _GoType(str(go_kind or ""), bool(type_set), bool(embeds_error))
            for row_id, go_kind, type_set, embeds_error in self._conn.execute(
                "SELECT id, json_extract(metadata_json, '$.go_kind'), "
                "json_extract(metadata_json, '$.type_set'), "
                "json_extract(metadata_json, '$.embeds_error') "
                "FROM graph_nodes WHERE lang = 'go' AND kind = 'class'"
            )
        }
        for owner, label, arity in self._conn.execute(
            "SELECT e.source_id, m.label, json_extract(m.metadata_json, '$.arity') "
            "FROM graph_edges_v12 e JOIN graph_nodes m ON m.id = e.target_id "
            "WHERE e.edge_type = 'contains' AND m.kind = 'method' AND m.lang = 'go'"
        ):
            if int(owner) in types:
                parsed = json.loads(arity) if arity else None
                types[int(owner)].methods[str(label).rpartition(".")[2]] = (
                    (int(parsed[0]), int(parsed[1])) if parsed else None
                )
        for source, target in self._conn.execute(
            "SELECT e.source_id, e.target_id FROM graph_edges_v12 e "
            "JOIN graph_nodes s ON s.id = e.source_id "
            "WHERE e.edge_type = 'inherits_from' AND s.lang = 'go' AND s.kind = 'class'"
        ):
            owner = types[int(source)]
            if int(target) in types:
                owner.embeds.append(int(target))
            else:
                owner.embeds_unseen = True
        return types


def _implementations(types: dict[int, _GoType]) -> list[tuple[int, int]]:
    memo: dict[int, dict[str, Arity] | None] = {}
    concrete = {
        type_id: methods
        for type_id, go_type in types.items()
        if go_type.go_kind not in ("interface", "alias")
        and (methods := _method_set(type_id, types, memo, frozenset()))
    }
    by_name: dict[str, set[int]] = {}
    for type_id, methods in concrete.items():
        for name in methods:
            by_name.setdefault(name, set()).add(type_id)
    pairs: list[tuple[int, int]] = []
    for iface_id, go_type in types.items():
        if go_type.go_kind != "interface":
            continue
        wanted = _method_set(iface_id, types, memo, frozenset())
        if not wanted:
            continue
        candidates = set.intersection(*(by_name.get(name, set()) for name in wanted))
        pairs += [
            (type_id, iface_id)
            for type_id in sorted(candidates)
            if all(_same_arity(wanted[name], concrete[type_id][name]) for name in wanted)
        ]
    return pairs


def _method_set(
    type_id: int,
    types: dict[int, _GoType],
    memo: dict[int, dict[str, Arity] | None],
    visiting: frozenset[int],
) -> dict[str, Arity] | None:
    # None marks an interface whose method set the graph cannot know.
    if type_id in memo:
        return memo[type_id]
    go_type = types[type_id]
    is_interface = go_type.go_kind == "interface"
    if is_interface and (go_type.type_set or go_type.embeds_unseen):
        memo[type_id] = None
        return None
    methods: dict[str, Arity] = {"Error": _ERROR_ARITY} if go_type.embeds_error else {}
    for embedded in go_type.embeds:
        if embedded in visiting:
            continue
        promoted = _method_set(embedded, types, memo, visiting | {type_id})
        if promoted is None and is_interface:
            memo[type_id] = None
            return None
        for name, arity in (promoted or {}).items():
            methods.setdefault(name, arity)
    methods.update(go_type.methods)
    memo[type_id] = methods
    return methods


def _same_arity(wanted: Arity, found: Arity) -> bool:
    return wanted is None or found is None or wanted == found
