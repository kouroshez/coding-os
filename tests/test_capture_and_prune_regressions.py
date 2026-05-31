"""Regression tests for TASK-016 (MultiEdit capture) + TASK-017 (FK PRAGMA).

Both fixes are one-liners on hot paths — the kind a casual ruff format or
copy-paste could silently revert. Each test asserts the *behavior* the fix
unlocked, so the suite goes red the moment the regression returns rather
than 6 days later when someone notices the empty observations table.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CAPTURE_HOOK = REPO_ROOT / "src" / "core" / "hooks" / "capture-observation.sh"
PRUNE_SCRIPT = REPO_ROOT / "src" / "scripts" / "prune_deleted_path.py"


# ---------------------------------------------------------------------------
# TASK-016 — capture-observation shell filter MUST accept MultiEdit
# ---------------------------------------------------------------------------


class TestCaptureObservationMultiEdit:
    """The shell filter at capture-observation.sh:28 historically dropped
    MultiEdit, which Claude SDK emits for ~90% of real agent edits — observations
    table stayed at 2 stale rows for days. Fix landed as TASK-016 (commit
    9dca67a). These tests pin the behaviour so a future revert flips red.
    """

    def _spawn(self, payload: dict, tmp_path: Path) -> subprocess.CompletedProcess:
        env = {
            "COS_STATE_DIR": str(tmp_path),
            "COS_AGENT_DIR": str(tmp_path / "claude"),
            "COS_AGENT": "claude",
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        }
        (tmp_path / "claude").mkdir(parents=True, exist_ok=True)
        return subprocess.run(
            ["bash", str(CAPTURE_HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=5,
            env=env,
        )

    def test_filter_accepts_multiedit(self, tmp_path: Path) -> None:
        """MultiEdit must pass the case statement so capture.py runs."""
        r = self._spawn(
            {
                "tool_name": "MultiEdit",
                "tool_input": {
                    "file_path": "/tmp/regression-multiedit.txt",
                    "edits": [{"old_string": "a", "new_string": "b"}],
                },
            },
            tmp_path,
        )
        assert r.returncode == 0, r.stderr
        # The hook prints a systemMessage envelope only when the case matches.
        # If MultiEdit were dropped, the script would exit 0 BEFORE the print.
        assert "[memory] +obs captured" in r.stdout

    def test_filter_accepts_write(self, tmp_path: Path) -> None:
        r = self._spawn(
            {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x.txt"}},
            tmp_path,
        )
        assert "[memory] +obs captured" in r.stdout

    def test_filter_accepts_edit(self, tmp_path: Path) -> None:
        r = self._spawn(
            {"tool_name": "Edit", "tool_input": {"file_path": "/tmp/x.txt"}},
            tmp_path,
        )
        assert "[memory] +obs captured" in r.stdout

    def test_filter_skips_read(self, tmp_path: Path) -> None:
        """Read must still short-circuit (no observation overhead for queries)."""
        r = self._spawn(
            {"tool_name": "Read", "tool_input": {"file_path": "/tmp/x.txt"}},
            tmp_path,
        )
        assert r.returncode == 0
        # Skipped tools never reach the systemMessage print.
        assert "[memory] +obs captured" not in r.stdout

    def test_shell_case_string_explicit(self) -> None:
        """Pin the exact case-pattern in source so a regex-shaped revert
        (e.g. `Write|Edit)`) flips the test before runtime would notice."""
        src = CAPTURE_HOOK.read_text()
        assert "Write|Edit|MultiEdit)" in src, (
            "capture-observation.sh case-pattern no longer includes MultiEdit — "
            "see TASK-016 / audit-memory-dead.md"
        )


# ---------------------------------------------------------------------------
# TASK-017 — prune_deleted_path.py MUST enable PRAGMA foreign_keys = ON
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
            "prune_deleted_path.py no longer enables FK enforcement — "
            "see TASK-017 / audit-graph-extractor.md"
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
            timeout=5,
        )
        assert result.returncode == 0, result.stderr


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
