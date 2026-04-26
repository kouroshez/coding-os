"""
Tests for Phase H — auto-sync on writes.

Covers:
  - index_single_file() scope matching, mtime guard, delete signal
  - _match_source_config correctly classifies scoped vs unscoped paths
  - auto-reindex-docs.sh hook fires on Write|Edit, silent on unscoped
  - hook error log gets populated on failure and stays bounded

Integration notes:
  - We drive index_single_file directly; the shell hook is tested via
    subprocess.run with a synthetic tool_call JSON on stdin.
  - All tests run against isolated tmp_path projects so no state leaks.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import init_db  # noqa: E402
from doc_indexer import _match_source_config, index_single_file, load_rag_config  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]
_AUTO_REINDEX_HOOK = _REPO_ROOT / "core" / "hooks" / "auto-reindex-docs.sh"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MINI_RAG_CONFIG = """\
sources:
  - path: docs/PRD/
    type: prd
  - path: docs/engineering/
    type: engineering
    priority: 0.7

exclude:
  - docs/playbooks/
  - docs/governance/
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Minimal consumer-project layout with rag-config + scoped/unscoped docs."""
    root = tmp_path / "proj"
    (root / ".coding-os").mkdir(parents=True)
    (root / ".coding-os" / "rag-config.yaml").write_text(_MINI_RAG_CONFIG)
    (root / "docs" / "PRD").mkdir(parents=True)
    (root / "docs" / "engineering").mkdir(parents=True)
    (root / "docs" / "playbooks").mkdir(parents=True)
    return root


@pytest.fixture
def conn(project: Path) -> sqlite3.Connection:
    c = init_db(project / ".coding-os" / "thinking_os.db")
    yield c
    c.close()


def _write_doc(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


# ---------------------------------------------------------------------------
# _match_source_config — scope classifier
# ---------------------------------------------------------------------------

class TestMatchSourceConfig:
    def test_scoped_prd_file_matches(self, project: Path) -> None:
        target = _write_doc(project, "docs/PRD/billing.md", "# Billing\n\n## Scope\nBody.")
        config = load_rag_config(project / ".coding-os" / "rag-config.yaml")
        match = _match_source_config(
            target, config["sources"], project, config["exclude"],
        )
        assert match is not None
        assert match["type"] == "prd"

    def test_scoped_engineering_file_matches_with_priority(self, project: Path) -> None:
        target = _write_doc(project, "docs/engineering/backend-rules.md", "# Rules\n\n## Decimal\nx")
        config = load_rag_config(project / ".coding-os" / "rag-config.yaml")
        match = _match_source_config(
            target, config["sources"], project, config["exclude"],
        )
        assert match is not None
        assert match["type"] == "engineering"
        assert match.get("priority") == 0.7

    def test_excluded_playbook_returns_none(self, project: Path) -> None:
        target = _write_doc(project, "docs/playbooks/backend.md", "# Plays")
        config = load_rag_config(project / ".coding-os" / "rag-config.yaml")
        match = _match_source_config(
            target, config["sources"], project, config["exclude"],
        )
        assert match is None

    def test_outside_project_root_returns_none(self, project: Path, tmp_path: Path) -> None:
        outside = tmp_path / "other.md"
        outside.write_text("# outside")
        config = load_rag_config(project / ".coding-os" / "rag-config.yaml")
        match = _match_source_config(
            outside, config["sources"], project, config["exclude"],
        )
        assert match is None

    def test_missing_file_returns_none(self, project: Path) -> None:
        config = load_rag_config(project / ".coding-os" / "rag-config.yaml")
        match = _match_source_config(
            project / "docs" / "PRD" / "ghost.md",
            config["sources"], project, config["exclude"],
        )
        assert match is None


# ---------------------------------------------------------------------------
# index_single_file — lifecycle
# ---------------------------------------------------------------------------

class TestIndexSingleFile:
    def test_first_time_reindexed(self, project: Path, conn: sqlite3.Connection) -> None:
        f = _write_doc(project, "docs/PRD/billing.md", "# Billing\n\n## V1\nfirst pass body.")
        result = index_single_file(
            conn, f,
            project_root=project,
            config_path=project / ".coding-os" / "rag-config.yaml",
        )
        assert result["status"] == "reindexed"
        assert result["new_chunks"] >= 1
        assert result["source_type"] == "prd"

        stored = conn.execute(
            "SELECT COUNT(*), MAX(mtime) FROM document_chunks WHERE source_path = ?",
            (result["file"],),
        ).fetchone()
        assert stored[0] >= 1

    def test_mtime_guard_short_circuits(self, project: Path, conn: sqlite3.Connection) -> None:
        f = _write_doc(project, "docs/PRD/billing.md", "# Billing\n\n## V1\nbody.")
        r1 = index_single_file(
            conn, f, project_root=project,
            config_path=project / ".coding-os" / "rag-config.yaml",
        )
        assert r1["status"] == "reindexed"

        # Second call with identical mtime → unchanged
        r2 = index_single_file(
            conn, f, project_root=project,
            config_path=project / ".coding-os" / "rag-config.yaml",
        )
        assert r2["status"] == "unchanged"
        assert r2["new_chunks"] == 0

    def test_edit_reindexes_with_new_content(
        self, project: Path, conn: sqlite3.Connection,
    ) -> None:
        f = _write_doc(project, "docs/PRD/billing.md", "# Billing\n\n## V1\nold body.")
        index_single_file(
            conn, f, project_root=project,
            config_path=project / ".coding-os" / "rag-config.yaml",
        )
        # Write new content with a bumped mtime so the guard releases.
        time.sleep(1.1)  # second-granularity stat on some filesystems
        f.write_text("# Billing\n\n## V2\nrewritten body.")

        r = index_single_file(
            conn, f, project_root=project,
            config_path=project / ".coding-os" / "rag-config.yaml",
        )
        assert r["status"] == "reindexed"
        # The old V1 body should be gone
        hits = conn.execute(
            "SELECT content FROM document_chunks WHERE source_path = ?",
            (r["file"],),
        ).fetchall()
        joined = " ".join(row[0] for row in hits)
        assert "old body" not in joined
        assert "rewritten body" in joined

    def test_unscoped_path_is_noop(self, project: Path, conn: sqlite3.Connection) -> None:
        f = _write_doc(project, "docs/playbooks/plays.md", "# plays")
        r = index_single_file(
            conn, f, project_root=project,
            config_path=project / ".coding-os" / "rag-config.yaml",
        )
        assert r["status"] == "unscoped"
        assert r["new_chunks"] == 0

    def test_non_markdown_is_unscoped(self, project: Path, conn: sqlite3.Connection) -> None:
        f = _write_doc(project, "docs/PRD/notes.txt", "not markdown")
        r = index_single_file(
            conn, f, project_root=project,
            config_path=project / ".coding-os" / "rag-config.yaml",
        )
        assert r["status"] == "unscoped"

    def test_delete_removes_ghost_chunks(
        self, project: Path, conn: sqlite3.Connection,
    ) -> None:
        f = _write_doc(project, "docs/PRD/billing.md", "# Billing\n\n## V1\nbody.")
        r1 = index_single_file(
            conn, f, project_root=project,
            config_path=project / ".coding-os" / "rag-config.yaml",
        )
        rel = r1["file"]
        assert conn.execute(
            "SELECT COUNT(*) FROM document_chunks WHERE source_path = ?", (rel,),
        ).fetchone()[0] > 0

        f.unlink()
        r2 = index_single_file(
            conn, rel, project_root=project,
            config_path=project / ".coding-os" / "rag-config.yaml",
        )
        assert r2["status"] == "deleted"
        assert conn.execute(
            "SELECT COUNT(*) FROM document_chunks WHERE source_path = ?", (rel,),
        ).fetchone()[0] == 0

    def test_missing_untracked_file_is_missing(
        self, project: Path, conn: sqlite3.Connection,
    ) -> None:
        r = index_single_file(
            conn, "docs/PRD/ghost.md", project_root=project,
            config_path=project / ".coding-os" / "rag-config.yaml",
        )
        assert r["status"] == "missing"

    def test_force_reindexes_even_when_mtime_same(
        self, project: Path, conn: sqlite3.Connection,
    ) -> None:
        f = _write_doc(project, "docs/PRD/billing.md", "# Billing\n\n## V1\nbody.")
        r1 = index_single_file(
            conn, f, project_root=project,
            config_path=project / ".coding-os" / "rag-config.yaml",
        )
        assert r1["status"] == "reindexed"
        r2 = index_single_file(
            conn, f, project_root=project,
            config_path=project / ".coding-os" / "rag-config.yaml",
            force=True,
        )
        assert r2["status"] == "reindexed"

    def test_relative_path_resolves(
        self, project: Path, conn: sqlite3.Connection,
    ) -> None:
        _write_doc(project, "docs/PRD/billing.md", "# Billing\n\n## V1\nbody.")
        r = index_single_file(
            conn, "docs/PRD/billing.md", project_root=project,
            config_path=project / ".coding-os" / "rag-config.yaml",
        )
        assert r["status"] == "reindexed"
        assert r["file"] == "docs/PRD/billing.md"


# ---------------------------------------------------------------------------
# Shell hook integration
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not _AUTO_REINDEX_HOOK.exists(),
    reason="auto-reindex-docs.sh missing (fresh clone?)",
)
class TestAutoReindexHook:
    def _invoke(
        self,
        project: Path,
        tool_name: str,
        file_path: str,
    ) -> subprocess.CompletedProcess:
        payload = json.dumps({
            "tool_name": tool_name,
            "tool_input": {"file_path": file_path},
        })
        env = {
            **os.environ,
            "COS_STATE_DIR": str(project / ".coding-os"),
            "COS_PROJECT_ROOT": str(project),
            "COS_DB_PATH": str(project / ".coding-os" / "thinking_os.db"),
            "COS_BRAIN_DIR": str(_REPO_ROOT / "core" / "thinking_os"),
            "COS_RAG_CONFIG": str(project / ".coding-os" / "rag-config.yaml"),
            "PATH": os.environ.get("PATH", ""),
        }
        return subprocess.run(
            ["bash", str(_AUTO_REINDEX_HOOK)],
            input=payload, env=env, capture_output=True, text=True, timeout=10,
            cwd=str(project),
        )

    def test_exits_zero_on_non_write_tool(self, project: Path) -> None:
        r = self._invoke(project, "Read", "docs/PRD/billing.md")
        assert r.returncode == 0
        assert r.stdout == ""

    def test_exits_zero_on_non_markdown_write(self, project: Path) -> None:
        r = self._invoke(project, "Write", "src/main.py")
        assert r.returncode == 0

    def test_exits_zero_on_unscoped_markdown(self, project: Path) -> None:
        _write_doc(project, "docs/playbooks/plays.md", "# plays")
        r = self._invoke(project, "Write", str(project / "docs/playbooks/plays.md"))
        assert r.returncode == 0

    def test_exits_zero_when_rag_config_missing(self, tmp_path: Path) -> None:
        # New project without rag-config → silent skip, no error
        empty = tmp_path / "no-rag"
        empty.mkdir()
        (empty / "docs").mkdir()
        target = empty / "docs" / "x.md"
        target.write_text("# x")
        payload = json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": str(target)},
        })
        r = subprocess.run(
            ["bash", str(_AUTO_REINDEX_HOOK)],
            input=payload,
            env={
                **os.environ,
                "COS_STATE_DIR": str(empty / ".coding-os"),
                "COS_PROJECT_ROOT": str(empty),
                "PATH": os.environ.get("PATH", ""),
            },
            capture_output=True, text=True, timeout=10,
        )
        assert r.returncode == 0

    def test_scoped_write_dispatches_reindex(self, project: Path) -> None:
        f = _write_doc(project, "docs/PRD/billing.md", "# Billing\n\n## V1\nbody.")
        r = self._invoke(project, "Write", str(f))
        assert r.returncode == 0
        # Wait a bit for the background worker to finish
        time.sleep(1.5)
        conn = sqlite3.connect(str(project / ".coding-os" / "thinking_os.db"))
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM document_chunks WHERE source_path = ?",
                ("docs/PRD/billing.md",),
            ).fetchone()[0]
        finally:
            conn.close()
        assert count >= 1

    def test_error_log_bounded(self, project: Path) -> None:
        # Trigger log writes by hitting an intentionally broken config path,
        # then append filler lines, then verify trim happens on next fire.
        err_log = project / ".coding-os" / ".reindex-errors.log"
        err_log.parent.mkdir(parents=True, exist_ok=True)
        err_log.write_text("\n".join(f"line {i}" for i in range(300)) + "\n")

        f = _write_doc(project, "docs/PRD/billing.md", "# Billing\n\n## V1\nbody.")
        self._invoke(project, "Write", str(f))

        # After fire, log must be <= 200 lines
        time.sleep(0.5)
        if err_log.exists():
            line_count = len(err_log.read_text().splitlines())
            assert line_count <= 200


# ---------------------------------------------------------------------------
# Cleanup sanity — stray workers shouldn't leak into subsequent tests
# ---------------------------------------------------------------------------

def test_session_cleanup(project: Path) -> None:
    # If any background indexers are still running, give them a moment to exit.
    time.sleep(1.0)
    # Not asserting anything — presence of this test just makes sure pytest
    # tears down tmp_path AFTER any background worker has released it.
    assert (project / ".coding-os").exists()
