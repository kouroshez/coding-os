"""cos pr — local landing, unprotected-integration warnings, and worktree resolution.

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


class TestCosPrLand(PrHarness):
    """cos pr — local landing, unprotected-integration warnings, and worktree resolution."""

    def test_pr_land_merges_to_local_integration_and_cleans_up(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-614: local_autonomous lands the agent branch onto LOCAL integration after
        # a green verify, then removes the worktree+branch — zero push/PR/CI, no orphan.
        import time

        monkeypatch.setenv("COS_GIT_AUTONOMY", "local_autonomous")
        (repo / ".coding-os").mkdir(parents=True, exist_ok=True)
        (repo / ".coding-os" / ".last-verify.json").write_text(
            json.dumps({"cli": {"status": "PASS", "ts": int(time.time())}}), encoding="utf-8"
        )
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        (wt / "landed.txt").write_text("work\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(wt), "add", "landed.txt"], check=True)
        subprocess.run(["git", "-C", str(wt), "commit", "-q", "-m", "work"], check=True)

        res = runner.invoke(cli, ["pr", "land", "--adhoc", "--repo", str(repo), "--json"])
        assert res.exit_code == 0, res.output
        assert json.loads(res.output)["landed"] is True
        assert (repo / "landed.txt").exists()  # work landed on local main
        assert "agents/adhoc/ses-test-abc" not in self._branches(repo)  # no orphan branch
        assert "adhoc-ses-test-abc" not in self._worktrees(repo)  # no orphan worktree

    def test_pr_land_refuses_without_green_verify(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-614: a RED/absent local verify must NOT land — the commit stays on the branch.
        monkeypatch.setenv("COS_GIT_AUTONOMY", "local_autonomous")
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "work"], check=True
        )

        res = runner.invoke(cli, ["pr", "land", "--adhoc", "--repo", str(repo), "--json"])
        assert res.exit_code == 1, res.output
        data = json.loads(res.output)
        assert data["landed"] is False and data["reason"] == "verify-not-green"
        assert "agents/adhoc/ses-test-abc" in self._branches(
            repo
        )  # branch survives, nothing landed

    def test_pr_land_aborts_on_conflict(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-614: a merge conflict → `merge --abort`, no land, surfaced; integration clean.
        import time

        monkeypatch.setenv("COS_GIT_AUTONOMY", "local_autonomous")
        (repo / ".coding-os").mkdir(parents=True, exist_ok=True)
        (repo / ".coding-os" / ".last-verify.json").write_text(
            json.dumps({"cli": {"status": "PASS", "ts": int(time.time())}}), encoding="utf-8"
        )
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        (wt / "c.txt").write_text("branch side\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(wt), "add", "c.txt"], check=True)
        subprocess.run(["git", "-C", str(wt), "commit", "-q", "-m", "branch c"], check=True)
        # a conflicting add of the SAME path on local main
        (repo / "c.txt").write_text("main side\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "c.txt"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "main c"], check=True)

        res = runner.invoke(cli, ["pr", "land", "--adhoc", "--repo", str(repo), "--json"])
        assert res.exit_code == 1, res.output
        data = json.loads(res.output)
        assert data["landed"] is False and data["reason"] == "merge-conflict"
        assert "agents/adhoc/ses-test-abc" in self._branches(repo)  # not landed → branch survives
        assert not (repo / ".git" / "MERGE_HEAD").exists()  # merge --abort left the tree clean
        assert (repo / "c.txt").read_text() == "main side\n"  # integration unchanged

    def test_submit_local_autonomy_never_pushes(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-540: the `local` rung commits in the worktree but never pushes —
        # works with NO remote at all (the repo fixture has none) and short-circuits
        # before the capability probe, so a missing remote is the mode, not a degrade.
        import cli.pr_commands as prc

        monkeypatch.setenv("COS_GIT_AUTONOMY", "local")
        self._fake_gh(prc, monkeypatch)  # any gh pr merge => AssertionError

        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "wip"], check=True
        )
        res = runner.invoke(cli, ["pr", "submit", "--adhoc", "--repo", str(repo)])

        assert res.exit_code == 0, res.output
        assert "merge_status: local" in res.output

    # --- TASK-586: Layer-0 legibility (unprotected-integration warning) -------

    def test_unprotected_warning_helper_unit(self) -> None:
        import cli.pr_commands as prc

        msg = prc._unprotected_warning("main")
        assert "main" in msg and "branch-guard" in msg and "GitHub ruleset" in msg

    def test_preflight_warns_on_unprotected_integration(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.pr_commands as prc

        self._add_bare_remote(repo, tmp_path)
        monkeypatch.setattr(prc, "_gh_ready", lambda: True)
        monkeypatch.setattr(prc, "_has_required_check", lambda r, b: False)
        res = runner.invoke(cli, ["pr", "preflight", "--repo", str(repo)])
        assert res.exit_code == 0, res.output  # pr_ok (remote+gh) — warning never hard-fails
        assert "unprotected_integration: True" in res.output
        assert "warning:" in res.output and "branch-guard" in res.output

    def test_preflight_no_warning_with_required_check(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.pr_commands as prc

        self._add_bare_remote(repo, tmp_path)
        monkeypatch.setattr(prc, "_gh_ready", lambda: True)
        monkeypatch.setattr(prc, "_has_required_check", lambda r, b: True)
        res = runner.invoke(cli, ["pr", "preflight", "--repo", str(repo)])
        assert "unprotected_integration: False" in res.output
        assert "warning:" not in res.output

    def test_preflight_no_warning_without_remote(self, runner: CliRunner, repo: Path) -> None:
        res = runner.invoke(cli, ["pr", "preflight", "--repo", str(repo)])
        assert res.exit_code == 1  # no remote → degraded-trunk
        assert "warning:" not in res.output  # local/no-forge mode, not an unprotected forge

    def test_submit_warns_on_unprotected_integration(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.pr_commands as prc

        self._add_bare_remote(repo, tmp_path)
        monkeypatch.delenv("COS_GIT_AUTONOMY", raising=False)  # draft
        monkeypatch.setattr(prc, "_gh_ready", lambda: True)
        monkeypatch.setattr(prc, "_has_required_check", lambda r, b: False)
        monkeypatch.setattr(prc, "_open_pr_count", lambda r, s: 0)
        self._fake_gh(prc, monkeypatch)
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "wip"], check=True
        )
        res = runner.invoke(cli, ["pr", "submit", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "warning:" in res.output and "branch-guard" in res.output

    def test_submit_local_rung_action_is_human_only(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.pr_commands as prc

        monkeypatch.setenv("COS_GIT_AUTONOMY", "local")
        self._fake_gh(prc, monkeypatch)
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "wip"], check=True
        )
        res = runner.invoke(cli, ["pr", "submit", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "HUMAN integrates" in res.output and "branch-guard-blocked" in res.output
        assert "git merge --no-ff" in res.output
        assert "pushed: False" in res.output
        assert "autonomy_level: local" in res.output
        # branch stays local — nothing was pushed (no remote even exists)
        assert "agents/adhoc/ses-test-abc" in self._branches(repo)

    def test_submit_resolves_worktree_when_session_differs(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-541: open under session A, then submit under a DIFFERENT session id
        # (the pid-fallback case). submit must resolve the real worktree+branch
        # from disk, not re-derive a session-B path that never existed.
        import cli.pr_commands as prc

        monkeypatch.setenv("COS_GIT_AUTONOMY", "local")  # commit-only — no remote needed
        self._fake_gh(prc, monkeypatch)

        monkeypatch.setenv("COS_AGENT_SESSION_ID", "ses-AAA")
        runner.invoke(cli, ["pr", "open", "--task", "TASK-777", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("TASK-777-ses-AAA"))
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "wip"], check=True
        )

        # submit under a different session id — must still find TASK-777-ses-AAA
        monkeypatch.setenv("COS_AGENT_SESSION_ID", "ses-BBB")
        res = runner.invoke(cli, ["pr", "submit", "--task", "TASK-777", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "branch: agents/TASK-777/ses-AAA" in res.output  # resolved from disk, not ses-BBB
        assert "merge_status: local" in res.output

    # --- TASK-542: cos pr self-reads git_settings from hub-settings.json --------
