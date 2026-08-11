"""cos pr — PR triage ranking and cross-branch conflict detection.

Part of tests/test_cli.py — collected via the aggregator, not directly.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from _cli_suite.pr_base import PrHarness
from _cli_suite.shared import cli


class TestCosPrTriage(PrHarness):
    """cos pr — PR triage ranking and cross-branch conflict detection."""

    def test_pr_triage_ranks_open_prs(
        self, runner: CliRunner, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-618: cos pr triage emits ONE digest of open agents/* PRs ranked to
        # minimise the human's time-to-unblock — quick-merge (green+clean+no review)
        # first, then needs-review, conflict, red, waiting; non-agent PRs excluded.
        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: True)
        green = [{"status": "COMPLETED", "conclusion": "SUCCESS"}]
        running = [{"status": "IN_PROGRESS"}]
        failing = [{"conclusion": "FAILURE"}]
        rows = [
            {
                "number": 1,
                "headRefName": "agents/t/a",
                "state": "OPEN",
                "statusCheckRollup": running,
                "mergeable": "MERGEABLE",
                "createdAt": "2026-01-01T00:00:00Z",
            },
            {
                "number": 2,
                "headRefName": "agents/t/b",
                "state": "OPEN",
                "statusCheckRollup": failing,
                "mergeable": "MERGEABLE",
                "createdAt": "2026-01-01T00:00:00Z",
            },
            {
                "number": 3,
                "headRefName": "agents/t/c",
                "state": "OPEN",
                "statusCheckRollup": green,
                "mergeable": "CONFLICTING",
                "createdAt": "2026-01-01T00:00:00Z",
            },
            {
                "number": 4,
                "headRefName": "agents/t/d",
                "state": "OPEN",
                "statusCheckRollup": green,
                "mergeable": "MERGEABLE",
                "reviewDecision": "REVIEW_REQUIRED",
                "autoMergeRequest": {"enabledAt": "x"},
                "createdAt": "2026-01-01T00:00:00Z",
            },
            {
                "number": 5,
                "headRefName": "agents/t/e",
                "state": "OPEN",
                "statusCheckRollup": green,
                "mergeable": "MERGEABLE",
                "createdAt": "2026-01-01T00:00:00Z",
            },
            {
                "number": 6,
                "headRefName": "feature/x",
                "state": "OPEN",  # non-agent → excluded
                "statusCheckRollup": green,
                "mergeable": "MERGEABLE",
                "createdAt": "2026-01-01T00:00:00Z",
            },
        ]
        real_run = prc._run

        def fake_run(args, **kw):
            if args[:3] == ["gh", "pr", "list"]:
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps(rows), stderr="")
            return real_run(args, **kw)

        monkeypatch.setattr(prc, "_run", fake_run)
        res = runner.invoke(cli, ["pr", "triage", "--repo", str(repo), "--json"])
        assert res.exit_code == 0, res.output
        data = json.loads(res.output)
        assert data["open"] == 5  # the non-agent PR is excluded
        assert data["quick_merge"] == 1
        assert [e["category"] for e in data["prs"]] == [
            "quick-merge",
            "needs-review",
            "conflict",
            "red",
            "waiting",
        ]
        assert data["prs"][0]["branch"] == "agents/t/e"  # the safe one-click, surfaced first

    def test_pr_triage_empty_report(
        self, runner: CliRunner, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: True)
        real_run = prc._run

        def fake_run(args, **kw):
            if args[:3] == ["gh", "pr", "list"]:
                return subprocess.CompletedProcess(args, 0, stdout="[]", stderr="")
            return real_run(args, **kw)

        monkeypatch.setattr(prc, "_run", fake_run)
        res = runner.invoke(cli, ["pr", "triage", "--repo", str(repo), "--json"])
        assert res.exit_code == 0, res.output
        data = json.loads(res.output)
        assert data["open"] == 0 and data["prs"] == []

    def test_pr_ci_rollup_requests_automerge_fields(
        self, runner: CliRunner, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The STOP-on-green decision needs isDraft + autoMergeRequest in the gh query;
        # drop them and every green PR misreads as passing-unarmed → never lands (D5).
        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: True)
        captured: dict[str, list[str]] = {}
        real_run = prc._run

        def fake_run(args, **kw):
            if args[:3] == ["gh", "pr", "view"]:
                captured["args"] = args
                green = [{"status": "COMPLETED", "conclusion": "SUCCESS"}]
                payload = json.dumps(
                    {
                        "state": "OPEN",
                        "statusCheckRollup": green,
                        "autoMergeRequest": {"enabledAt": "x"},
                    }
                )
                return subprocess.CompletedProcess(args, 0, stdout=payload, stderr="")
            return real_run(args, **kw)

        monkeypatch.setattr(prc, "_run", fake_run)
        res = runner.invoke(cli, ["pr", "status", "--branch", "agents/x/1", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "ci_rollup: passing" in res.output and "passing-unarmed" not in res.output
        json_arg = captured["args"][captured["args"].index("--json") + 1]
        assert "isDraft" in json_arg and "autoMergeRequest" in json_arg

    # --- cross-branch conflict pre-detection (TASK-558) --------------------

    def test_pr_conflicts_reports_cross_branch_overlap(
        self, runner: CliRunner, repo: Path, tmp_path: Path
    ) -> None:
        # Two live agent branches editing foo.py → only the SHARED file is flagged,
        # the per-branch-unique files are not. Advisory, exit 0.
        self._mk_agent_branch(repo, tmp_path, "agents/a/s1", {"foo.py": "A\n", "only_a.py": "x\n"})
        self._mk_agent_branch(repo, tmp_path, "agents/b/s2", {"foo.py": "B\n", "only_b.py": "y\n"})
        res = runner.invoke(
            cli, ["pr", "conflicts", "--branch", "agents/a/s1", "--repo", str(repo), "--json"]
        )
        assert res.exit_code == 0, res.output
        conflicts = json.loads(res.output)["conflicts"]
        assert conflicts == [{"branch": "agents/b/s2", "files": ["foo.py"]}]

    def test_pr_conflicts_detects_uncommitted_overlap(
        self, runner: CliRunner, repo: Path, tmp_path: Path
    ) -> None:
        # The target's STILL-UNCOMMITTED edit to bar.py overlaps a peer's committed
        # bar.py — earliest pre-detection (touched = merge-base diff ∪ worktree porcelain).
        a = self._mk_agent_branch(repo, tmp_path, "agents/a/s1", {})
        (a / "bar.py").write_text("uncommitted A\n", encoding="utf-8")  # not committed
        self._mk_agent_branch(repo, tmp_path, "agents/b/s2", {"bar.py": "B\n"})
        res = runner.invoke(
            cli, ["pr", "conflicts", "--branch", "agents/a/s1", "--repo", str(repo), "--json"]
        )
        assert res.exit_code == 0, res.output
        conflicts = json.loads(res.output)["conflicts"]
        assert conflicts and conflicts[0]["files"] == ["bar.py"]

    def test_pr_conflicts_no_overlap_reads_none(
        self, runner: CliRunner, repo: Path, tmp_path: Path
    ) -> None:
        self._mk_agent_branch(repo, tmp_path, "agents/a/s1", {"a.py": "x\n"})
        self._mk_agent_branch(repo, tmp_path, "agents/b/s2", {"b.py": "y\n"})
        res = runner.invoke(
            cli, ["pr", "conflicts", "--branch", "agents/a/s1", "--repo", str(repo)]
        )
        assert res.exit_code == 0, res.output
        assert "conflicts: (none)" in res.output and "no peer overlap" in res.output

    # --- consumer-fixture dogfood: the full pr-mode loop (TASK-521) ---------
