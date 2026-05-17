"""Tests for `cos cognition trace-replay --audit-mode` (TASK-004 G14 follow-up).

Covers the 4 branches added in src/cli/cognition.py::_assert_exhaustive_evidence:
  • no intent.json                                  → SKIP exit 0
  • intent.exhaustive=false                         → SKIP exit 0
  • exhaustive + no EvidenceBundle                  → FAIL exit 1
  • exhaustive + bundle missing exhaustive_evidence → FAIL exit 1
  • exhaustive + counts_after has residuals         → FAIL exit 1
  • exhaustive + reviewer_check != "pass"           → FAIL exit 1
  • exhaustive + everything green                   → PASS exit 0

Uses Click's CliRunner so the command runs in-process (no uv subprocess)
and the test fixtures monkeypatch the env so the agent dir lives under
tmp_path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner, Result


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))


from cli.cognition import cognition_group  # noqa: E402


def _seed_trace(agent_dir: Path, session_id: str) -> None:
    trace_dir = agent_dir / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    path = trace_dir / f"{session_id}.jsonl"
    lines = [
        {"kind": "analyze_done", "ts": "2026-05-17T00:00:01Z"},
        {"kind": "compose_done", "ts": "2026-05-17T00:00:02Z"},
    ]
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")


def _seed_intent(agent_dir: Path, **fields) -> None:
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / ".intent.json").write_text(json.dumps(fields))


def _seed_bundle(agent_dir: Path, session_id: str, payload: dict) -> None:
    (agent_dir / f"evidence_bundle_{session_id}.json").write_text(json.dumps(payload))


@pytest.fixture
def env(tmp_path, monkeypatch):
    agent_dir = tmp_path / ".coding-os" / "claude"
    agent_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path / ".coding-os"))
    monkeypatch.setenv("COS_AGENT", "claude")
    monkeypatch.setenv("COS_AGENT_DIR", str(agent_dir))
    monkeypatch.chdir(tmp_path)
    return tmp_path, agent_dir, "ses-test-001"


def _run(sid: str) -> Result:
    runner = CliRunner()
    return runner.invoke(cognition_group, ["trace-replay", sid, "--audit-mode"])


class TestSkipBranches:
    def test_no_intent_skips(self, env):
        _, agent_dir, sid = env
        _seed_trace(agent_dir, sid)
        result = _run(sid)
        assert result.exit_code == 0, result.output
        assert "SKIP" in result.output
        assert "no intent.json" in result.output

    def test_non_exhaustive_intent_skips(self, env):
        _, agent_dir, sid = env
        _seed_trace(agent_dir, sid)
        _seed_intent(agent_dir, exhaustive=False, predicates=[])
        result = _run(sid)
        assert result.exit_code == 0, result.output
        assert "SKIP" in result.output
        assert "not exhaustive" in result.output


class TestFailBranches:
    def test_exhaustive_no_bundle_fails(self, env):
        _, agent_dir, sid = env
        _seed_trace(agent_dir, sid)
        _seed_intent(agent_dir, exhaustive=True, predicates=["coverage_100"])
        result = _run(sid)
        assert result.exit_code == 1, result.output
        assert "no EvidenceBundle" in result.output

    def test_bundle_missing_exhaustive_evidence_fails(self, env):
        _, agent_dir, sid = env
        _seed_trace(agent_dir, sid)
        _seed_intent(agent_dir, exhaustive=True, predicates=["coverage_100"])
        _seed_bundle(agent_dir, sid, {"task_marker": "T", "persona_id": "p"})
        result = _run(sid)
        assert result.exit_code == 1, result.output
        assert "no exhaustive_evidence slot" in result.output

    def test_counts_after_residuals_fail(self, env):
        _, agent_dir, sid = env
        _seed_trace(agent_dir, sid)
        _seed_intent(agent_dir, exhaustive=True, predicates=["coverage_100"])
        _seed_bundle(
            agent_dir,
            sid,
            {
                "task_marker": "T",
                "persona_id": "p",
                "exhaustive_evidence": {
                    "categories_declared": ["a"],
                    "categories_covered": ["a"],
                    "counts_before": {"a": 5},
                    "counts_after": {"a": 3},
                    "files_searched": ["x.py"],
                    "tests_run": ["pytest"],
                    "gaps_remaining": [],
                    "confidence": 0.9,
                    "reviewer_check": "pass",
                    "audit_artifact_path": None,
                },
            },
        )
        result = _run(sid)
        assert result.exit_code == 1, result.output
        assert "counts_after non-zero" in result.output

    def test_reviewer_check_pending_fails(self, env):
        _, agent_dir, sid = env
        _seed_trace(agent_dir, sid)
        _seed_intent(agent_dir, exhaustive=True, predicates=["coverage_100"])
        _seed_bundle(
            agent_dir,
            sid,
            {
                "task_marker": "T",
                "persona_id": "p",
                "exhaustive_evidence": {
                    "categories_declared": ["a"],
                    "categories_covered": ["a"],
                    "counts_before": {"a": 5},
                    "counts_after": {"a": 0},
                    "files_searched": ["x.py"],
                    "tests_run": ["pytest"],
                    "gaps_remaining": [],
                    "confidence": 0.9,
                    "reviewer_check": "pending",
                    "audit_artifact_path": None,
                },
            },
        )
        result = _run(sid)
        assert result.exit_code == 1, result.output
        assert "reviewer_check=" in result.output


class TestPassBranch:
    def test_all_predicates_satisfied_passes(self, env):
        _, agent_dir, sid = env
        _seed_trace(agent_dir, sid)
        _seed_intent(agent_dir, exhaustive=True, predicates=["coverage_100"])
        _seed_bundle(
            agent_dir,
            sid,
            {
                "task_marker": "T",
                "persona_id": "p",
                "exhaustive_evidence": {
                    "categories_declared": ["a"],
                    "categories_covered": ["a"],
                    "counts_before": {"a": 5},
                    "counts_after": {"a": 0},
                    "files_searched": ["x.py"],
                    "tests_run": ["pytest"],
                    "gaps_remaining": [],
                    "confidence": 1.0,
                    "reviewer_check": "pass",
                    "audit_artifact_path": None,
                },
            },
        )
        result = _run(sid)
        assert result.exit_code == 0, result.output
        assert "audit] PASS" in result.output
        assert "exhaustive obligations satisfied" in result.output
