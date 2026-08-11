"""cos pr — git state listing and CI rollup classification.

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


class TestCosPrStatus(PrHarness):
    """cos pr — git state listing and CI rollup classification."""

    def test_git_state_lists_branches_current_and_remote(self, repo: Path) -> None:
        # TASK-534: real repo state for the Hub Git tab — local git only, so it
        # answers (current + branches) even with no remote configured.
        import cli.pr_commands as prc

        subprocess.run(["git", "-C", str(repo), "branch", "develop"], check=True)
        st = prc._git_state(str(repo))
        assert st["current_branch"] == "main"
        assert {"main", "develop"} <= set(st["branches"])
        assert st["remote_url"] == ""

    # --- TASK-529: CI rollup signal for the autonomous driver loop ----------

    def test_rollup_state_classification(self) -> None:
        import cli.pr_commands as prc

        assert (
            prc._rollup_state({"mergedAt": "2026-06-24T00:00:00Z", "state": "MERGED"}) == "merged"
        )
        assert prc._rollup_state({"state": "CLOSED"}) == "closed"
        assert prc._rollup_state({"state": "OPEN", "statusCheckRollup": []}) == "pending"
        red = {
            "state": "OPEN",
            "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "FAILURE"}],
        }
        assert prc._rollup_state(red) == "red"
        pend = {"state": "OPEN", "statusCheckRollup": [{"status": "IN_PROGRESS"}]}
        assert prc._rollup_state(pend) == "pending"
        green = [{"status": "COMPLETED", "conclusion": "SUCCESS"}]
        # green but auto-merge NOT armed (draft autonomy / no required check) → the
        # signal-derivable STOP state, so the driver never re-polls forever (D5).
        assert prc._rollup_state({"state": "OPEN", "statusCheckRollup": green}) == "passing-unarmed"
        # green AND auto-merge armed (not a draft) → it will land itself.
        armed = {
            "state": "OPEN",
            "statusCheckRollup": green,
            "autoMergeRequest": {"enabledAt": "x"},
        }
        assert prc._rollup_state(armed) == "passing"
        # green + armed but a GitHub draft PR → still won't auto-land → STOP state.
        draft = {**armed, "isDraft": True}
        assert prc._rollup_state(draft) == "passing-unarmed"
        # red wins over pending when both are present
        mixed = {
            "state": "OPEN",
            "statusCheckRollup": [{"status": "IN_PROGRESS"}, {"conclusion": "FAILURE"}],
        }
        assert prc._rollup_state(mixed) == "red"

    def test_rollup_state_merge_queue(self) -> None:
        # TASK-613: a PR in the GitHub merge queue reads as a DISTINCT `queued` (not
        # pending) so the driver waits instead of re-submitting; an UNMERGEABLE entry
        # (the queue will eject it) reads as red so only that PR is healed while
        # followers keep merging. Signal = GraphQL mergeQueueEntry, injected by
        # _pr_ci_rollup (gh pr view --json cannot supply it).
        import cli.pr_commands as prc

        green = [{"status": "COMPLETED", "conclusion": "SUCCESS"}]
        running = [{"status": "IN_PROGRESS"}]
        for st in ("QUEUED", "AWAITING_CHECKS", "MERGEABLE", "LOCKED"):
            # queued wins over the waiting merge_group checks (which read as pending)…
            pr = {"state": "OPEN", "statusCheckRollup": running, "mergeQueueEntry": {"state": st}}
            assert prc._rollup_state(pr) == "queued", st
            # …and over green-but-armed (in the queue, hasn't landed yet).
            armed_q = {
                "state": "OPEN",
                "statusCheckRollup": green,
                "autoMergeRequest": {"enabledAt": "x"},
                "mergeQueueEntry": {"state": st},
            }
            assert prc._rollup_state(armed_q) == "queued", st
        # ejected / will-be-ejected → red (heal only this PR).
        ejected = {
            "state": "OPEN",
            "statusCheckRollup": green,
            "mergeQueueEntry": {"state": "UNMERGEABLE"},
        }
        assert prc._rollup_state(ejected) == "red"
        # a genuinely failing check still wins over a queue entry (defense in depth).
        red_in_q = {
            "state": "OPEN",
            "statusCheckRollup": [{"conclusion": "FAILURE"}],
            "mergeQueueEntry": {"state": "AWAITING_CHECKS"},
        }
        assert prc._rollup_state(red_in_q) == "red"
        # back-compat: no entry (no merge queue) → byte-unchanged verdicts.
        assert prc._rollup_state({"state": "OPEN", "statusCheckRollup": running}) == "pending"
        assert (
            prc._rollup_state(
                {
                    "state": "OPEN",
                    "statusCheckRollup": green,
                    "autoMergeRequest": {"enabledAt": "x"},
                }
            )
            == "passing"
        )
        assert (
            prc._rollup_state(
                {"state": "OPEN", "statusCheckRollup": green, "mergeQueueEntry": None}
            )
            == "passing-unarmed"
        )

    def test_pr_ci_rollup_merge_queue_probe(
        self, runner: CliRunner, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-613: a pending/passing base verdict triggers the GraphQL mergeQueueEntry
        # probe and upgrades to `queued`; a final verdict (red) skips the probe, so a
        # repo with no merge queue makes zero extra calls (byte-unchanged).
        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: True)
        real_run = prc._run
        graphql = {"n": 0}

        def fake_passing(args, **kw):
            if args[:3] == ["gh", "pr", "view"]:
                green = [{"status": "COMPLETED", "conclusion": "SUCCESS"}]
                payload = json.dumps(
                    {
                        "number": 7,
                        "state": "OPEN",
                        "statusCheckRollup": green,
                        "autoMergeRequest": {"enabledAt": "x"},
                    }
                )
                return subprocess.CompletedProcess(args, 0, stdout=payload, stderr="")
            if args[:3] == ["gh", "api", "graphql"]:
                graphql["n"] += 1
                payload = json.dumps(
                    {
                        "data": {
                            "repository": {"pullRequest": {"mergeQueueEntry": {"state": "QUEUED"}}}
                        }
                    }
                )
                return subprocess.CompletedProcess(args, 0, stdout=payload, stderr="")
            return real_run(args, **kw)

        monkeypatch.setattr(prc, "_run", fake_passing)
        assert prc._pr_ci_rollup(str(repo), "agents/x/1") == "queued"
        assert graphql["n"] == 1  # probed because the base verdict was passing

        graphql["n"] = 0

        def fake_red(args, **kw):
            if args[:3] == ["gh", "pr", "view"]:
                payload = json.dumps(
                    {"number": 7, "state": "OPEN", "statusCheckRollup": [{"conclusion": "FAILURE"}]}
                )
                return subprocess.CompletedProcess(args, 0, stdout=payload, stderr="")
            if args[:3] == ["gh", "api", "graphql"]:
                graphql["n"] += 1
                return subprocess.CompletedProcess(args, 0, stdout="{}", stderr="")
            return real_run(args, **kw)

        monkeypatch.setattr(prc, "_run", fake_red)
        assert prc._pr_ci_rollup(str(repo), "agents/x/1") == "red"
        assert graphql["n"] == 0  # final verdict → no merge-queue probe

    def test_pr_status_branch_reports_ci_rollup(
        self, runner: CliRunner, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: True)
        real_run = prc._run

        def fake_run(args, **kw):
            if args[:3] == ["gh", "pr", "view"]:
                payload = json.dumps(
                    {
                        "state": "OPEN",
                        "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "FAILURE"}],
                    }
                )
                return subprocess.CompletedProcess(args, 0, stdout=payload, stderr="")
            return real_run(args, **kw)

        monkeypatch.setattr(prc, "_run", fake_run)
        res = runner.invoke(cli, ["pr", "status", "--branch", "agents/x/1", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "ci_rollup: red" in res.output
