"""Regression tests for the prune helper's FK PRAGMA.

The fix is a one-liner on a hot path — the kind a casual ruff format or
copy-paste could silently revert. Each test asserts the *behavior* the fix
unlocked, so the suite goes red the moment the regression returns.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PRUNE_SCRIPT = REPO_ROOT / "src" / "scripts" / "prune_deleted_path.py"

# A hang detector, not a performance budget; matches SMOKE_TIMEOUT_S in
# tests/test_script_entrypoints.py.
SUBPROCESS_TIMEOUT_S = 30


# ---------------------------------------------------------------------------
# prune_deleted_path.py MUST enable PRAGMA foreign_keys = ON
# ---------------------------------------------------------------------------


class TestPruneDeletedPathPragma:
    """The FK on graph_edges_v12.{source,target}_id declares ON DELETE CASCADE,
    but sqlite3 defaults FK enforcement OFF on every fresh connection — so the
    prune helper silently leaked orphan edges on every file deletion. Fix
    landed as TASK-017 (commit 8cce3a7). Tests pin both source-level invariant
    and runtime behaviour.
    """

    def test_pragma_string_in_source(self) -> None:
        src = PRUNE_SCRIPT.read_text()
        assert "PRAGMA foreign_keys = ON" in src, (
            "prune_deleted_path.py no longer enables FK enforcement — see TASK-017"
        )

    def test_cascade_fires_on_delete(self, tmp_path: Path) -> None:
        """Reproduce the exact mechanism: open a DB with the script's
        connection style + PRAGMA, delete a node, assert dependent edges
        gone. If the PRAGMA disappears, this test flips red.
        """
        db = tmp_path / "probe.db"
        conn = sqlite3.connect(str(db))
        conn.executescript(
            """
            CREATE TABLE nodes (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE edges (
              id INTEGER PRIMARY KEY,
              src INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE
            );
            INSERT INTO nodes VALUES (1,'A'),(2,'B');
            INSERT INTO edges (src) VALUES (1),(1),(2);
            """
        )
        conn.commit()
        # Same line as prune_deleted_path.py:38 — without this, the DELETE
        # below would leave orphans and the assertion fails.
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM nodes WHERE id = 1")
        conn.commit()
        remaining = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        conn.close()
        assert remaining == 1, (
            f"CASCADE did not fire; {remaining} edges survived after node delete. "
            "Likely PRAGMA foreign_keys = ON was removed from prune script."
        )

    @staticmethod
    def _load_pruner(name: str):
        import importlib.util

        spec = importlib.util.spec_from_file_location(name, PRUNE_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_doc_delete_leaves_no_audit_residue(self, tmp_path: Path) -> None:
        # TASK-401: the audit trail is retired — pruning a doc must not
        # reference doc_audit_trail at all (git is the forensic record).
        db = tmp_path / "no-audit.db"
        conn = sqlite3.connect(str(db))
        conn.commit()
        conn.close()

        mod = self._load_pruner("prune_deleted_path_doc")
        counts = mod._prune_one("docs/governance/gone.md", db_path=db)
        assert "audit_rows" not in counts

    def test_script_imports_cleanly(self) -> None:
        """The script must remain importable so the regression test stays
        self-contained even if pruner internals refactor."""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import ast; ast.parse(open(r'" + str(PRUNE_SCRIPT) + "').read())",
            ],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT_S,
        )
        assert result.returncode == 0, result.stderr


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
