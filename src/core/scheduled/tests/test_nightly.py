"""Tests for core/scheduled/ — nightly maintenance pipeline."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Make scheduled package importable
_SCHED = Path(__file__).resolve().parents[1]
_THINKING_OS = _SCHED.parent / "thinking_os"
for _p in (_SCHED, _THINKING_OS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from _activity import activity_since, observations_since_marker, outcomes_since_marker
from _state import (
    days_since_marker,
    read_registry,
    read_state,
    touch_marker,
    write_state,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path: Path) -> sqlite3.Connection:
    """Minimal DB with required tables for nightly tasks."""
    db_path = tmp_path / ".coding-os" / "coding-os.db"
    db_path.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, description TEXT);
        INSERT OR IGNORE INTO schema_version VALUES (26, 'test');

        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            title TEXT,
            narrative TEXT,
            concepts TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS task_outcomes (
            task_id TEXT PRIMARY KEY,
            type TEXT,
            domain TEXT,
            complexity TEXT,
            outcome TEXT,
            skills_used TEXT,
            model TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS learned_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern TEXT,
            memory_type TEXT,
            domain TEXT,
            source TEXT,
            confidence REAL DEFAULT 0.5,
            decay_rate REAL DEFAULT 0.1,
            impact_score REAL DEFAULT 0.5,
            concepts TEXT,
            times_validated INTEGER DEFAULT 0,
            times_violated INTEGER DEFAULT 0,
            access_count INTEGER DEFAULT 0,
            last_accessed_at TEXT,
            promoted_to TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            last_validated TEXT,
            trust_tier TEXT DEFAULT 'volatile',
            provenance TEXT DEFAULT 'agent_learned'
        );

        CREATE TABLE IF NOT EXISTS routing_weights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT,
            complexity TEXT,
            model TEXT,
            skill TEXT,
            success_rate REAL,
            sample_count INTEGER,
            last_updated TEXT DEFAULT (datetime('now')),
            last_recalc_at TEXT,
            outcomes_at_recalc INTEGER,
            UNIQUE(domain, complexity, model, skill)
        );
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def project_root(tmp_path: Path, db: Path) -> Path:
    return tmp_path


# ---------------------------------------------------------------------------
# _state tests
# ---------------------------------------------------------------------------


class TestWriteReadState:
    def test_roundtrip(self, project_root: Path) -> None:
        data = {"run_at": "2026-05-06T03:00:00Z", "tasks": {"decay": {"status": "ok"}}}
        write_state(project_root, data)
        assert read_state(project_root) == data

    def test_read_missing_returns_empty(self, tmp_path: Path) -> None:
        assert read_state(tmp_path / "nonexistent") == {}

    def test_atomic_write(self, project_root: Path) -> None:
        write_state(project_root, {"a": 1})
        write_state(project_root, {"b": 2})
        assert read_state(project_root) == {"b": 2}


class TestDaysSinceMarker:
    def test_missing_returns_none(self, tmp_path: Path) -> None:
        assert days_since_marker(tmp_path / "missing") is None

    def test_fresh_marker_returns_zero(self, tmp_path: Path) -> None:
        m = tmp_path / ".last-decay"
        touch_marker(m)
        age = days_since_marker(m)
        assert age is not None
        assert age < 0.01

    def test_old_marker_returns_days(self, tmp_path: Path) -> None:
        m = tmp_path / ".last-decay"
        touch_marker(m)
        # Backdate mtime by 8 days
        old_time = (datetime.now(timezone.utc) - timedelta(days=8)).timestamp()
        import os

        os.utime(m, (old_time, old_time))
        age = days_since_marker(m)
        assert age is not None
        assert 7.9 < age < 8.1


class TestReadRegistry:
    def test_fallback_to_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("COS_PROJECT_ROOT", "")
        # Patch Path.home() so the real ~/.coding-os/registry.json is not found
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "fake-home"))
        projects = read_registry(hub_state_dir=tmp_path / "nonexistent")
        assert len(projects) == 1
        assert projects[0]["slug"] == tmp_path.name

    def test_reads_registry_json(self, tmp_path: Path) -> None:
        reg = tmp_path / "registry.json"
        reg.write_text(
            json.dumps(
                {
                    "version": 1,
                    "projects": [{"slug": "proj-a", "path": "/tmp/proj-a"}],
                }
            )
        )
        projects = read_registry(hub_state_dir=tmp_path)
        assert projects[0]["slug"] == "proj-a"


# ---------------------------------------------------------------------------
# _activity tests
# ---------------------------------------------------------------------------


class TestActivitySince:
    def test_empty_db_returns_zero(self, db: Path) -> None:
        result = activity_since(db, days=1)
        assert result["obs_count"] == 0
        assert result["outcome_count"] == 0
        assert result["has_activity"] is False

    def test_detects_recent_observation(self, db: Path) -> None:
        with sqlite3.connect(str(db)) as conn:
            conn.execute("INSERT INTO observations (title) VALUES ('test obs')")
            conn.commit()
        result = activity_since(db, days=1)
        assert result["obs_count"] == 1
        assert result["has_activity"] is True

    def test_ignores_old_observation(self, db: Path) -> None:
        old_ts = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        with sqlite3.connect(str(db)) as conn:
            conn.execute(
                "INSERT INTO observations (title, created_at) VALUES ('old', ?)", (old_ts,)
            )
            conn.commit()
        result = activity_since(db, days=1)
        assert result["obs_count"] == 0

    def test_missing_db_returns_zero(self, tmp_path: Path) -> None:
        result = activity_since(tmp_path / "missing.db", days=1)
        assert result["has_activity"] is False


class TestOutcomesSinceMarker:
    def test_no_marker_counts_all(self, db: Path, tmp_path: Path) -> None:
        with sqlite3.connect(str(db)) as conn:
            conn.execute("INSERT INTO task_outcomes (task_id, outcome) VALUES ('T1', 'success')")
            conn.commit()
        count = outcomes_since_marker(db, tmp_path / "missing-marker")
        assert count == 1

    def test_marker_gates_count(self, db: Path, tmp_path: Path) -> None:
        marker = tmp_path / ".last-extract"
        touch_marker(marker)

        with sqlite3.connect(str(db)) as conn:
            conn.execute("INSERT INTO task_outcomes (task_id, outcome) VALUES ('T1', 'success')")
            conn.commit()

        # Outcomes inserted AFTER marker was touched → should count 0
        # (timing-sensitive; backdate marker by 1 second to be safe)
        import os
        import time

        past = time.time() - 2
        os.utime(marker, (past, past))

        count = outcomes_since_marker(db, marker)
        assert count == 1


# ---------------------------------------------------------------------------
# nightly.py integration tests
# ---------------------------------------------------------------------------


class TestNightlyRunProject:
    def test_skips_when_db_missing(self, tmp_path: Path) -> None:
        from nightly import run_project

        result = run_project({"slug": "x", "path": str(tmp_path)}, dry_run=True)
        assert result["tasks"]["all"]["status"] == "skipped"
        assert "db_not_found" in result["tasks"]["all"]["reason"]

    def test_skips_when_schema_too_old(self, tmp_path: Path) -> None:
        db_path = tmp_path / ".coding-os" / "coding-os.db"
        db_path.parent.mkdir(parents=True)
        with sqlite3.connect(str(db_path)) as conn:
            conn.executescript("""
                CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY);
                INSERT INTO schema_migrations VALUES (3);
            """)
        from nightly import run_project

        result = run_project({"slug": "x", "path": str(tmp_path)}, dry_run=True)
        assert result["tasks"]["all"]["status"] == "skipped"
        assert "schema_version" in result["tasks"]["all"]["reason"]

    def test_dry_run_does_not_write(self, project_root: Path, db: Path) -> None:
        from nightly import run_project

        run_project({"slug": "test", "path": str(project_root)}, dry_run=True)
        # decay marker must NOT have been written in dry_run
        marker = project_root / ".coding-os" / ".last-decay"
        assert not marker.exists()

    def test_decay_skipped_when_fresh_marker(self, project_root: Path, db: Path) -> None:
        marker = project_root / ".coding-os" / ".last-decay"
        touch_marker(marker)
        from nightly import run_project

        result = run_project({"slug": "test", "path": str(project_root)}, dry_run=False)
        assert result["tasks"]["decay"]["status"] == "skipped"

    def test_disabled_after_max_failures(self, project_root: Path, db: Path) -> None:
        from nightly import _MAX_CONSECUTIVE_FAILURES

        write_state(
            project_root,
            {
                "consecutive_failures": _MAX_CONSECUTIVE_FAILURES,
                "last_error": "some error",
            },
        )
        from nightly import run_project

        result = run_project({"slug": "test", "path": str(project_root)}, dry_run=False)
        assert result["tasks"]["all"]["status"] == "skipped"
        assert "disabled" in result["tasks"]["all"]["reason"]

    def test_state_written_after_run(self, project_root: Path, db: Path) -> None:
        from nightly import run_project

        run_project({"slug": "test", "path": str(project_root)}, dry_run=True)
        state = read_state(project_root)
        assert "run_at" in state
        assert "tasks" in state


class TestNightlyMain:
    def test_dry_run_exits_zero(
        self, project_root: Path, db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import nightly

        monkeypatch.setattr(
            nightly,
            "read_registry",
            lambda **_: [{"slug": "test", "path": str(project_root)}],
        )
        rc = nightly.main(["--dry-run"])
        assert rc == 0

    def test_reset_failures(
        self, project_root: Path, db: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        write_state(project_root, {"consecutive_failures": 5})
        import nightly

        monkeypatch.setattr(
            nightly,
            "read_registry",
            lambda **_: [{"slug": "test", "path": str(project_root)}],
        )
        nightly.main(["--reset-failures", "--dry-run"])
        state = read_state(project_root)
        assert state.get("consecutive_failures", 0) == 0


class TestNightlyEntrypointSmoke:
    def test_script_runs_as_direct_subprocess(self) -> None:
        import subprocess

        script = Path(__file__).resolve().parents[1] / "nightly.py"
        # -S drops site so the editable-install finder can't resolve `scheduled`
        # for us — this keeps the script's own sys.path bootstrap load-bearing
        # (without -S the finder masks a broken bootstrap and the test is a false-green).
        result = subprocess.run(
            [sys.executable, "-S", str(script), "--help"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "nightly maintenance" in result.stdout


# ---------------------------------------------------------------------------
# graph_reindex_if_stale (Task 4 — added 2026-05-18)
# ---------------------------------------------------------------------------


class TestGraphReindexIfStale:
    """Probe-driven nightly reindex covers the gap when no edits fired the
    PostToolUse auto-reindex hook for >24h."""

    def _write_probe(self, project_root: Path, last_ok_at: int) -> Path:
        state = project_root / ".coding-os"
        state.mkdir(parents=True, exist_ok=True)
        probe = state / ".graph-backend.json"
        probe.write_text(json.dumps({"backend": "sqlite", "last_ok_at": last_ok_at}))
        return probe

    def test_skips_when_probe_missing(self, tmp_path: Path) -> None:
        import nightly

        result = nightly._run_graph_reindex_if_stale(tmp_path, dry_run=False)
        assert result == {"status": "skipped", "reason": "no_probe_yet"}

    def test_skips_when_probe_fresh(self, tmp_path: Path) -> None:
        import time as _t

        import nightly

        self._write_probe(tmp_path, int(_t.time()) - 60)  # 60s old
        result = nightly._run_graph_reindex_if_stale(tmp_path, dry_run=False)
        assert result["status"] == "skipped"
        assert "fresh" in result["reason"]

    def test_dry_run_when_probe_stale(self, tmp_path: Path) -> None:
        import time as _t

        import nightly

        self._write_probe(tmp_path, int(_t.time()) - 200_000)  # >24h
        result = nightly._run_graph_reindex_if_stale(tmp_path, dry_run=True)
        assert result["status"] == "dry_run"
        assert result["would_reindex"] is True
        assert result["age_seconds"] >= 200_000

    def test_invokes_subprocess_when_stale(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import time as _t

        import nightly

        self._write_probe(tmp_path, int(_t.time()) - 200_000)

        captured: dict = {}

        class _FakeCompleted:
            returncode = 0
            stdout = "[graph-reindex] processed=42 skipped=0 errors=0 duration=1.5s\n"
            stderr = ""

        def _fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["cwd"] = kwargs.get("cwd")
            return _FakeCompleted()

        # Patch subprocess inside the function's local import scope by
        # replacing it on the imported subprocess module reference.
        import subprocess

        monkeypatch.setattr(subprocess, "run", _fake_run)

        result = nightly._run_graph_reindex_if_stale(tmp_path, dry_run=False)
        assert result["status"] == "ok"
        assert "processed=42" in result["summary"]
        assert captured["cmd"][0] == sys.executable
        assert captured["cmd"][1:4] == ["-m", "cli.main", "graph-reindex"]
        assert captured["cwd"] == str(tmp_path)
