"""cos pr — the dogfood loop, worktree bootstrap, and review-gated auto-merge.

Part of tests/test_cli.py — collected via the aggregator, not directly.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from _cli_suite.pr_base import PrHarness
from _cli_suite.shared import cli


class TestCosPrBootstrap(PrHarness):
    """cos pr — the dogfood loop, worktree bootstrap, and review-gated auto-merge."""

    def test_dogfood_full_pr_loop(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """isolate → work → rebase+push → cleanup on a real fixture repo + bare
        remote, with coding-os itself never flipping to pr-mode. The PR/auto-merge
        steps degrade gracefully (no GitHub behind the bare remote)."""
        import cli.pr_commands as prc

        self._add_bare_remote(repo, tmp_path)
        monkeypatch.setattr(prc, "_gh_ready", lambda: True)  # reach the push path
        monkeypatch.setattr(prc, "_has_required_check", lambda r, b: False)
        monkeypatch.setattr(prc, "_open_pr_count", lambda r, s: 0)

        # isolate
        opened = runner.invoke(cli, ["pr", "open", "--task", "TASK-DOG", "--repo", str(repo)])
        assert opened.exit_code == 0, opened.output
        assert "agents/TASK-DOG/ses-test-abc" in self._branches(repo)
        wt = next((tmp_path / "wt").rglob("TASK-DOG-ses-test-abc"))

        # work + commit inside the isolated worktree
        (wt / "feature.txt").write_text("done", encoding="utf-8")
        subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(wt), "commit", "-q", "-m", "feat: dogfood"], check=True)

        # publish — rebase onto FETCH_HEAD + lease push reach the remote; the gh
        # PR step degrades (no GitHub), but submit must not crash.
        submitted = runner.invoke(cli, ["pr", "submit", "--task", "TASK-DOG", "--repo", str(repo)])
        assert submitted.exit_code == 0, submitted.output
        on_remote = subprocess.run(
            ["git", "-C", str(repo), "ls-remote", "origin", "agents/TASK-DOG/ses-test-abc"],
            capture_output=True,
            text=True,
        ).stdout
        assert "agents/TASK-DOG/ses-test-abc" in on_remote, (
            "branch must reach the integration remote"
        )

        # cleanup — no orphan worktree or local branch left behind
        cleaned = runner.invoke(cli, ["pr", "cleanup", "--task", "TASK-DOG", "--repo", str(repo)])
        assert cleaned.exit_code == 0, cleaned.output
        assert "agents/TASK-DOG/ses-test-abc" not in self._branches(repo)
        assert "TASK-DOG-ses-test-abc" not in self._worktrees(repo)

    # --- TASK-593: worktree dependency/secret bootstrap -----------------------

    def test_open_no_bootstrap_config_is_noop(
        self, runner: CliRunner, repo: Path, tmp_path: Path
    ) -> None:
        # No worktree_include / worktree_setup_cmd → byte-identical to today.
        (repo / "node_modules").mkdir()
        res = runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "bootstrap: (none)" in res.output
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        assert not (wt / "node_modules").exists()  # nothing linked without config

    def test_open_bootstrap_symlinks_includes_and_runs_setup(
        self, runner: CliRunner, repo: Path, tmp_path: Path
    ) -> None:
        # Declared gitignored paths are symlinked in + the setup command runs.
        (repo / "node_modules").mkdir()
        (repo / "node_modules" / "pkg").write_text("dep", encoding="utf-8")
        (repo / ".env").write_text("SECRET=1", encoding="utf-8")
        self._write_git_settings(
            repo,
            enabled=True,
            worktree_include=["node_modules", ".env"],
            worktree_setup_cmd="touch .setup-done",
        )
        res = runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        assert (wt / "node_modules").is_symlink()
        assert (wt / ".env").is_symlink()
        assert (wt / "node_modules" / "pkg").read_text() == "dep"  # link resolves
        assert (wt / ".setup-done").exists()  # setup command ran in the worktree
        assert "setup=ok" in res.output

    def test_open_bootstrapped_symlink_does_not_leak_into_pr(
        self, runner: CliRunner, repo: Path, tmp_path: Path
    ) -> None:
        # Regression: a symlink named after a trailing-slash gitignore pattern
        # (node_modules/) is NOT matched by it and would otherwise show as untracked
        # in the worktree → leak into the PR. The worktree exclude entry prevents it.
        (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "gitignore"], check=True)
        (repo / "node_modules").mkdir()
        (repo / "node_modules" / "pkg").write_text("dep", encoding="utf-8")
        self._write_git_settings(repo, enabled=True, worktree_include=["node_modules"])

        res = runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        assert (wt / "node_modules").is_symlink()
        status = subprocess.run(
            ["git", "-C", str(wt), "status", "--porcelain"], capture_output=True, text=True
        ).stdout
        assert "node_modules" not in status, f"linked dep leaked into the worktree: {status!r}"

    def test_open_bootstrap_ignores_path_traversal(
        self, runner: CliRunner, repo: Path, tmp_path: Path
    ) -> None:
        # Containment: an absolute or .. include path is skipped, never linked out.
        (repo / "node_modules").mkdir()
        self._write_git_settings(
            repo, enabled=True, worktree_include=["../escape", "/etc/passwd", "node_modules"]
        )
        res = runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        assert not (wt.parent / "escape").exists()  # no link escaped the worktree
        assert (wt / "node_modules").is_symlink()  # the safe one still linked
        assert "linked=node_modules" in res.output

    # --- TASK-592: review-required is a distinct signal, not silent auto-merge ---

    def test_rollup_state_review_required_overrides_passing(self) -> None:
        import cli.pr_commands as prc

        green = [{"conclusion": "SUCCESS", "status": "COMPLETED"}]
        armed = {
            "state": "OPEN",
            "statusCheckRollup": green,
            "autoMergeRequest": {"enabledAt": "x"},
        }
        # Green + auto-merge armed, but the review gate is still open → review-required.
        assert (
            prc._rollup_state({**armed, "reviewDecision": "REVIEW_REQUIRED"}) == "review-required"
        )
        assert (
            prc._rollup_state({**armed, "reviewDecision": "CHANGES_REQUESTED"}) == "review-required"
        )
        # No review gate (approved / not required) → unchanged passing signal.
        assert prc._rollup_state({**armed, "reviewDecision": "APPROVED"}) == "passing"
        assert prc._rollup_state({**armed, "reviewDecision": None}) == "passing"

    def test_submit_auto_merge_armed_awaiting_review(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # auto_merge + required check + a required REVIEW: arming is correct (it lands
        # once approved) but submit must surface the human-approval gate, not "will merge".
        import cli.pr_commands as prc

        self._add_bare_remote(repo, tmp_path)
        monkeypatch.setenv("COS_GIT_AUTONOMY", "auto_merge")
        monkeypatch.setattr(prc, "_gh_ready", lambda: True)
        monkeypatch.setattr(prc, "_has_required_check", lambda r, b: True)
        monkeypatch.setattr(prc, "_open_pr_count", lambda r, s: 0)
        merge_calls: list = []
        self._fake_gh(prc, monkeypatch, merge_calls=merge_calls, review_decision="REVIEW_REQUIRED")

        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "wip"], check=True
        )
        res = runner.invoke(cli, ["pr", "submit", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "merge_status: auto-merge-armed-awaiting-review" in res.output
        assert "review_required: True" in res.output
        assert len(merge_calls) == 1  # auto-merge IS armed — it merges once approved
        assert "approve" in res.output.lower()  # action tells a human to approve

    def test_submit_auto_merge_armed_no_review_is_unchanged(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Regression: with NO review gate the normal armed path is byte-for-byte intact.
        import cli.pr_commands as prc

        self._add_bare_remote(repo, tmp_path)
        monkeypatch.setenv("COS_GIT_AUTONOMY", "auto_merge")
        monkeypatch.setattr(prc, "_gh_ready", lambda: True)
        monkeypatch.setattr(prc, "_has_required_check", lambda r, b: True)
        monkeypatch.setattr(prc, "_open_pr_count", lambda r, s: 0)
        merge_calls: list = []
        self._fake_gh(prc, monkeypatch, merge_calls=merge_calls, review_decision=None)

        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "wip"], check=True
        )
        res = runner.invoke(cli, ["pr", "submit", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "merge_status: auto-merge-armed" in res.output
        assert "awaiting-review" not in res.output
        assert "review_required: False" in res.output
