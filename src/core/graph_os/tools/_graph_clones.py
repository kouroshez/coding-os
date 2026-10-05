"""Clone queries: cos_graph_duplicates and the clone tier of cos_graph_similar.

Private module of graph_os.tools.graph — import via the graph module,
never directly (the kernel imports this file at its bottom).

Reads the body fingerprints the extractors store on each declaration
(extractors/_fingerprint.py): equal `ast_hash` is a copy with renamed names and
constants, equal `content_hash` too is an exact copy. A file whose own
`content_hash` matches another file's is a byte-identical copy. Generated files
(ingest.base.is_generated) repeat by design and are left out of the report.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ..backend import BackendUnavailable
from ..test_paths import is_test_path
from . import graph as _kernel
from ._graph_envelope import _clamp_int, _fail, _ok, _validate_enum, _validate_positive_int
from ._graph_walk import NodeSummary

CLONE_TYPES = ("", "exact", "renamed")
DUPLICATED_FILE_SHARE = 0.5
MIN_SHARED_SYMBOLS = 2
EMPTY_FILE_HASH = "e3b0c44298fc1c14"

_MEMBER_COLUMNS = "uid, kind, label, file_path, start_line, end_line, ast_hash, content_hash"
_FINGERPRINTED = (
    "ast_hash IS NOT NULL AND content_hash IS NOT NULL AND file_path IS NOT NULL "
    "AND start_line IS NOT NULL AND end_line IS NOT NULL"
)


@dataclass(frozen=True)
class _Member:
    uid: str
    kind: str
    label: str
    file_path: str
    start_line: int
    end_line: int
    structure: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"uid": self.uid, "lines": [self.start_line, self.end_line]}


def _members(conn: Any, sql: str, args: Iterable[Any] = ()) -> list[_Member]:
    return [_Member(*row) for row in conn.execute(sql, tuple(args)).fetchall()]


def _clone_type(members: list[_Member]) -> str:
    return "exact" if len({member.text for member in members}) == 1 else "renamed"


def _in_scope(path: str, scope: str) -> bool:
    return not scope or path == scope or path.startswith(scope + "/")


def _repeated_members(conn: Any) -> list[_Member]:
    return _members(
        conn,
        f"SELECT {_MEMBER_COLUMNS} FROM graph_nodes WHERE {_FINGERPRINTED} AND ast_hash IN ("
        f"SELECT ast_hash FROM graph_nodes WHERE {_FINGERPRINTED} "
        "GROUP BY ast_hash HAVING COUNT(*) > 1)",
    )


def _groups(members: list[_Member], clone_type: str) -> list[list[_Member]]:
    by_structure: dict[str, list[_Member]] = defaultdict(list)
    for member in members:
        by_structure[member.structure].append(member)
    groups: list[list[_Member]] = []
    for group in by_structure.values():
        if clone_type == "exact":
            by_text: dict[str, list[_Member]] = defaultdict(list)
            for member in group:
                by_text[member.text].append(member)
            groups.extend(exact for exact in by_text.values() if len(exact) > 1)
        elif len(group) > 1 and (clone_type == "" or _clone_type(group) == "renamed"):
            groups.append(group)
    return groups


def _duplicated_lines(group: list[_Member]) -> int:
    return max(m.end_line - m.start_line + 1 for m in group) * (len(group) - 1)


def _drop_nested(groups: list[list[_Member]]) -> list[list[_Member]]:
    # A copied class repeats as a group per method; report the outermost copy.
    groups = sorted(groups, key=_duplicated_lines, reverse=True)
    spans: dict[str, list[tuple[int, int]]] = defaultdict(list)
    kept: list[list[_Member]] = []
    for group in groups:
        if all(_covered(member, spans[member.file_path]) for member in group):
            continue
        kept.append(group)
        for member in group:
            spans[member.file_path].append((member.start_line, member.end_line))
    return kept


def _covered(member: _Member, spans: list[tuple[int, int]]) -> bool:
    return any(
        start <= member.start_line
        and member.end_line <= end
        and (start, end) != (member.start_line, member.end_line)
        for start, end in spans
    )


def _duplicated_files(conn: Any, groups: list[list[_Member]]) -> list[dict[str, Any]]:
    shared: dict[tuple[str, str], int] = defaultdict(int)
    for group in groups:
        files = sorted({member.file_path for member in group})
        for index, first in enumerate(files):
            for second in files[index + 1 :]:
                shared[(first, second)] += 1
    if not shared:
        return []
    symbols = dict(
        conn.execute(
            f"SELECT file_path, COUNT(*) FROM graph_nodes WHERE {_FINGERPRINTED} GROUP BY file_path"
        ).fetchall()
    )
    pairs = []
    for (first, second), count in shared.items():
        share = (count / max(1, symbols.get(first, 0)), count / max(1, symbols.get(second, 0)))
        if count >= MIN_SHARED_SYMBOLS and max(share) >= DUPLICATED_FILE_SHARE:
            pairs.append(
                {
                    "files": [first, second],
                    "shared_symbols": count,
                    "share": [round(min(1.0, value), 2) for value in share],
                }
            )
    return sorted(pairs, key=lambda pair: (-pair["shared_symbols"], pair["files"]))


def _generated_files(conn: Any) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT file_path FROM graph_nodes WHERE uid LIKE 'code:file:%' "
            "AND json_extract(metadata_json, '$.generated') = 1"
        ).fetchall()
    }


def _identical_files(conn: Any) -> list[list[str]]:
    rows = conn.execute(
        "SELECT content_hash, file_path FROM graph_nodes "
        "WHERE uid LIKE 'code:file:%' AND content_hash IS NOT NULL AND content_hash != ? "
        "AND content_hash IN (SELECT content_hash FROM graph_nodes WHERE uid LIKE 'code:file:%' "
        "GROUP BY content_hash HAVING COUNT(*) > 1)",
        (EMPTY_FILE_HASH,),
    ).fetchall()
    by_hash: dict[str, list[str]] = defaultdict(list)
    for content_hash, file_path in rows:
        by_hash[content_hash].append(file_path)
    return sorted(sorted(files) for files in by_hash.values() if len(files) > 1)


def cos_graph_duplicates(
    *,
    scope: str = "",
    clone_type: str = "",
    include_tests: bool = False,
    top: int = 50,
    backend: str | None = None,
) -> dict[str, Any]:
    """List copy-pasted code: clone groups of symbols, duplicated files and identical files."""
    err: dict[str, Any] | None = _validate_positive_int(top, "top") or _validate_enum(
        clone_type, CLONE_TYPES, "clone_type"
    )
    if err:
        return err
    top, _ = _clamp_int(top, min_v=1, max_v=500)
    scope = scope.strip().strip("/").removeprefix("./")
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    conn = getattr(be, "_conn", None)
    if conn is None:
        return _fail("unavailable", "clone detection requires the sqlite backend")

    generated = _generated_files(conn)
    members = [
        member
        for member in _repeated_members(conn)
        if member.file_path not in generated
        and (include_tests or not is_test_path(member.file_path))
    ]
    groups = [
        group
        for group in _drop_nested(_groups(members, clone_type))
        if any(_in_scope(member.file_path, scope) for member in group)
    ]
    files = [
        pair
        for pair in _duplicated_files(conn, groups)
        if any(_in_scope(path, scope) for path in pair["files"])
    ]
    identical = [
        paths
        for paths in (
            [path for path in group if path not in generated] for group in _identical_files(conn)
        )
        if len(paths) > 1
        and any(_in_scope(path, scope) for path in paths)
        and (include_tests or not all(is_test_path(path) for path in paths))
    ]
    fingerprinted = conn.execute(
        f"SELECT COUNT(*) FROM graph_nodes WHERE {_FINGERPRINTED}"
    ).fetchone()[0]
    return _ok(
        {
            "groups": [
                {
                    "clone_type": _clone_type(group),
                    "duplicated_lines": _duplicated_lines(group),
                    "members": [member.to_dict() for member in group],
                }
                for group in groups[:top]
            ],
            "duplicated_files": files[:top],
            "identical_files": identical[:top],
            "total_count": len(groups),
        },
        meta={
            "backend": be.backend_id,
            "scope": scope,
            "clone_type": clone_type or "exact,renamed",
            "include_tests": include_tests,
            "fingerprinted_symbols": fingerprinted,
            "generated_files_skipped": len(generated),
            "duplicated_files_total": len(files),
            "identical_files_total": len(identical),
            "result_truncated": max(len(groups), len(files), len(identical)) > top,
        },
    )


def clone_twins(be: Any, root: Any) -> list[dict[str, Any]]:
    conn = getattr(be, "_conn", None)
    if conn is None:
        return []
    if root.uid.startswith("code:file:"):
        return _file_twins(be, conn, root)
    if not root.ast_hash or not root.content_hash:
        return []
    twins = _members(
        conn,
        f"SELECT {_MEMBER_COLUMNS} FROM graph_nodes WHERE {_FINGERPRINTED} "
        "AND ast_hash = ? AND uid != ?",
        (root.ast_hash, root.uid),
    )
    return [
        {
            "uid": twin.uid,
            "kind": twin.kind,
            "label": twin.label,
            "file_path": twin.file_path,
            "start_line": twin.start_line,
            "similarity": 1.0,
            "clone_type": "exact" if twin.text == root.content_hash else "renamed",
        }
        for twin in twins
    ]


def _file_twins(be: Any, conn: Any, root: Any) -> list[dict[str, Any]]:
    own = _members(
        conn,
        f"SELECT {_MEMBER_COLUMNS} FROM graph_nodes WHERE {_FINGERPRINTED} AND file_path = ?",
        (root.file_path,),
    )
    shared: dict[str, set[str]] = defaultdict(set)
    if own:
        hashes = sorted({member.structure for member in own})
        placeholders = ",".join("?" * len(hashes))
        for file_path, structure in conn.execute(
            f"SELECT file_path, ast_hash FROM graph_nodes WHERE {_FINGERPRINTED} "
            f"AND file_path != ? AND ast_hash IN ({placeholders})",
            (root.file_path, *hashes),
        ).fetchall():
            shared[file_path].add(structure)
    identical: set[str] = set()
    if root.content_hash and root.content_hash != EMPTY_FILE_HASH:
        identical = {
            row[0]
            for row in conn.execute(
                "SELECT file_path FROM graph_nodes WHERE uid LIKE 'code:file:%' "
                "AND content_hash = ? AND uid != ?",
                (root.content_hash, root.uid),
            ).fetchall()
        }
    nodes = be.get_nodes_bulk([f"code:file:{path}" for path in {*shared, *identical}])
    twins = []
    for uid, node in nodes.items():
        path = uid.removeprefix("code:file:")
        share = 1.0 if path in identical else len(shared[path]) / len({m.structure for m in own})
        twins.append(
            {
                **NodeSummary.from_node(node).to_dict(),
                "similarity": round(share, 4),
                "clone_type": "identical" if path in identical else "shared_symbols",
                "shared_symbols": len(shared[path]),
            }
        )
    return sorted(twins, key=lambda twin: (-twin["similarity"], twin["uid"]))
