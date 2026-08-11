"""cos pr — submit, autonomy levels, and auto-merge arming.

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


class TestCosPrSubmit(PrHarness):
    """cos pr — submit, autonomy levels, and auto-merge arming."""

    def test_submit_emits_degraded_status_without_required_check(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.pr_commands as prc

        self._add_bare_remote(repo, tmp_path)
        monkeypatch.setenv(
            "COS_GIT_AUTONOMY", "auto_merge"
        )  # past draft → exercises the CI-gate path
        monkeypatch.setattr(prc, "_gh_ready", lambda: True)
        monkeypatch.setattr(prc, "_has_required_check", lambda r, b: False)
        monkeypatch.setattr(prc, "_open_pr_count", lambda r, s: 0)
        self._fake_gh(prc, monkeypatch)  # gh pr merge => AssertionError if called

        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "wip"], check=True
        )
        res = runner.invoke(cli, ["pr", "submit", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        # explicit, actionable degraded status — never a silent open PR
        assert "merge_status: degraded-no-required-check" in res.output
        assert "auto_merge_armed: False" in res.output
        assert "required status check" in res.output  # action names what's missing

    def test_unknown_autonomy_level_falls_back_to_draft(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # M2: a typo'd rung written outside the Hub API (CLI/hand-edit) must not
        # silently behave as draft while masquerading as the typo — fall back to draft.
        import cli.pr_commands as prc

        monkeypatch.setenv("COS_GIT_AUTONOMY", "auto-merge")  # hyphen typo
        assert prc._autonomy_level() == "draft"
        monkeypatch.setenv("COS_GIT_AUTONOMY", "autonomous")  # valid rung survives
        assert prc._autonomy_level() == "autonomous"
        monkeypatch.setenv("COS_GIT_AUTONOMY", "local")
        assert prc._autonomy_level() == "local"

    def test_submit_degraded_with_task_escalates_to_blocked(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # H3: auto_merge + no required check is a silent deadlock — with a real task
        # it must escalate the board task to blocked, not just emit a stderr line.
        import cli.pr_commands as prc

        self._add_bare_remote(repo, tmp_path)
        monkeypatch.setenv("COS_GIT_AUTONOMY", "auto_merge")
        monkeypatch.setattr(prc, "_gh_ready", lambda: True)
        monkeypatch.setattr(prc, "_has_required_check", lambda r, b: False)
        monkeypatch.setattr(prc, "_open_pr_count", lambda r, s: 0)
        self._fake_gh(prc, monkeypatch)  # gh pr merge => AssertionError if armed
        calls: list = []
        monkeypatch.setattr(prc, "_escalate_blocked", lambda *a, **k: calls.append(a) or True)

        runner.invoke(cli, ["pr", "open", "--task", "TASK-999", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("TASK-999-ses-test-abc"))
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "wip"], check=True
        )
        res = runner.invoke(cli, ["pr", "submit", "--task", "TASK-999", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "merge_status: degraded-no-required-check" in res.output
        assert "board_blocked: True" in res.output
        assert calls, "degraded auto_merge with a task must call _escalate_blocked"
        assert "TASK-999" in calls[0][1]  # task_id threaded to the escalation

    def test_submit_arms_auto_merge_once_with_required_check(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.pr_commands as prc

        self._add_bare_remote(repo, tmp_path)
        monkeypatch.setenv("COS_GIT_AUTONOMY", "auto_merge")  # draft never arms (TASK-533)
        monkeypatch.setattr(prc, "_gh_ready", lambda: True)
        monkeypatch.setattr(prc, "_has_required_check", lambda r, b: True)
        monkeypatch.setattr(prc, "_open_pr_count", lambda r, s: 0)
        merge_calls: list = []
        self._fake_gh(prc, monkeypatch, merge_calls=merge_calls)

        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "wip"], check=True
        )
        res = runner.invoke(cli, ["pr", "submit", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "auto_merge_armed: True" in res.output
        assert "merge_status: auto-merge-armed" in res.output
        # armed exactly once, with the squash auto-merge form
        assert len(merge_calls) == 1, merge_calls
        assert merge_calls[0][:5] == ["gh", "pr", "merge", "--auto", "--squash"]

    def test_auto_merge_loop_end_to_end(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-616: prove the FULL auto_merge lifecycle in CI without GitHub minutes —
        # open → submit (push + create + arm) → status pending → passing → merged →
        # cleanup. A stateful mock-gh advances the PR each rollup poll the way GitHub
        # would: checks go green, the armed auto-merge then lands it, the branch is gone.
        import cli.pr_commands as prc

        self._add_bare_remote(repo, tmp_path)
        monkeypatch.setenv("COS_GIT_AUTONOMY", "auto_merge")
        monkeypatch.setattr(prc, "_gh_ready", lambda: True)
        monkeypatch.setattr(prc, "_has_required_check", lambda r, b: True)
        monkeypatch.setattr(prc, "_open_pr_count", lambda r, s: 0)

        st = {"created": False, "armed": False, "merged": False, "polls": 0}
        real_run = prc._run

        def view(payload: object) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess([], 0, stdout=json.dumps(payload), stderr="")

        def fake_run(args, **kw):
            head = args[:3]
            if head == ["gh", "pr", "create"]:
                st["created"] = True
                return subprocess.CompletedProcess(args, 0, stdout="https://gh/pr/1\n", stderr="")
            if head == ["gh", "pr", "merge"]:
                st["armed"] = True
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            if head == ["gh", "api", "graphql"]:  # no merge queue in this scenario
                return view({"data": {"repository": {"pullRequest": {"mergeQueueEntry": None}}}})
            if head == ["gh", "pr", "view"]:
                fields = args[args.index("--json") + 1] if "--json" in args else ""
                if "statusCheckRollup" not in fields:  # _pr_review_required probe (submit)
                    return view({"reviewDecision": None})
                st["polls"] += 1
                if st["merged"]:
                    return view(
                        {"number": 1, "state": "MERGED", "mergedAt": "2026-01-01T00:00:00Z"}
                    )
                if st["polls"] == 1:  # checks still running
                    return view(
                        {
                            "number": 1,
                            "state": "OPEN",
                            "statusCheckRollup": [{"status": "IN_PROGRESS"}],
                        }
                    )
                # checks green; an armed auto-merge fires right after this poll
                pr = {
                    "number": 1,
                    "state": "OPEN",
                    "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}],
                }
                if st["armed"]:
                    pr["autoMergeRequest"] = {"enabledAt": "x"}
                    st["merged"] = True
                return view(pr)
            if head == ["gh", "pr", "list"]:  # _pr_state for the cleanup merge-gate
                if st["merged"]:
                    return view([{"state": "MERGED", "mergedAt": "2026-01-01T00:00:00Z"}])
                return view([{"state": "OPEN"}] if st["created"] else [])
            return real_run(args, **kw)

        monkeypatch.setattr(prc, "_run", fake_run)

        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "wip"], check=True
        )
        sub = runner.invoke(cli, ["pr", "submit", "--adhoc", "--repo", str(repo)])
        assert sub.exit_code == 0, sub.output
        assert "auto_merge_armed: True" in sub.output

        branch = "agents/adhoc/ses-test-abc"
        rollups = []
        for _ in range(3):  # one status poll per agent turn (the SKILL's loop)
            r = runner.invoke(
                cli, ["pr", "status", "--branch", branch, "--repo", str(repo), "--json"]
            )
            assert r.exit_code == 0, r.output
            rollups.append(json.loads(r.output)["ci_rollup"])
        assert rollups == ["pending", "passing", "merged"], rollups

        clean = runner.invoke(cli, ["pr", "cleanup", "--adhoc", "--repo", str(repo)])
        assert clean.exit_code == 0, clean.output
        assert "agents/adhoc/ses-test-abc" not in self._branches(repo)
        assert "adhoc-ses-test-abc" not in self._worktrees(repo)

    def test_submit_draft_autonomy_never_arms_even_with_required_check(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-533: default 'draft' opens the PR but never arms auto-merge,
        # even when a required check exists — a human merges.
        import cli.pr_commands as prc

        self._add_bare_remote(repo, tmp_path)
        monkeypatch.delenv("COS_GIT_AUTONOMY", raising=False)  # default = draft
        monkeypatch.setattr(prc, "_gh_ready", lambda: True)
        monkeypatch.setattr(prc, "_has_required_check", lambda r, b: True)
        monkeypatch.setattr(prc, "_open_pr_count", lambda r, s: 0)
        self._fake_gh(prc, monkeypatch)  # gh pr merge => AssertionError if armed

        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "wip"], check=True
        )
        res = runner.invoke(cli, ["pr", "submit", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "merge_status: draft" in res.output
        assert "auto_merge_armed: False" in res.output
        assert "autonomy_level: draft" in res.output

    def test_autonomy_levels_include_local_autonomous(self) -> None:
        # TASK-614: the rung must exist in BOTH the consumer-side tuple and the Hub
        # settings Literal (settings.py is exercised by test_hub_settings_git).
        import cli.pr_commands as prc

        assert "local_autonomous" in prc._AUTONOMY_LEVELS
