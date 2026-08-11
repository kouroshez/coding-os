"""cos pr — worktree open, cleanup, and preflight degradation.

Part of tests/test_cli.py — collected via the aggregator, not directly.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from _cli_suite.pr_base import PrHarness
from _cli_suite.shared import cli


class TestCosPrLifecycle(PrHarness):
    """cos pr — worktree open, cleanup, and preflight degradation."""

    def test_open_adhoc_creates_worktree_and_branch(self, runner: CliRunner, repo: Path) -> None:
        res = runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "agents/adhoc/ses-test-abc" in self._branches(repo)
        assert "adhoc-ses-test-abc" in self._worktrees(repo)

    def test_open_task_namespaces_branch(self, runner: CliRunner, repo: Path) -> None:
        res = runner.invoke(cli, ["pr", "open", "--task", "TASK-999", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "agents/TASK-999/ses-test-abc" in self._branches(repo)

    def test_open_is_idempotent(self, runner: CliRunner, repo: Path) -> None:
        first = runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        second = runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        assert first.exit_code == 0, first.output
        assert second.exit_code == 0, second.output

    def test_open_worktree_lives_under_slugged_root(
        self, runner: CliRunner, repo: Path, tmp_path: Path
    ) -> None:
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt_root = tmp_path / "wt"
        # COS_WORKTREE_ROOT/<repo-slug>/adhoc-<session>
        slugged = [p for p in wt_root.iterdir() if p.is_dir() and p.name.startswith("repo-")]
        assert slugged, "worktree must live under a per-repo slug dir"
        assert (slugged[0] / "adhoc-ses-test-abc").is_dir()

    def test_cleanup_removes_worktree_and_branch(self, runner: CliRunner, repo: Path) -> None:
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        res = runner.invoke(cli, ["pr", "cleanup", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 0, res.output  # no work yet → recoverable → removes
        assert "agents/adhoc/ses-test-abc" not in self._branches(repo)
        assert "adhoc-ses-test-abc" not in self._worktrees(repo)

    # --- TASK-530: cleanup is merge-gated (no silent destruction of live work) --

    def test_cleanup_refuses_open_pr_without_force(
        self, runner: CliRunner, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_pr_state", lambda r, b: "open")
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        res = runner.invoke(cli, ["pr", "cleanup", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 1, res.output
        assert "pr_state: open" in res.output
        assert "agents/adhoc/ses-test-abc" in self._branches(repo)  # kept

    def test_cleanup_force_removes_open_pr(
        self, runner: CliRunner, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_pr_state", lambda r, b: "open")
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        res = runner.invoke(cli, ["pr", "cleanup", "--adhoc", "--force", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "agents/adhoc/ses-test-abc" not in self._branches(repo)

    def test_cleanup_removes_merged_pr(
        self, runner: CliRunner, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_pr_state", lambda r, b: "merged")
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        res = runner.invoke(cli, ["pr", "cleanup", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "agents/adhoc/ses-test-abc" not in self._branches(repo)

    def test_cleanup_refuses_unpushed_branch_with_no_pr(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: False)  # no gh => _pr_state "unknown"
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        # a local-only commit, never submitted/pushed — must be protected
        (wt / "x.txt").write_text("wip", encoding="utf-8")
        subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(wt), "commit", "-q", "-m", "wip"], check=True)
        res = runner.invoke(cli, ["pr", "cleanup", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 1, res.output
        assert "not on origin" in res.output
        assert "agents/adhoc/ses-test-abc" in self._branches(repo)  # kept

    def test_cleanup_bundles_merged_branch_with_unpushed_commits(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-566 H: a merged/closed branch with a CLEAN tree but unpushed local
        # commits used to skip BOTH gates (state not in none/unknown; tree not dirty)
        # and `branch -D` discarded the commits with no bundle. It must now bundle first.
        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_pr_state", lambda *a, **k: "merged")
        monkeypatch.setenv("COS_REAPED_ROOT", str(tmp_path / "reaped"))
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        (wt / "x.txt").write_text("wip", encoding="utf-8")  # local-only, unrecoverable
        subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(wt), "commit", "-q", "-m", "wip"], check=True)
        # tree is now CLEAN (committed) — the exact gap the old dirty-only preserve missed
        res = runner.invoke(cli, ["pr", "cleanup", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 0, res.output  # deletes (was silent loss)
        assert ".bundle" in res.output  # but the unpushed work was bundled first
        assert "agents/adhoc/ses-test-abc" not in self._branches(repo)  # removed

    def test_preflight_degrades_without_remote(self, runner: CliRunner, repo: Path) -> None:
        res = runner.invoke(cli, ["pr", "preflight", "--repo", str(repo)])
        assert res.exit_code == 1, res.output  # no remote => not pr_ok
        assert "degraded-trunk" in res.output

    def test_submit_degrades_without_capability(self, runner: CliRunner, repo: Path) -> None:
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        res = runner.invoke(cli, ["pr", "submit", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 1, res.output  # no remote/gh => degrade, not crash
        assert "degraded-trunk" in res.output

    def test_open_requires_git_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        not_a_repo = tmp_path / "plain"
        not_a_repo.mkdir()
        res = runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(not_a_repo)])
        assert res.exit_code != 0
        assert "git repository" in res.output

    # --- reaper (TASK-519) -------------------------------------------------
