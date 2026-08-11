"""cos pr — git_settings resolution and cleanup under session drift.

Part of tests/test_cli.py — collected via the aggregator, not directly.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from _cli_suite.pr_base import PrHarness
from _cli_suite.shared import cli


class TestCosPrSettings(PrHarness):
    """cos pr — git_settings resolution and cleanup under session drift."""

    def test_submit_reads_local_autonomy_from_settings_file(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # autonomy_level=local on disk + NO env var → submit takes the local path.
        import cli.pr_commands as prc

        monkeypatch.delenv("COS_GIT_AUTONOMY", raising=False)
        self._write_git_settings(repo, enabled=True, autonomy_level="local")
        self._fake_gh(prc, monkeypatch)  # any gh pr merge => AssertionError

        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "wip"], check=True
        )
        res = runner.invoke(cli, ["pr", "submit", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "merge_status: local" in res.output
        assert "pushed: False" in res.output
        assert "autonomy_level: local" in res.output

    def test_env_autonomy_overrides_settings_file(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Explicit env var wins over the file: file=local but env=auto_merge → not local.
        import cli.pr_commands as prc

        self._add_bare_remote(repo, tmp_path)
        self._write_git_settings(repo, enabled=True, autonomy_level="local")
        monkeypatch.setenv("COS_GIT_AUTONOMY", "auto_merge")
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
        assert "autonomy_level: auto_merge" in res.output  # env beat the file
        assert "pushed: True" in res.output
        assert len(merge_calls) == 1  # auto-merge armed — not the local path

    def test_open_reads_integration_branch_from_settings_file(
        self, runner: CliRunner, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # integration_branch=develop on disk + NO env var → worktree bases on develop.
        monkeypatch.delenv("COS_GIT_INTEGRATION_BRANCH", raising=False)
        subprocess.run(["git", "-C", str(repo), "branch", "develop"], check=True)
        self._write_git_settings(repo, enabled=True, integration_branch="develop")

        res = runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "integration: develop" in res.output

    def test_settings_resolve_from_main_repo_inside_worktree(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Run the helper with cwd INSIDE a linked worktree (repo arg = the worktree
        # path): --git-common-dir must resolve back to the MAIN repo's settings file.
        import cli.pr_commands as prc

        monkeypatch.delenv("COS_GIT_AUTONOMY", raising=False)
        self._write_git_settings(repo, enabled=True, autonomy_level="autonomous")
        wt = tmp_path / "linked-wt"
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "-q", "--detach", str(wt), "main"],
            check=True,
        )
        # repo arg is the worktree, but the settings live only in the MAIN repo
        assert not (wt / ".coding-os").exists()
        assert prc._autonomy_level(str(wt)) == "autonomous"
        assert Path(prc._main_repo_root(str(wt))).resolve() == repo.resolve()

    def test_cleanup_resolves_worktree_when_session_differs(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-541: cleanup under a different session id still removes the real
        # worktree+branch (no work yet => recoverable => removes).
        monkeypatch.setenv("COS_AGENT_SESSION_ID", "ses-AAA")
        runner.invoke(cli, ["pr", "open", "--task", "TASK-888", "--repo", str(repo)])
        assert "agents/TASK-888/ses-AAA" in self._branches(repo)

        monkeypatch.setenv("COS_AGENT_SESSION_ID", "ses-BBB")
        res = runner.invoke(cli, ["pr", "cleanup", "--task", "TASK-888", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "agents/TASK-888/ses-AAA" not in self._branches(repo)  # the real branch was removed

    def test_cleanup_refuses_live_peer_worktree_under_drift(
        self, runner: CliRunner, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Review finding 2: the single-candidate fallback can resolve a LIVE peer's
        # worktree (same task slug, different session). cleanup must refuse to destroy
        # it (no peer data-loss) when the owner session is provably live — but the
        # TASK-541 drift path (owner gone, "unknown") above still cleans up.
        import socket

        monkeypatch.setenv("COS_AGENT_SESSION_ID", "ses-AAA")
        runner.invoke(cli, ["pr", "open", "--task", "TASK-999", "--repo", str(repo)])
        assert "agents/TASK-999/ses-AAA" in self._branches(repo)

        # ses-AAA is provably live: a presence record carrying this (alive) pid + host.
        sess_dir = repo / ".coding-os" / "panel-x" / "sessions"
        sess_dir.mkdir(parents=True, exist_ok=True)
        (sess_dir / "ses-AAA.json").write_text(
            json.dumps({"pid": os.getpid(), "host": socket.gethostname()}), encoding="utf-8"
        )

        monkeypatch.setenv("COS_AGENT_SESSION_ID", "ses-BBB")
        res = runner.invoke(cli, ["pr", "cleanup", "--task", "TASK-999", "--repo", str(repo)])
        assert res.exit_code == 1, res.output
        assert "another live session" in res.output
        assert "agents/TASK-999/ses-AAA" in self._branches(repo)  # peer worktree NOT destroyed

    def test_cleanup_preserves_uncommitted_work_before_destroy_under_drift(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-561: a drifted/peer worktree with no presence record reads as "unknown"
        # (live-peer gate does NOT fire) and its committed branch is recoverable
        # (merge-gate passes) — so the OLD path force-removed it, wiping the
        # UNCOMMITTED file. cleanup must now bundle that dirty tree before destroying.
        monkeypatch.setenv("COS_REAPED_ROOT", str(tmp_path / "reaped"))
        monkeypatch.setenv("COS_AGENT_SESSION_ID", "ses-AAA")
        runner.invoke(cli, ["pr", "open", "--task", "TASK-777", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("TASK-777-ses-AAA"))
        (wt / "uncommitted.txt").write_text(
            "peer work at risk", encoding="utf-8"
        )  # dirty → must preserve

        monkeypatch.setenv("COS_AGENT_SESSION_ID", "ses-BBB")  # drift: different session id
        res = runner.invoke(cli, ["pr", "cleanup", "--task", "TASK-777", "--repo", str(repo)])
        assert res.exit_code == 0, res.output  # recoverable + preserved → still cleans up
        bundles = list((tmp_path / "reaped").rglob("*.bundle"))
        assert bundles, "uncommitted work must be bundled before the worktree is destroyed"
        # D2: the bundle tip must actually CONTAIN the preserved file, not just the old
        # branch tip — a bundle that captured nothing would still exist (TASK-565 / L).
        head_sha = subprocess.run(
            ["git", "-C", str(repo), "bundle", "list-heads", str(bundles[0])],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()[0]
        tree = subprocess.run(
            ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", head_sha],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "uncommitted.txt" in tree, f"bundle tip missing the preserved file; tree={tree!r}"

    def test_cleanup_keeps_worktree_when_drift_preservation_fails(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-561 / D2: if preservation fails on a drifted dirty worktree, cleanup must
        # KEEP the worktree (the only copy) and refuse — never destroy unpreserved work.
        import cli.pr_commands as prc

        monkeypatch.setattr(
            prc, "_preserve_reaped", lambda r, w, b: None
        )  # simulate bundle failure
        monkeypatch.setenv("COS_AGENT_SESSION_ID", "ses-AAA")
        runner.invoke(cli, ["pr", "open", "--task", "TASK-666", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("TASK-666-ses-AAA"))
        (wt / "uncommitted.txt").write_text("peer work at risk", encoding="utf-8")  # dirty

        monkeypatch.setenv("COS_AGENT_SESSION_ID", "ses-BBB")  # drift
        res = runner.invoke(cli, ["pr", "cleanup", "--task", "TASK-666", "--repo", str(repo)])
        assert res.exit_code == 1, res.output
        assert "preservation failed" in res.output
        assert "agents/TASK-666/ses-AAA" in self._branches(repo)  # worktree+branch KEPT
