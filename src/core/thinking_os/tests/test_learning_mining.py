"""Friction, commit and hook-block lesson mining — the signal-sourced half."""

from __future__ import annotations

import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from database import init_db
from tools._learning_mining import _mine_friction_lessons
from tools._learning_mining_logs import (
    _FIX_COMMIT_RE,
    _commit_subject_key,
    _mine_commit_lessons,
    _mine_hook_block_lessons,
)
from tools.learning import learn_extract


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = init_db(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture
def seeded_conn(conn: sqlite3.Connection) -> sqlite3.Connection:
    """DB with enough task outcomes to trigger pattern extraction."""
    for i in range(5):
        conn.execute(
            "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
            "VALUES (?, 'feat', 'BACKEND', 'COMPLICATED', ?)",
            (f"TASK-{i:03d}", "rework" if i < 4 else "success"),
        )
    conn.commit()
    return conn


class TestFrictionLessons:
    """The real learning signal: actionable lessons mined from recurring
    failure observations (hook BLOCKs, tool failures, completion gaps) —
    not aggregate success statistics. Contract: learning-extraction.md."""

    @staticmethod
    def _seed_failures(conn, n, narrative, memory_type="hook_block", session="ses-f", days_ago=0):
        created = f"datetime('now', '-{int(days_ago)} days')" if days_ago else "CURRENT_TIMESTAMP"
        for i in range(n):
            conn.execute(
                "INSERT INTO observations (session_id, tool_name, observation_type, "
                "memory_type, impact_score, title, narrative, content_hash, created_at) "
                f"VALUES (?, 'Edit', 'tool_failure', ?, 0.6, ?, ?, ?, {created})",
                (
                    session,
                    memory_type,
                    "[BLOCKED] Tool failure: Edit",
                    narrative,
                    f"h-{memory_type}-{session}-{i}",
                ),
            )
        conn.commit()

    def test_mines_lesson_from_recurring_block(self, seeded_conn: sqlite3.Connection) -> None:

        self._seed_failures(
            seeded_conn,
            3,
            "BLOCKED: editing src/core/x.py without the graph-explorer skill loaded",
        )
        lessons = _mine_friction_lessons(seeded_conn, min_occurrences=3)
        assert any(le["action"] in ("created", "updated") for le in lessons)
        rows = seeded_conn.execute(
            "SELECT pattern, source FROM learned_patterns WHERE memory_type='lesson'"
        ).fetchall()
        assert len(rows) >= 1
        assert rows[0]["source"] == "friction"
        assert "occurrences" in rows[0]["pattern"]

    def test_one_off_failure_not_minted(self, seeded_conn: sqlite3.Connection) -> None:

        self._seed_failures(seeded_conn, 1, "BLOCKED: a unique one-off thing", session="ses-one")
        lessons = _mine_friction_lessons(seeded_conn, min_occurrences=3)
        assert lessons == []  # floor=2 — a single occurrence never becomes a rule

    def test_re_mine_updates_not_duplicates(self, seeded_conn: sqlite3.Connection) -> None:

        self._seed_failures(
            seeded_conn, 2, "BLOCKED: write through symlink CLAUDE.md", session="ses-a"
        )
        _mine_friction_lessons(seeded_conn, min_occurrences=3)
        # one more occurrence of the SAME failure (count grows 2 -> 3)
        self._seed_failures(
            seeded_conn, 1, "BLOCKED: write through symlink CLAUDE.md", session="ses-b"
        )
        _mine_friction_lessons(seeded_conn, min_occurrences=3)
        rows = seeded_conn.execute(
            "SELECT pattern FROM learned_patterns WHERE memory_type='lesson'"
        ).fetchall()
        assert len(rows) == 1  # count-agnostic identity → single row, not a snapshot per run

    def test_learn_extract_includes_friction(self, seeded_conn: sqlite3.Connection) -> None:
        self._seed_failures(
            seeded_conn, 2, "BLOCKED: missing doc anchor for this session", session="ses-x"
        )
        learn_extract(seeded_conn, min_occurrences=3)
        lesson_count = seeded_conn.execute(
            "SELECT COUNT(*) FROM learned_patterns WHERE memory_type='lesson'"
        ).fetchone()[0]
        assert lesson_count >= 1

    def test_no_observations_no_lessons(self, seeded_conn: sqlite3.Connection) -> None:

        assert _mine_friction_lessons(seeded_conn, min_occurrences=3) == []

    def test_old_observations_age_out(self, seeded_conn: sqlite3.Connection) -> None:
        # failures older than the recency window must NOT be re-minted as lessons

        self._seed_failures(
            seeded_conn, 3, "BLOCKED: ancient resolved trap", session="ses-old", days_ago=120
        )
        assert _mine_friction_lessons(seeded_conn, min_occurrences=3) == []

    def test_noise_failures_not_minted(self, seeded_conn: sqlite3.Connection) -> None:
        # tool-fumbles + expected refusals are never lessons, even when recurring

        noise = (
            "EISDIR: illegal operation on a directory, read '/x/y/learning.py'",
            "File does not exist. Note: your current working directory is /x",
            "Refusing to write through symlink: /x/CLAUDE.md",
            "Output does not match required schema: StructuredOutput root must have 'area'",
            "Error executing tool cos_task_create: 1 validation error for cos_task_createArguments",
            "File content (31119 tokens) exceeds maximum allowed tokens (25000)",
            "Tool 'firecrawl_scrape' execution failed: Scrape aborted after exceeding retry limit",
            "MCP error -32602: Tool 'firecrawl_search' parameter validation failed",
        )
        for idx, narrative in enumerate(noise):
            self._seed_failures(
                seeded_conn, 3, narrative, memory_type="error", session=f"ses-n{idx}"
            )
        assert _mine_friction_lessons(seeded_conn, min_occurrences=3) == []

    def test_noise_in_title_filtered(self, seeded_conn: sqlite3.Connection) -> None:
        # StructuredOutput marks the TITLE; the narrative reads like a generic
        # schema error — must still be filtered (title is screened too).

        for i in range(3):
            seeded_conn.execute(
                "INSERT INTO observations (session_id, tool_name, observation_type, "
                "memory_type, impact_score, title, narrative, content_hash) "
                "VALUES (?, 'StructuredOutput', 'tool_failure', 'error', 0.6, ?, ?, ?)",
                (
                    "ses-so",
                    "Tool failure: StructuredOutput",
                    "Output does not match required schema: must have property 'fix'",
                    f"h-so-{i}",
                ),
            )
        seeded_conn.commit()
        assert _mine_friction_lessons(seeded_conn, min_occurrences=3) == []

    def test_lesson_carries_file_concept(self, seeded_conn: sqlite3.Connection) -> None:
        # friction lessons embed file:<basename> in concepts so JIT recall can
        # key on the source file (not basename-in-text, which never matched).

        for i in range(3):
            seeded_conn.execute(
                "INSERT INTO observations (session_id, tool_name, observation_type, memory_type, "
                "impact_score, title, narrative, content_hash, files_modified) "
                "VALUES ('ses-fc', 'Edit', 'tool_failure', 'error', 0.6, '[BLOCKED] Edit', "
                "'BLOCKED: editing core module without the required skill', ?, 'src/core/widget.py')",
                (f"hfc{i}",),
            )
        seeded_conn.commit()
        _mine_friction_lessons(seeded_conn, min_occurrences=3)
        concepts = " ".join(
            r[0] or ""
            for r in seeded_conn.execute(
                "SELECT concepts FROM learned_patterns WHERE memory_type='lesson'"
            ).fetchall()
        )
        assert "file:widget.py" in concepts


class TestCommitLessons:
    """The real engineering-lesson signal: fix:/revert: commit subjects mined
    from git history. Contract: learning-extraction.md §5."""

    @staticmethod
    def _git(repo: Path, *args: str) -> None:

        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)

    def _make_repo(self, tmp_path: Path) -> Path:
        repo = tmp_path / "proj"
        (repo / ".coding-os").mkdir(parents=True)
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.email", "t@t.t")
        self._git(repo, "config", "user.name", "t")
        return repo

    def test_fix_commit_regex(self) -> None:

        assert _FIX_COMMIT_RE.match("fix(cli): something")
        assert _FIX_COMMIT_RE.match("revert: bad change")
        assert _FIX_COMMIT_RE.match("fix!: breaking")
        assert not _FIX_COMMIT_RE.match("feat: a feature")
        assert not _FIX_COMMIT_RE.match("docs: update")

    def test_subject_key_normalises_ids(self) -> None:

        a = _commit_subject_key("repoint spec link for TASK-077 anchor")
        b = _commit_subject_key("repoint spec link for TASK-099 anchor")
        assert a == b  # TASK ids + digits normalised → same cluster

    def test_recurring_fix_minted_at_threshold(self, tmp_path: Path) -> None:

        repo = self._make_repo(tmp_path)
        for _ in range(3):  # >= _COMMIT_FIX_MIN_RECURRENCE → systemic-gap signal
            self._git(
                repo,
                "commit",
                "--allow-empty",
                "-q",
                "-m",
                "fix: handle null user in session lookup",
            )
        self._git(repo, "commit", "--allow-empty", "-q", "-m", "feat: unrelated change")
        c = init_db(repo / ".coding-os" / "coding-os.db")
        try:
            _mine_commit_lessons(c)
            rows = c.execute(
                "SELECT pattern FROM learned_patterns WHERE source='commit'"
            ).fetchall()
            assert rows and "Fixed repeatedly" in rows[0]["pattern"]
        finally:
            c.close()

    def test_one_off_fix_not_minted(self, tmp_path: Path) -> None:
        # a fix subject below the recurrence threshold is terse noise → dropped

        repo = self._make_repo(tmp_path)
        for _ in range(2):
            self._git(
                repo,
                "commit",
                "--allow-empty",
                "-q",
                "-m",
                "fix: a one-off thing that happened twice",
            )
        c = init_db(repo / ".coding-os" / "coding-os.db")
        try:
            assert _mine_commit_lessons(c) == []
        finally:
            c.close()

    def test_single_revert_minted(self, tmp_path: Path) -> None:

        repo = self._make_repo(tmp_path)
        self._git(
            repo, "commit", "--allow-empty", "-q", "-m", "revert: drop the broken cache layer"
        )
        c = init_db(repo / ".coding-os" / "coding-os.db")
        try:
            _mine_commit_lessons(c)  # a revert mints at any count
            rows = c.execute(
                "SELECT pattern FROM learned_patterns WHERE source='commit'"
            ).fetchall()
            assert rows and "Reverted before" in rows[0]["pattern"]
        finally:
            c.close()

    def test_no_git_repo_noop(self, conn: sqlite3.Connection) -> None:
        # conn's db is not under a .coding-os/ project root → no-op, no crash

        assert _mine_commit_lessons(conn) == []


