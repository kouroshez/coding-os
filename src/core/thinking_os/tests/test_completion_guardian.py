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
        f"| {i+1} | c{i+1} | p | 1 | 1 | yes | 0 | no | x |"
        for i in range(unchecked_rows)
    )
    text = (
        f"---\naudit_id: {slug}\ntask_id: TASK-X\nstatus: {status}\n---\n"
        "# audit\n\n## Categories\n\n"
        "| # | Category | Pattern | Files scanned | Hits before | Fixed | Hits after | Verified | Evidence |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
        + rows
        + "\n"
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

    def test_exhaustive_with_completed_audit_no_evidence_fails_on_predicates(
        self, env
    ) -> None:
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
