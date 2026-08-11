"""
Tests for session lifecycle hooks (TASK-156).

Covers session ID format, session-end summary write, DB-absent handling.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db


class TestSessionIdFormat:
    def test_format_pattern(self) -> None:
        """Session ID should match ses-YYYYMMDD-HHMMSS-XXXX."""
        # Simulate what the hook generates
        result = subprocess.run(
            [
                "bash",
                "-c",
                'echo "ses-$(date +%Y%m%d-%H%M%S)-$(head -c 4 /dev/urandom | xxd -p | head -c 4)"',
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        session_id = result.stdout.strip()
        assert re.match(r"ses-\d{8}-\d{6}-[a-f0-9]{4}", session_id)

    def test_unique_ids(self) -> None:
        """Two generated IDs should differ."""
        ids = set()
        for _ in range(5):
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    'echo "ses-$(date +%Y%m%d-%H%M%S)-$(head -c 4 /dev/urandom | xxd -p | head -c 4)"',
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            ids.add(result.stdout.strip())
        # At least some should be unique (suffix randomness)
        assert len(ids) >= 2


class TestSessionContextHook:
    def test_hook_syntax(self) -> None:
        """session-context.sh should have valid bash syntax."""
        hooks_dir = Path(__file__).resolve().parent.parent.parent / "hooks"
        result = subprocess.run(
            ["bash", "-n", str(hooks_dir / "session-context.sh")],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0

    def test_session_end_syntax(self) -> None:
        """session-end.sh should have valid bash syntax."""
        hooks_dir = Path(__file__).resolve().parent.parent.parent / "hooks"
        result = subprocess.run(
            ["bash", "-n", str(hooks_dir / "session-end.sh")],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0


class TestApplySessionFacts:
    def _db_with_summary(self, tmp_path: Path):
        conn = init_db(tmp_path / "test.db")
        conn.execute("INSERT INTO session_summaries (session_id) VALUES ('ses-d')")
        conn.commit()
        return conn

    def test_fills_on_signal(self, tmp_path: Path) -> None:
        from cognition_schemas import SessionSummaryFacts
        from session_enrich import apply_session_facts

        conn = self._db_with_summary(tmp_path)
        facts = SessionSummaryFacts(
            has_signal=True,
            learned="chose X over Y because Z",
            investigated="session_enrich write path",
            next_steps="wire the observer worker",
        )
        assert apply_session_facts(conn, "ses-d", facts) is True
        row = conn.execute(
            "SELECT investigated, learned, next_steps FROM session_summaries WHERE session_id = 'ses-d'"
        ).fetchone()
        conn.close()
        assert row[0] == "session_enrich write path"
        assert row[1] == "chose X over Y because Z"
        assert row[2] == "wire the observer worker"

    def test_gated_when_no_signal(self, tmp_path: Path) -> None:
        from cognition_schemas import SessionSummaryFacts
        from session_enrich import apply_session_facts

        conn = self._db_with_summary(tmp_path)
        assert (
            apply_session_facts(conn, "ses-d", SessionSummaryFacts(has_signal=False, learned="x"))
            is False
        )
        row = conn.execute(
            "SELECT learned FROM session_summaries WHERE session_id = 'ses-d'"
        ).fetchone()
        conn.close()
        assert row[0] is None

    def test_gated_when_learned_blank(self, tmp_path: Path) -> None:
        from cognition_schemas import SessionSummaryFacts
        from session_enrich import apply_session_facts

        conn = self._db_with_summary(tmp_path)
        assert (
            apply_session_facts(conn, "ses-d", SessionSummaryFacts(has_signal=True, learned="   "))
            is False
        )
        row = conn.execute(
            "SELECT learned FROM session_summaries WHERE session_id = 'ses-d'"
        ).fetchone()
        conn.close()
        assert row[0] is None

    def test_coalesce_first_write_wins(self, tmp_path: Path) -> None:
        from cognition_schemas import SessionSummaryFacts
        from session_enrich import apply_session_facts

        conn = self._db_with_summary(tmp_path)
        conn.execute("UPDATE session_summaries SET learned = 'original' WHERE session_id = 'ses-d'")
        conn.commit()
        apply_session_facts(conn, "ses-d", SessionSummaryFacts(has_signal=True, learned="newer"))
        row = conn.execute(
            "SELECT learned FROM session_summaries WHERE session_id = 'ses-d'"
        ).fetchone()
        conn.close()
        assert row[0] == "original"

    def test_missing_row_is_noop(self, tmp_path: Path) -> None:
        from cognition_schemas import SessionSummaryFacts
        from session_enrich import apply_session_facts

        conn = init_db(tmp_path / "test.db")
        result = apply_session_facts(
            conn, "ses-absent", SessionSummaryFacts(has_signal=True, learned="x")
        )
        conn.close()
        assert result is False