class TestHookBlockLessons:
    """Hook BLOCKs never reach the observations table on Claude, but they ARE
    in the activity log. _mine_hook_block_lessons clusters recurring blocks
    (by hook + rule) into actionable lessons. Contract: learning-extraction.md."""

    @staticmethod
    def _write_log(path, lines):
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _block_line(hook, rule, *, days_ago=0):

        ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return f"[{ts}] [{hook}] [block] agent=claude session=s task=t rule={rule}"

    def test_mines_recurring_block(self, conn, tmp_path, monkeypatch):

        log = tmp_path / ".hooks.log"
        self._write_log(
            log, [self._block_line("enforce-skill", "graph-explorer") for _ in range(3)]
        )
        monkeypatch.setenv("COS_HOOK_LOG", str(log))
        lessons = _mine_hook_block_lessons(conn, min_occurrences=3)
        rows = conn.execute(
            "SELECT pattern FROM learned_patterns WHERE memory_type='lesson'"
        ).fetchall()
        assert lessons and rows
        assert "Recurring block" in rows[0]["pattern"]
        assert "enforce-skill" in rows[0]["pattern"]

    def test_one_off_block_not_minted(self, conn, tmp_path, monkeypatch):

        log = tmp_path / ".hooks.log"
        self._write_log(log, [self._block_line("enforce-skill", "only-once")])
        monkeypatch.setenv("COS_HOOK_LOG", str(log))
        assert _mine_hook_block_lessons(conn, min_occurrences=3) == []

    def test_old_blocks_ignored(self, conn, tmp_path, monkeypatch):

        log = tmp_path / ".hooks.log"
        self._write_log(
            log, [self._block_line("enforce-skill", "stale", days_ago=120) for _ in range(5)]
        )
        monkeypatch.setenv("COS_HOOK_LOG", str(log))
        assert _mine_hook_block_lessons(conn, min_occurrences=3) == []

    def test_missing_log_is_safe(self, conn, tmp_path, monkeypatch):

        monkeypatch.setenv("COS_HOOK_LOG", str(tmp_path / "does-not-exist.log"))
        monkeypatch.delenv("COS_HOOK_BLOCK_LOG", raising=False)
        assert _mine_hook_block_lessons(conn, min_occurrences=3) == []

    def test_mines_from_block_only_log_when_main_flooded(self, conn, tmp_path, monkeypatch):
        # The fix: the main log is flooded with non-block lines (blocks evicted),
        # but the block-only durable log retains them → still mined.

        main = tmp_path / ".hooks.log"
        self._write_log(
            main, ["[2026-06-08T10:00:00Z] [some-hook] [fire] agent=claude session=s task=t"] * 50
        )
        blk = tmp_path / ".hook-blocks.log"
        self._write_log(
            blk, [self._block_line("enforce-skill", "graph-explorer") for _ in range(3)]
        )
        monkeypatch.setenv("COS_HOOK_LOG", str(main))
        monkeypatch.setenv("COS_HOOK_BLOCK_LOG", str(blk))
        lessons = _mine_hook_block_lessons(conn, min_occurrences=3)
        assert lessons and "enforce-skill" in lessons[0]["pattern"]

    def test_mirrored_block_not_double_counted(self, conn, tmp_path, monkeypatch):
        # Every block is mirrored to BOTH logs. The miner reads ONE source (block
        # log preferred), so 3 real blocks count as 3 — never 6 from summing both.

        mirrored = [
            self._block_line("thinking_os-gate", "gate-not-recorded", days_ago=d) for d in (0, 1, 2)
        ]
        main = tmp_path / ".hooks.log"
        blk = tmp_path / ".hook-blocks.log"
        self._write_log(main, mirrored)  # same 3 lines in both logs
        self._write_log(blk, mirrored)
        monkeypatch.setenv("COS_HOOK_LOG", str(main))
        monkeypatch.setenv("COS_HOOK_BLOCK_LOG", str(blk))
        lessons = _mine_hook_block_lessons(conn, min_occurrences=3)
        assert lessons
        assert "3 occurrences" in lessons[0]["pattern"]  # 3, not 6 — single source
