"""Tests for completion_guardian (TASK-004 G4).

Covers:
  * No intent file → pass
  * intent.exhaustive=false → pass
  * exhaustive intent + audit with unchecked rows → fail
  * exhaustive intent + audit fully checked + no evidence → fail (predicates)
  * exhaustive intent + audit fully checked + full evidence → pass
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
THINKING_OS = REPO_ROOT / "src" / "core" / "thinking_os"
if str(THINKING_OS) not in sys.path:
    sys.path.insert(0, str(THINKING_OS))

from completion_guardian import guard_completion  # noqa: E402


def _write_intent(agent_dir: Path, payload: dict) -> None:
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / ".intent.json").write_text(json.dumps(payload))


def _write_bundle(agent_dir: Path, session_id: str, payload: dict) -> None:
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / f"evidence_bundle_{session_id}.json").write_text(json.dumps(payload))


def _write_audit(repo_root: Path, slug: str, status: str, unchecked_rows: int) -> Path:
    audit_dir = repo_root / "docs" / "tasks" / "audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        f"| {i + 1} | c{i + 1} | p | 1 | 1 | yes | 0 | no | x |" for i in range(unchecked_rows)
    )
    text = (
        f"---\naudit_id: {slug}\ntask_id: TASK-X\nstatus: {status}\n---\n"
        "# audit\n\n## Categories\n\n"
        "| # | Category | Pattern | Files scanned | Hits before | Fixed | Hits after | Verified | Evidence |\n"
        "|---|---|---|---|---|---|---|---|---|\n" + rows + "\n"
    )
    path = audit_dir / f"audit-{slug}.md"
    path.write_text(text)
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    agent_dir = tmp_path / ".coding-os" / "claude"
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path / ".coding-os"))
    monkeypatch.setenv("COS_AGENT", "claude")
    monkeypatch.setenv("COS_AGENT_DIR", str(agent_dir))
    monkeypatch.chdir(tmp_path)
    return tmp_path, agent_dir


class TestNoIntent:
    def test_no_intent_file_passes(self, env) -> None:
        repo, _ = env
        result = guard_completion(session_id="s1", repo_root=repo)
        assert result.status == "pass"
        assert result.intent_exhaustive is False
        assert result.gaps == []


class TestNonExhaustive:
    def test_intent_exhaustive_false_passes(self, env) -> None:
        repo, agent_dir = env
        _write_intent(agent_dir, {"exhaustive": False, "predicates": []})
        result = guard_completion(session_id="s1", repo_root=repo)
        assert result.status == "pass"


class TestAuditRowGaps:
    def test_exhaustive_with_unchecked_rows_fails(self, env) -> None:
        repo, agent_dir = env
        _write_intent(agent_dir, {"exhaustive": True, "predicates": ["coverage_100"]})
        _write_audit(repo, "slug-a", "in_progress", unchecked_rows=3)
        result = guard_completion(session_id="s1", repo_root=repo)
        assert result.status == "fail"
        assert any("3 unchecked" in gap for gap in result.gaps)
        assert any("predicates_unsatisfied" in gap for gap in result.gaps)

    def test_exhaustive_with_completed_audit_no_evidence_fails_on_predicates(self, env) -> None:
        repo, agent_dir = env
        _write_intent(agent_dir, {"exhaustive": True, "predicates": ["coverage_100"]})
        _write_audit(repo, "slug-b", "in_progress", unchecked_rows=0)
        result = guard_completion(session_id="s1", repo_root=repo)
        assert result.status == "fail"
        # No audit-row gaps, but predicate gap still present.
        assert all("unchecked" not in g for g in result.gaps)
        assert any("predicates_unsatisfied" in g for g in result.gaps)


class TestPredicateSatisfied:
    def test_exhaustive_with_full_evidence_passes(self, env) -> None:
        repo, agent_dir = env
        _write_intent(agent_dir, {"exhaustive": True, "predicates": ["coverage_100"]})
        _write_audit(repo, "slug-c", "in_progress", unchecked_rows=0)
        _write_bundle(
            agent_dir,
            "s1",
            {
                "task_marker": "TASK-X",
                "persona_id": "implementer",
                "exhaustive_evidence": {
                    "categories_declared": ["c1"],
                    "categories_covered": ["c1"],
                    "counts_before": {"c1": 3},
                    "counts_after": {"c1": 0},
                    "files_searched": ["src/foo.py"],
                    "tests_run": ["pytest"],
                    "gaps_remaining": [],
                    "confidence": 0.9,
                    "reviewer_check": "pass",
                    "audit_artifact_path": "docs/tasks/audits/audit-slug-c.md",
                },
            },
        )
        result = guard_completion(session_id="s1", repo_root=repo)
        assert result.status == "pass", result.gaps
        assert result.gaps == []
        assert result.has_evidence_bundle is True


class TestMarkdownStatusForm:
    """Audit lifecycle hooks + guardian must recognise BOTH conventions:
    YAML frontmatter (`---\\nstatus: in_progress\\n---`, template-canonical)
    AND markdown bold (`**Status:** in_progress`, historic). Drift between
    consumers means an agent writing one form gets recognised by some hooks
    but not by the guardian → premature 'done' slips through."""

    def _write_markdown_form_audit(
        self,
        repo_root: Path,
        slug: str,
        status: str,
        unchecked_rows: int,
    ) -> Path:
        audit_dir = repo_root / "docs" / "tasks" / "audits"
        audit_dir.mkdir(parents=True, exist_ok=True)
        rows = "\n".join(
            f"| {i + 1} | c{i + 1} | p | 1 | 1 | yes | 0 | no | x |"
            for i in range(unchecked_rows)
        )
        # NO YAML frontmatter — only markdown bold metadata. This is the
        # historic form (audit-graph-os-*.md, TASK-029/032).
        text = (
            f"# Audit — {slug}\n\n"
            f"**Task:** TASK-X\n"
            f"**Status:** {status}\n\n"
            "## Categories\n\n"
            "| # | Category | Pattern | Files scanned | Hits before | Fixed | Hits after | Verified | Evidence |\n"
            "|---|---|---|---|---|---|---|---|---|\n" + rows + "\n"
        )
        path = audit_dir / f"audit-{slug}.md"
        path.write_text(text)
        return path

    def test_markdown_in_progress_blocks_premature_done(self, env) -> None:
        repo, agent_dir = env
        _write_intent(agent_dir, {"exhaustive": True, "predicates": ["coverage_100"]})
        self._write_markdown_form_audit(repo, "md-slug", "in_progress", unchecked_rows=2)
        result = guard_completion(session_id="s1", repo_root=repo)
        # Guardian MUST see the markdown-form audit as active and report
        # the 2 unchecked rows as gaps. Pre-fix the guardian skipped this
        # file (YAML-only regex), letting premature 'done' through.
        assert result.status == "fail"
        assert any("2 unchecked" in g for g in result.gaps)

    def test_markdown_complete_not_scanned(self, env) -> None:
        repo, agent_dir = env
        _write_intent(agent_dir, {"exhaustive": True, "predicates": []})
        # Markdown form `**Status:** complete` — guardian should not flag.
        self._write_markdown_form_audit(repo, "md-done", "complete", unchecked_rows=5)
        result = guard_completion(session_id="s1", repo_root=repo)
        assert result.status == "pass"


class TestCompletedAuditStatus:
    def test_completed_audit_not_scanned(self, env) -> None:
        repo, agent_dir = env
        _write_intent(agent_dir, {"exhaustive": True, "predicates": []})
        # status:completed → not scanned by guardian (no row check needed).
        _write_audit(repo, "slug-d", "completed", unchecked_rows=5)
        result = guard_completion(session_id="s1", repo_root=repo)
        assert result.status == "pass"
        assert result.audits_checked == []


class TestMissingEvidenceBundle:
    def test_exhaustive_no_bundle_for_session(self, env) -> None:
        repo, agent_dir = env
        _write_intent(agent_dir, {"exhaustive": True, "predicates": ["coverage_100"]})
        _write_audit(repo, "slug-e", "in_progress", unchecked_rows=0)
        result = guard_completion(session_id="missing-session", repo_root=repo)
        assert result.status == "fail"
        assert any("no EvidenceBundle" in g for g in result.gaps)


class TestSessionMismatchGuard:
    def test_intent_with_different_session_id_is_ignored(self, env) -> None:
        repo, agent_dir = env
        # Stale intent stamped with prior session id.
        _write_intent(
            agent_dir,
            {
                "exhaustive": True,
                "predicates": ["coverage_100"],
                "session_id": "ses-old-001",
            },
        )
        _write_audit(repo, "slug-stale", "in_progress", unchecked_rows=3)
        # Guardian invoked for a DIFFERENT session.
        result = guard_completion(session_id="ses-new-002", repo_root=repo)
        assert result.status == "pass", result.gaps
        assert result.intent_exhaustive is False
        assert result.gaps == []

    def test_intent_with_matching_session_id_still_enforces(self, env) -> None:
        repo, agent_dir = env
        _write_intent(
            agent_dir,
            {
                "exhaustive": True,
                "predicates": ["coverage_100"],
                "session_id": "ses-match-001",
            },
        )
        _write_audit(repo, "slug-match", "in_progress", unchecked_rows=2)
        result = guard_completion(session_id="ses-match-001", repo_root=repo)
        assert result.status == "fail"
        assert any("2 unchecked" in g for g in result.gaps)

    def test_intent_without_session_id_still_enforces_back_compat(self, env) -> None:
        """Old intent.json without session_id field — no rejection."""
        repo, agent_dir = env
        _write_intent(
            agent_dir,
            {"exhaustive": True, "predicates": ["coverage_100"]},
        )
        _write_audit(repo, "slug-legacy", "in_progress", unchecked_rows=1)
        result = guard_completion(session_id="ses-any-id", repo_root=repo)
        assert result.status == "fail"

    def test_guardian_called_without_session_id_does_not_reject(self, env) -> None:
        """When session_id arg is empty, skip the mismatch check entirely."""
        repo, agent_dir = env
        _write_intent(
            agent_dir,
            {
                "exhaustive": True,
                "predicates": ["coverage_100"],
                "session_id": "ses-foo",
            },
        )
        _write_audit(repo, "slug-empty", "in_progress", unchecked_rows=1)
        result = guard_completion(session_id="", repo_root=repo)
        assert result.status == "fail"


class TestGapObservationRecorded:
    def test_failure_inserts_observation_row(self, env, monkeypatch) -> None:
        repo, agent_dir = env
        # Set up an in-process SQLite DB with the observations schema.
        import sqlite3

        db_path = repo / ".coding-os" / "coding-os.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE observations ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " session_id TEXT, tool_name TEXT, observation_type TEXT,"
                " memory_type TEXT, impact_score REAL, title TEXT,"
                " narrative TEXT, facts TEXT,"
                " created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
            )
        monkeypatch.setenv("COS_DB_PATH", str(db_path))

        _write_intent(agent_dir, {"exhaustive": True, "predicates": ["coverage_100"]})
        _write_audit(repo, "slug-fail", "in_progress", unchecked_rows=2)

        # Drive main() to trigger the gap-observation insert path.
        from completion_guardian import _record_gap_observation_safe, guard_completion

        result = guard_completion(session_id="ses-1", repo_root=repo)
        assert result.status == "fail"
        _record_gap_observation_safe("ses-1", result)

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT observation_type, memory_type, title, session_id FROM observations"
            ).fetchall()
        assert len(rows) == 1
        obs_type, mem_type, title, sess = rows[0]
        assert obs_type == "completion_gap"
        assert mem_type == "error"
        assert "completion_gap" in title
        assert sess == "ses-1"


class TestEvidenceDispatchCrossCheck:
    """G4 hardening (TASK-059): a bundle file claiming exhaustive_evidence
    must be backed by a real formula_dispatches row — otherwise
    cos_supervise_record_output never ran and the audit checkbox was a
    false attestation the guardian must not trust."""

    def _full_bundle(self) -> dict:
        return {
            "task_marker": "TASK-X",
            "persona_id": "implementer",
            "exhaustive_evidence": {
                "categories_declared": ["c1"],
                "categories_covered": ["c1"],
                "counts_before": {"c1": 3},
                "counts_after": {"c1": 0},
                "files_searched": ["src/foo.py"],
                "tests_run": ["pytest"],
                "gaps_remaining": [],
                "confidence": 0.9,
                "reviewer_check": "pass",
                "audit_artifact_path": "docs/tasks/audits/audit-slug-c.md",
            },
        }

    def _make_dispatches_db(self, repo: Path, rows: list | None = None) -> Path:
        import sqlite3

        db_path = repo / ".coding-os" / "coding-os.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS formula_dispatches ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " session_id TEXT, task_marker TEXT, persona_id TEXT,"
                " formula_id TEXT, status TEXT)"
            )
            for r in rows or []:
                conn.execute(
                    "INSERT INTO formula_dispatches "
                    "(session_id, task_marker, persona_id, formula_id, status) "
                    "VALUES (?,?,?,?,?)",
                    r,
                )
        return db_path

    def test_bundle_without_dispatch_row_fails(self, env, monkeypatch) -> None:
        repo, agent_dir = env
        db_path = self._make_dispatches_db(repo, rows=[])
        monkeypatch.setenv("COS_DB_PATH", str(db_path))
        _write_intent(agent_dir, {"exhaustive": True, "predicates": ["coverage_100"]})
        _write_audit(repo, "slug-c", "in_progress", unchecked_rows=0)
        _write_bundle(agent_dir, "s1", self._full_bundle())
        result = guard_completion(session_id="s1", repo_root=repo)
        assert result.status == "fail"
        assert any("evidence_dispatch_missing" in g for g in result.gaps)

    def test_bundle_with_dispatch_row_passes(self, env, monkeypatch) -> None:
        repo, agent_dir = env
        db_path = self._make_dispatches_db(
            repo, rows=[("s1", "TASK-X", "implementer", "exhaustive_evidence", "ok")]
        )
        monkeypatch.setenv("COS_DB_PATH", str(db_path))
        _write_intent(agent_dir, {"exhaustive": True, "predicates": ["coverage_100"]})
        _write_audit(repo, "slug-c", "in_progress", unchecked_rows=0)
        _write_bundle(agent_dir, "s1", self._full_bundle())
        result = guard_completion(session_id="s1", repo_root=repo)
        assert result.status == "pass", result.gaps
        assert all("evidence_dispatch_missing" not in g for g in result.gaps)

    def test_missing_db_fail_open(self, env, monkeypatch) -> None:
        repo, agent_dir = env
        monkeypatch.setenv("COS_DB_PATH", str(repo / "nonexistent.db"))
        _write_intent(agent_dir, {"exhaustive": True, "predicates": ["coverage_100"]})
        _write_audit(repo, "slug-c", "in_progress", unchecked_rows=0)
        _write_bundle(agent_dir, "s1", self._full_bundle())
        result = guard_completion(session_id="s1", repo_root=repo)
        assert result.status == "pass", result.gaps
        assert all("evidence_dispatch_missing" not in g for g in result.gaps)
