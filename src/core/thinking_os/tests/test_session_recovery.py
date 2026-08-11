"""
Tests for session lifecycle hooks (TASK-156).

Covers session ID format, session-end summary write, DB-absent handling.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db


class TestOrphanSessionRecovery:
    """Covers the orphan-recovery path in session-context.sh — when a previous
    session accumulated observations but Stop never fired, the next startup
    must rebuild its session_summaries row from observations so no session is
    lost invisibly.
    """

    def test_rebuilds_summary_for_orphan(self, tmp_path: Path) -> None:
        """An orphan session (observations present, no summary row) gets a
        summary built with the correct observations_count."""
        from session_summary import build_session_summary

        db_path = tmp_path / "test.db"
        conn = init_db(db_path)

        orphan_id = "ses-20260401-120000-orph"
        # Insert 3 observations — simulates a session that edited files but
        # never had session-end.sh fire.
        for i in range(3):
            conn.execute(
                "INSERT INTO observations (session_id, tool_name, narrative, files_modified) "
                "VALUES (?, ?, ?, ?)",
                (orphan_id, "Edit", f"edit {i}", f"path/file_{i}.py"),
            )
        conn.commit()
        conn.close()

        # Confirm no summary row exists yet — this is the orphan condition.
        conn = sqlite3.connect(str(db_path))
        missing = conn.execute(
            "SELECT COUNT(*) FROM session_summaries WHERE session_id = ?",
            (orphan_id,),
        ).fetchone()[0]
        conn.close()
        assert missing == 0

        # Simulate what session-context.sh now does on startup.
        result = build_session_summary(session_id=orphan_id, db_path=str(db_path))
        assert result["status"] == "recorded"
        assert result["observations_count"] == 3

        # Summary row must now exist with accurate counts.
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM session_summaries WHERE session_id = ?",
            (orphan_id,),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["observations_count"] == 3

    def test_idempotent_when_summary_already_exists(self, tmp_path: Path) -> None:
        """Calling build_session_summary twice must not duplicate the row.
        Crucial because session-context.sh will call it on every startup —
        even after a clean Stop already ran session-end.sh."""
        from session_summary import build_session_summary

        db_path = tmp_path / "test.db"
        conn = init_db(db_path)
        sess_id = "ses-20260401-130000-idem"
        conn.execute(
            "INSERT INTO observations (session_id, tool_name, narrative, files_modified) "
            "VALUES (?, ?, ?, ?)",
            (sess_id, "Edit", "first edit", "file.py"),
        )
        conn.commit()
        conn.close()

        build_session_summary(session_id=sess_id, db_path=str(db_path))
        build_session_summary(session_id=sess_id, db_path=str(db_path))

        conn = sqlite3.connect(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM session_summaries WHERE session_id = ?",
            (sess_id,),
        ).fetchone()[0]
        conn.close()
        assert count == 1, "UPSERT must not duplicate rows"

    def test_empty_session_handled_gracefully(self, tmp_path: Path) -> None:
        """A session with zero observations should not crash — the startup
        path may see leftover COS_SESSION_FILE entries that never captured
        anything (e.g., user opened a chat and immediately closed it)."""
        from session_summary import build_session_summary

        db_path = tmp_path / "test.db"
        init_db(db_path).close()

        result = build_session_summary(
            session_id="ses-20260401-140000-empt",
            db_path=str(db_path),
        )
        assert result["status"] == "recorded"
        assert result["observations_count"] == 0


class TestSessionObserveWorker:
    def _db_with_changelog(self, tmp_path: Path, rows: list[tuple[str, str, float]]):
        conn = init_db(tmp_path / "test.db")
        conn.row_factory = sqlite3.Row
        conn.execute("INSERT INTO session_summaries (session_id) VALUES ('ses-w')")
        for tool, title, impact in rows:
            conn.execute(
                "INSERT INTO observations (session_id, tool_name, title, memory_type, impact_score) "
                "VALUES ('ses-w', ?, ?, 'changelog', ?)",
                (tool, title, impact),
            )
        conn.commit()
        return conn

    def _first_id(self, conn) -> int:
        return conn.execute("SELECT id FROM observations WHERE session_id='ses-w'").fetchone()[0]

    def _enrichment(self, obs_list, summary=None):
        from cognition_schemas import ObservationEnrichment, SessionEnrichment, SessionSummaryFacts

        return SessionEnrichment(
            observations=[ObservationEnrichment(**o) for o in obs_list],
            summary=summary or SessionSummaryFacts(),
        )

    def test_promotes_signal_rows(self, tmp_path: Path, monkeypatch) -> None:
        import session_observe_worker as w
        from cognition_schemas import SessionSummaryFacts

        conn = self._db_with_changelog(tmp_path, [("Edit", "Modified auth.py", 0.9)])
        oid = self._first_id(conn)
        enrich = self._enrichment(
            [
                {
                    "observation_id": oid,
                    "narrative": "hardened token refresh against replay",
                    "concepts": ["auth", "security"],
                    "has_signal": True,
                }
            ],
            SessionSummaryFacts(has_signal=True, learned="replay guard belongs at refresh"),
        )
        monkeypatch.setattr(w, "observe_session", lambda evidence: enrich)
        assert w.enrich_session(conn, "ses-w") == 1
        row = conn.execute(
            "SELECT memory_type, narrative, concepts FROM observations WHERE id=?", (oid,)
        ).fetchone()
        learned = conn.execute(
            "SELECT learned FROM session_summaries WHERE session_id='ses-w'"
        ).fetchone()[0]
        conn.close()
        assert row["memory_type"] == "discovery"
        assert "replay" in row["narrative"]
        assert "auth" in row["concepts"]
        assert learned == "replay guard belongs at refresh"

    def test_skips_no_signal_rows(self, tmp_path: Path, monkeypatch) -> None:
        import session_observe_worker as w

        conn = self._db_with_changelog(tmp_path, [("Edit", "reformatted file", 0.1)])
        oid = self._first_id(conn)
        enrich = self._enrichment([{"observation_id": oid, "narrative": "x", "has_signal": False}])
        monkeypatch.setattr(w, "observe_session", lambda evidence: enrich)
        assert w.enrich_session(conn, "ses-w") == 0
        mt = conn.execute("SELECT memory_type FROM observations WHERE id=?", (oid,)).fetchone()[0]
        conn.close()
        assert mt == "changelog"

    def test_redacts_secret_in_narrative(self, tmp_path: Path, monkeypatch) -> None:
        import session_observe_worker as w

        conn = self._db_with_changelog(tmp_path, [("Edit", "added client", 0.5)])
        oid = self._first_id(conn)
        enrich = self._enrichment(
            [
                {
                    "observation_id": oid,
                    # AWS's reserved documentation identifier — never valid.
                    "narrative": "wired client with AKIAIOSFODNN7EXAMPLE key",
                    "concepts": ["aws"],
                    "has_signal": True,
                }
            ]
        )
        monkeypatch.setattr(w, "observe_session", lambda evidence: enrich)
        w.enrich_session(conn, "ses-w")
        narrative = conn.execute(
            "SELECT narrative FROM observations WHERE id=?", (oid,)
        ).fetchone()[0]
        conn.close()
        assert "AKIAIOSFODNN7EXAMPLE" not in narrative
        assert "redacted" in narrative

    def test_ignores_hallucinated_observation_id(self, tmp_path: Path, monkeypatch) -> None:
        import session_observe_worker as w

        conn = self._db_with_changelog(tmp_path, [("Edit", "real row", 0.5)])
        oid = self._first_id(conn)
        enrich = self._enrichment(
            [{"observation_id": oid + 999, "narrative": "phantom", "has_signal": True}]
        )
        monkeypatch.setattr(w, "observe_session", lambda evidence: enrich)
        assert w.enrich_session(conn, "ses-w") == 0
        mt = conn.execute("SELECT memory_type FROM observations WHERE id=?", (oid,)).fetchone()[0]
        conn.close()
        assert mt == "changelog"

    def test_gate_off_returns_none_no_change(self, tmp_path: Path, monkeypatch) -> None:
        import session_observe_worker as w

        monkeypatch.delenv("COS_ENRICH_LLM", raising=False)  # default OFF
        conn = self._db_with_changelog(tmp_path, [("Edit", "row", 0.5)])
        # observe_session is the real one — gated off ⇒ returns None ⇒ no dispatch, no change.
        assert w.enrich_session(conn, "ses-w") == 0
        mt = conn.execute(
            "SELECT memory_type FROM observations WHERE session_id='ses-w'"
        ).fetchone()[0]
        conn.close()
        assert mt == "changelog"

    def test_idempotent_rerun(self, tmp_path: Path, monkeypatch) -> None:
        import session_observe_worker as w

        conn = self._db_with_changelog(tmp_path, [("Edit", "sig", 0.9)])
        oid = self._first_id(conn)
        enrich = self._enrichment(
            [
                {
                    "observation_id": oid,
                    "narrative": "did a real thing",
                    "concepts": ["x"],
                    "has_signal": True,
                }
            ]
        )
        monkeypatch.setattr(w, "observe_session", lambda evidence: enrich)
        assert w.enrich_session(conn, "ses-w") == 1
        assert w.enrich_session(conn, "ses-w") == 0  # promoted row left changelog — nothing to redo
        conn.close()

    def test_promote_clears_expires_at(self, tmp_path: Path, monkeypatch) -> None:
        import session_observe_worker as w

        conn = self._db_with_changelog(tmp_path, [("Edit", "sig", 0.9)])
        oid = self._first_id(conn)
        conn.execute(
            "UPDATE observations SET expires_at = '2099-01-01 00:00:00' WHERE id = ?", (oid,)
        )
        conn.commit()
        enrich = self._enrichment(
            [
                {
                    "observation_id": oid,
                    "narrative": "durable insight",
                    "concepts": ["x"],
                    "has_signal": True,
                }
            ]
        )
        monkeypatch.setattr(w, "observe_session", lambda evidence: enrich)
        w.enrich_session(conn, "ses-w")
        exp = conn.execute("SELECT expires_at FROM observations WHERE id = ?", (oid,)).fetchone()[0]
        conn.close()
        assert exp is None  # enriched discovery row is durable, off the changelog TTL
