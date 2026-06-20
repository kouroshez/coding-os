"""record_outcome refines an optimistic 'success' into the honest 'rework' from
the task's OWN history (reopen via task_status_history, backtrack in the closing
session). That non-monotone signal is the only thing that un-suppresses the
variance-gated learning extractors — without it every outcome was 'success' and
learn_extract minted almost nothing (192 tasks → 4 patterns)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db  # noqa: E402
from record_outcome import (  # noqa: E402
    _derive_blocked,
    _derive_rework,
    _read_gate_file,
    _resolve_model,
    record_outcome,
)


def _reopen(db: Path, task_id: str) -> None:
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO task_status_history (task_id, old_status, new_status, transitioned_at) "
        "VALUES (?, 'testing', 'in_progress', 0)",
        (task_id,),
    )
    conn.commit()
    conn.close()


def _block(db: Path, task_id: str) -> None:
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO task_status_history (task_id, old_status, new_status, transitioned_at) "
        "VALUES (?, 'in_progress', 'blocked', 0)",
        (task_id,),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def db(tmp_path: Path) -> Path:
    p = tmp_path / ".coding-os" / "coding-os.db"
    p.parent.mkdir(parents=True)
    init_db(p).close()
    return p


class TestDeriveRework:
    """Scenario coverage: clean / reopened / backtracked / explicit-non-success /
    refine-disabled — across the CLI task-done and MCP completion personas (both
    route through record_outcome)."""

    def test_clean_task_stays_success(self, db: Path) -> None:
        r = record_outcome(task_id="TASK-1", task_type="feat", outcome="success", db_path=db)
        assert r["outcome"] == "success"

    def test_reopened_task_becomes_rework(self, db: Path) -> None:
        _reopen(db, "TASK-2")
        r = record_outcome(task_id="TASK-2", task_type="fix", outcome="success", db_path=db)
        assert r["outcome"] == "rework"

    def test_backtrack_does_not_smear_to_rework(
        self, db: Path, tmp_path: Path, monkeypatch
    ) -> None:
        # Regression: backtrack was dropped as a signal because it is session-
        # scoped with no task_id — a single backtrack in a high-fanout closing
        # session would smear EVERY task closed in that session to 'rework'. A
        # clean (non-reopened) task closed in a session that has a backtrack must
        # stay 'success'.
        sess = "ses-claude-test-smear"
        sfile = tmp_path / "session-id"
        sfile.write_text(sess)
        monkeypatch.setenv("COS_SESSION_FILE", str(sfile))
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO backtrack_events (session_id, from_formula, to_formula, reason) "
            "VALUES (?, 'a', 'b', 'redo')",
            (sess,),
        )
        conn.commit()
        conn.close()
        r = record_outcome(task_id="TASK-CLEAN", task_type="fix", outcome="success", db_path=db)
        assert r["outcome"] == "success"  # no smear — backtrack is not a rework signal

    def test_explicit_nonsuccess_not_overridden(self, db: Path) -> None:
        _reopen(db, "TASK-4")  # has reopen signal, but caller asserts 'blocked'
        r = record_outcome(task_id="TASK-4", task_type="fix", outcome="blocked", db_path=db)
        assert r["outcome"] == "blocked"  # refine only upgrades an optimistic 'success'

    def test_refine_disabled_keeps_success(self, db: Path) -> None:
        _reopen(db, "TASK-5")
        r = record_outcome(
            task_id="TASK-5", task_type="fix", outcome="success",
            refine_from_history=False, db_path=db,
        )
        assert r["outcome"] == "success"

    def test_derive_helper_false_on_clean(self, db: Path) -> None:
        conn = sqlite3.connect(str(db))
        try:
            assert _derive_rework(conn, "UNKNOWN-TASK") is False
        finally:
            conn.close()


class TestDeriveBlocked:
    """The blocked emit path: a task that entered 'blocked' before completing is
    recorded 'blocked' (not the hardcoded 'success'); blocked outranks rework."""

    def test_blocked_history_becomes_blocked(self, db: Path) -> None:
        _block(db, "TASK-B1")
        r = record_outcome(task_id="TASK-B1", task_type="feat", outcome="success", db_path=db)
        assert r["outcome"] == "blocked"

    def test_blocked_outranks_rework(self, db: Path) -> None:
        _block(db, "TASK-B2")
        _reopen(db, "TASK-B2")  # both signals present
        r = record_outcome(task_id="TASK-B2", task_type="fix", outcome="success", db_path=db)
        assert r["outcome"] == "blocked"  # stronger friction marker wins

    def test_clean_task_not_blocked(self, db: Path) -> None:
        r = record_outcome(task_id="TASK-B3", task_type="feat", outcome="success", db_path=db)
        assert r["outcome"] == "success"

    def test_explicit_partial_not_overridden(self, db: Path) -> None:
        _block(db, "TASK-B4")  # has blocked signal, but caller asserts 'partial'
        r = record_outcome(task_id="TASK-B4", task_type="fix", outcome="partial", db_path=db)
        assert r["outcome"] == "partial"  # refine only upgrades an optimistic 'success'

    def test_derive_blocked_false_on_clean(self, db: Path) -> None:
        conn = sqlite3.connect(str(db))
        try:
            assert _derive_blocked(conn, "UNKNOWN-TASK") is False
        finally:
            conn.close()


class TestModelAndGateCapture:
    """The MCP server has no COS_PANEL_DIR/COS_AGENT_DIR but knows COS_AGENT, so
    model + complexity must resolve from <state>/<agent>/ — the same agent-subdir
    path skills_used already used. Before B-4, model was NULL + complexity UNKNOWN
    on every MCP-driven completion, starving the multi-model routing loop (F16)."""

    @staticmethod
    def _emulate_mcp_server(monkeypatch, state_dir: Path) -> None:
        monkeypatch.setenv("COS_STATE_DIR", str(state_dir))
        monkeypatch.setenv("COS_AGENT", "claude")
        for var in ("COS_AGENT_MODEL", "ANTHROPIC_MODEL", "COS_AGENT_DIR", "COS_PANEL_DIR"):
            monkeypatch.delenv(var, raising=False)

    def test_resolve_model_from_agent_subdir(self, tmp_path: Path, monkeypatch) -> None:
        (tmp_path / "claude").mkdir()
        (tmp_path / "claude" / ".model").write_text("claude-opus-4-8", encoding="utf-8")
        self._emulate_mcp_server(monkeypatch, tmp_path)
        assert _resolve_model() == "claude-opus-4-8"  # was None pre-fix

    def test_read_gate_from_agent_subdir_strips_ppid_prefix(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        (tmp_path / "claude").mkdir()
        # ppid- prefix (no session-id yet) — the old parser read it AS the level
        (tmp_path / "claude" / ".thinking_os-gate").write_text(
            "ppid-abc123 COMPLICATED 3", encoding="utf-8"
        )
        self._emulate_mcp_server(monkeypatch, tmp_path)
        assert _read_gate_file() == ("COMPLICATED", 3)  # was ("ppid-abc123", …) pre-fix

    def test_record_outcome_captures_model_and_complexity_end_to_end(
        self, db: Path, tmp_path: Path, monkeypatch
    ) -> None:
        state = db.parent  # <tmp>/.coding-os
        (state / "claude").mkdir(parents=True, exist_ok=True)
        (state / "claude" / ".model").write_text("claude-opus-4-8", encoding="utf-8")
        (state / "claude" / ".thinking_os-gate").write_text(
            "ses-x COMPLEX 5", encoding="utf-8"
        )
        self._emulate_mcp_server(monkeypatch, state)

        record_outcome(task_id="TASK-9", task_type="feat", outcome="success", db_path=db)

        conn = sqlite3.connect(str(db))
        try:
            row = conn.execute(
                "SELECT model, complexity, dimensions FROM task_outcomes WHERE task_id='TASK-9'"
            ).fetchone()
        finally:
            conn.close()
        assert row == ("claude-opus-4-8", "COMPLEX", 5)  # both were NULL/UNKNOWN pre-fix

    def test_read_gate_from_panel_subdir(self, tmp_path: Path, monkeypatch) -> None:
        """Production routes the gate to <state>/<agent>/panels/<id>/ — one level
        below the flat search; _newest_panel_gate must reach it (pass-3 review)."""
        panel = tmp_path / "claude" / "panels" / "p1"
        panel.mkdir(parents=True)
        (panel / ".thinking_os-gate").write_text("ses-x COMPLICATED 4", encoding="utf-8")
        self._emulate_mcp_server(monkeypatch, tmp_path)
        assert _read_gate_file() == ("COMPLICATED", 4)  # was UNKNOWN pre-fix

    def test_read_gate_strips_bare_uuid_prefix(self, tmp_path: Path, monkeypatch) -> None:
        """A bare-UUID session prefix (CLAUDE_CODE_SESSION_ID) matches no known
        prefix; skip any leading non-level token so it is not read as the level."""
        (tmp_path / "claude").mkdir()
        (tmp_path / "claude" / ".thinking_os-gate").write_text(
            "3f2a9c10-7b4e-4d21-9a8c-0e1f2a3b4c5d COMPLEX 6", encoding="utf-8"
        )
        self._emulate_mcp_server(monkeypatch, tmp_path)
        assert _read_gate_file() == ("COMPLEX", 6)  # was ('3f2a9c10-...', ...) pre-fix
