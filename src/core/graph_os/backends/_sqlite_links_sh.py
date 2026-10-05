"""graph_os — SQLite backend: bind shell function stubs to the library that defines them.

code_shell names a command its own file does not define `code:external:shfn:<name>`.
When exactly one real shell function carries that name — fallback no-op shims
excluded — the call binds to it; an external tool (`jq`, `git`) has no
definition and keeps its stub, which is how "which scripts use jq" is answered.
"""

from __future__ import annotations

import json

from ._sqlite_connection import _SqliteConnectionBase

SHELL_FUNCTION_PREFIX = "code:external:shfn:"
LINKED_CONFIDENCE = 0.7


class _SqliteShellLinkMixin(_SqliteConnectionBase):
    """Cross-file binding for shell functions defined in sourced libraries."""

    def link_shell_functions(self, *, file_path: str | None = None) -> int:
        """Bind `shfn` stubs to the one real definition; return the stubs bound."""
        with self._write_lock:
            bound = 0
            for stub_id, uid in self._shell_stub_rows(file_path):
                target_id = self._shell_function(str(uid)[len(SHELL_FUNCTION_PREFIX) :])
                if target_id is None:
                    continue
                self._conn.execute(
                    "UPDATE OR IGNORE graph_edges_v12 SET target_id = ?, "
                    "confidence = MAX(confidence, ?) WHERE target_id = ?",
                    (target_id, LINKED_CONFIDENCE, int(stub_id)),
                )
                bound += 1
            self._conn.commit()
        return bound

    def _shell_stub_rows(self, file_path: str | None) -> list[tuple[int, str]]:
        if file_path:
            return self._conn.execute(
                "SELECT DISTINCT stub.id, stub.uid FROM graph_edges_v12 e "
                "JOIN graph_nodes stub ON stub.id = e.target_id "
                "JOIN graph_nodes src ON src.id = e.source_id "
                "WHERE src.file_path = ? AND stub.uid LIKE 'code:external:shfn:%'",
                (file_path,),
            ).fetchall()
        return self._conn.execute(
            "SELECT id, uid FROM graph_nodes WHERE uid LIKE 'code:external:shfn:%'"
        ).fetchall()

    def _shell_function(self, name: str) -> int | None:
        rows = self._conn.execute(
            "SELECT id, metadata_json FROM graph_nodes "
            "WHERE kind = 'function' AND lang = 'sh' AND label = ?",
            (name,),
        ).fetchall()
        real = [int(row_id) for row_id, meta in rows if not _is_shim(meta)]
        return real[0] if len(real) == 1 else None


def _is_shim(metadata_json: str | None) -> bool:
    try:
        return bool(json.loads(metadata_json or "{}").get("fallback_shim"))
    except ValueError:
        return False
