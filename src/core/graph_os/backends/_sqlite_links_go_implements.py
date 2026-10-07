"""graph_os — SQLite backend: give a Go type an `implements` edge to each interface it satisfies.

Go satisfies interfaces structurally, so the edge is computed, not read: a
concrete type implements an in-repo interface when it has every method the
interface lists, by name, `[parameters, results]` arity and parameter and result
types (package qualifiers dropped, so `*domain.User` matches `*User`; not
compared when either side is generic). A type's methods are the ones it contains
(those declared in another file of its package included, once `link_go_symbols`
has hung them off the type) plus the ones its embedded types promote — `error`
too — at the shallowest depth; a name two embedded types promote at that depth
is ambiguous and left out, as the compiler leaves it. An interface adds the
methods of the interfaces it embeds. An interface embedding one the graph cannot
see (`io.Reader`), or a constraint (`~int | float64`), has an unknown method set
and is skipped rather than guessed. An interface with an unexported method only
takes types of its own package. Type names are compared as text, so the edge is
0.8.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from ._sqlite_connection import _SqliteConnectionBase

IMPLEMENTS_EXTRACTOR = "go_implements@v1"
IMPLEMENTS_CONFIDENCE = 0.8
_ERROR_SIGNATURE: tuple[tuple[int, int] | None, str | None] = ((0, 1), "->string")

Arity = tuple[int, int] | None
# A method's [parameters, results] arity and its `go_types` signature, either unknown.
Signature = tuple[Arity, str | None]
# Per method name: its signature and how deep in the embedding it was found.
MethodSet = dict[str, tuple[Signature, int]]


@dataclass
class _GoType:
    go_kind: str
    package: str = ""
    type_set: bool = False
    embeds_error: bool = False
    generic: bool = False
    methods: dict[str, Signature] = field(default_factory=dict)
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
            int(row_id): _GoType(
                str(go_kind or ""),
                PurePosixPath(str(file_path or "")).parent.as_posix(),
                bool(type_set),
                bool(embeds_error),
                bool(generic),
            )
            for row_id, file_path, go_kind, type_set, embeds_error, generic in self._conn.execute(
                "SELECT id, file_path, json_extract(metadata_json, '$.go_kind'), "
                "json_extract(metadata_json, '$.type_set'), "
                "json_extract(metadata_json, '$.embeds_error'), "
                "json_extract(metadata_json, '$.generic') "
                "FROM graph_nodes WHERE lang = 'go' AND kind = 'class'"
            )
        }
        for owner, label, arity, signature in self._conn.execute(
            "SELECT e.source_id, m.label, json_extract(m.metadata_json, '$.arity'), "
            "json_extract(m.metadata_json, '$.go_types') "
            "FROM graph_edges_v12 e JOIN graph_nodes m ON m.id = e.target_id "
            "WHERE e.edge_type = 'contains' AND m.kind = 'method' AND m.lang = 'go'"
        ):
            if int(owner) in types:
                parsed = json.loads(arity) if arity else None
                types[int(owner)].methods[str(label).rpartition(".")[2]] = (
                    (int(parsed[0]), int(parsed[1])) if parsed else None,
                    str(signature) if signature else None,
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
    memo: dict[int, MethodSet | None] = {}
    concrete = {
        type_id: {name: signature for name, (signature, _) in methods.items()}
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
        found = _method_set(iface_id, types, memo, frozenset())
        if not found:
            continue
        wanted = {name: signature for name, (signature, _) in found.items()}
        candidates = set.intersection(*(by_name.get(name, set()) for name in wanted))
        if any(name[:1].islower() for name in wanted):
            # An unexported method seals the interface to its own package.
            candidates = {c for c in candidates if types[c].package == go_type.package}
        pairs += [
            (type_id, iface_id)
            for type_id in sorted(candidates)
            if all(
                _compatible(
                    wanted[name],
                    concrete[type_id][name],
                    compare_types=not (go_type.generic or types[type_id].generic),
                )
                for name in wanted
            )
        ]
    return pairs


def _method_set(
    type_id: int,
    types: dict[int, _GoType],
    memo: dict[int, MethodSet | None],
    visiting: frozenset[int],
) -> MethodSet | None:
    # None marks an interface whose method set the graph cannot know.
    if type_id in memo:
        return memo[type_id]
    go_type = types[type_id]
    is_interface = go_type.go_kind == "interface"
    if is_interface and (go_type.type_set or go_type.embeds_unseen):
        memo[type_id] = None
        return None
    # name -> (signature, depth, how many embedded types reach it at that depth)
    promoted: dict[str, tuple[Signature, int, int]] = {}
    sources: list[MethodSet] = [{"Error": (_ERROR_SIGNATURE, 0)}] if go_type.embeds_error else []
    for embedded in go_type.embeds:
        if embedded in visiting:
            continue
        reached = _method_set(embedded, types, memo, visiting | {type_id})
        if reached is None and is_interface:
            memo[type_id] = None
            return None
        sources.append(reached or {})
    for source in sources:
        for name, (signature, depth) in source.items():
            seen = promoted.get(name)
            if seen is None or depth + 1 < seen[1]:
                promoted[name] = (signature, depth + 1, 1)
            elif depth + 1 == seen[1]:
                promoted[name] = (seen[0], seen[1], seen[2] + 1)
    methods: MethodSet = {
        name: (signature, depth)
        for name, (signature, depth, count) in promoted.items()
        # An interface may embed two that share a method; a struct's selector is ambiguous.
        if count == 1 or is_interface
    }
    methods.update({name: (signature, 0) for name, signature in go_type.methods.items()})
    memo[type_id] = methods
    return methods


def _compatible(wanted: Signature, found: Signature, *, compare_types: bool) -> bool:
    (wanted_arity, wanted_types), (found_arity, found_types) = wanted, found
    if wanted_arity is not None and found_arity is not None and wanted_arity != found_arity:
        return False
    return not (compare_types and wanted_types and found_types and wanted_types != found_types)
