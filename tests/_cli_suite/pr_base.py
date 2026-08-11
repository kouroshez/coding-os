"""Shared harness for the cos pr suites — part of tests/test_cli.py.

Every TestCosPr* class inherits this; it owns the throwaway git repo fixture
and the static helpers those suites call through `self`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from _cli_suite.shared import cli


class PrHarness:
    """Throwaway git repo plus the git/gh probes the cos pr suites share."""

    @staticmethod
    def _init_repo(path: Path) -> None:
        run = lambda *a: subprocess.run(  # noqa: E731 — terse local test helper
            ["git", "-C", str(path), *a], check=True, capture_output=True, text=True
        )
        subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
        run("config", "user.email", "t@t")
        run("config", "user.name", "t")
        (path / "README.md").write_text("x", encoding="utf-8")
        run("add", "-A")
        run("commit", "-q", "-m", "init")

    @pytest.fixture
    def repo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        r = tmp_path / "repo"
        r.mkdir()
        self._init_repo(r)
        monkeypatch.setenv("COS_WORKTREE_ROOT", str(tmp_path / "wt"))
        monkeypatch.setenv("COS_AGENT_SESSION_ID", "ses-test-abc")
        monkeypatch.delenv("COS_PANEL_DIR", raising=False)
        return r

    @staticmethod
    def _branches(repo: Path) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), "branch", "--list", "agents/*"],
            capture_output=True,
            text=True,
        ).stdout

    @staticmethod
    def _worktrees(repo: Path) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), "worktree", "list"], capture_output=True, text=True
        ).stdout

    @staticmethod
    def _add_bare_remote(repo: Path, tmp_path: Path) -> None:
        bare = tmp_path / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
        g = ["git", "-C", str(repo)]
        subprocess.run([*g, "remote", "add", "origin", str(bare)], check=True)
        subprocess.run([*g, "push", "-q", "origin", "main"], check=True)

    def test_submit_circuit_breaker_caps_open_prs(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.pr_commands as prc

        self._add_bare_remote(repo, tmp_path)
        monkeypatch.setattr(prc, "_gh_ready", lambda: True)  # pretend gh is ready
        monkeypatch.setattr(prc, "_has_required_check", lambda r, b: False)
        monkeypatch.setattr(prc, "_open_pr_count", lambda r, s: 5)  # already at the cap
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "wip"], check=True
        )
        res = runner.invoke(cli, ["pr", "submit", "--adhoc", "--repo", str(repo)])
        assert res.exit_code == 1, res.output  # breaker open → refuse BEFORE pushing (finding 9)
        assert "circuit_breaker" in res.output and "open" in res.output
        # the breaker is checked before the push, so nothing was pushed
        assert "pushed: False" in res.output

    # --- TASK-527: no-required-check repo must NOT silently strand a PR -------
    @staticmethod
    def _fake_gh(prc, monkeypatch, *, merge_calls: list | None = None, review_decision=None):
        """Route `gh pr create`/`merge`/`view` to fakes, real subprocess for git."""
        real_run = prc._run

        def fake_run(args, **kw):
            if args[:3] == ["gh", "pr", "create"]:
                return subprocess.CompletedProcess(args, 0, stdout="https://gh/pr/1\n", stderr="")
            if args[:3] == ["gh", "pr", "merge"]:
                if merge_calls is None:
                    raise AssertionError("auto-merge must NOT arm without a required check")
                merge_calls.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
            if args[:3] == ["gh", "pr", "view"]:
                body = json.dumps({"reviewDecision": review_decision})
                return subprocess.CompletedProcess(args, 0, stdout=body, stderr="")
            return real_run(args, **kw)

        monkeypatch.setattr(prc, "_run", fake_run)

    @staticmethod
    def _write_git_settings(repo: Path, **git_settings: object) -> None:
        # The Hub writes this; the CLI shell never receives COS_GIT_* (cos-env.sh
        # exports those only into hook subprocesses), so submit/open must self-read.
        state = repo / ".coding-os"
        state.mkdir(parents=True, exist_ok=True)
        (state / "hub-settings.json").write_text(
            json.dumps({"git_settings": git_settings}), encoding="utf-8"
        )

    @staticmethod
    def _mk_agent_branch(
        repo: Path, tmp_path: Path, branch: str, committed: dict[str, str]
    ) -> Path:
        wt = tmp_path / "wts" / branch.replace("/", "-")
        wt.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "-b", branch, str(wt), "main"],
            check=True,
            capture_output=True,
            text=True,
        )
        for name, content in committed.items():
            (wt / name).write_text(content, encoding="utf-8")
        if committed:
            subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(wt),
                    "-c",
                    "user.email=t@t",
                    "-c",
                    "user.name=t",
                    "commit",
                    "-q",
                    "-m",
                    f"work {branch}",
                ],
                check=True,
            )
        return wt
