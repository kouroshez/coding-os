"""cos pr — reaper concurrency, work preservation, and heal budget.

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


class TestCosPrReapRecovery(PrHarness):
    """cos pr — reaper concurrency, work preservation, and heal budget."""

    def test_reopen_refreshes_owner_stamp(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-594: `git worktree lock` no-ops on an already-locked tree, so an
        # idempotent re-open must unlock+relock to refresh the owner=<pid> stamp to
        # the (possibly restarted) session's current pid.
        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: False)
        sess_dir = repo / ".coding-os" / "claude" / "sessions"
        sess_dir.mkdir(parents=True, exist_ok=True)
        rec = sess_dir / "ses-test-abc.json"
        rec.write_text(json.dumps({"session_id": "ses-test-abc", "pid": 11111}), encoding="utf-8")
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        assert "owner=11111" in prc._worktree_lock_reason(str(repo), wt)
        rec.write_text(json.dumps({"session_id": "ses-test-abc", "pid": 22222}), encoding="utf-8")
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])  # idempotent re-open
        assert "owner=22222" in prc._worktree_lock_reason(str(repo), wt)  # stamp refreshed

    def test_reap_removes_dead_pid_session(
        self, runner: CliRunner, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A recorded pid that is no longer alive on this host is positive death
        # evidence → reaped (even with no ended_at).
        import time

        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: False)
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        sess_dir = repo / ".coding-os" / "claude" / "sessions"
        sess_dir.mkdir(parents=True, exist_ok=True)
        (sess_dir / "ses-test-abc.json").write_text(
            json.dumps(
                {
                    "session_id": "ses-test-abc",
                    "pid": 2147483646,
                    "last_tool_at": int(time.time()) - 9999,
                }
            ),
            encoding="utf-8",
        )
        res = runner.invoke(cli, ["pr", "reap", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "agents/adhoc/ses-test-abc" not in self._branches(repo)  # dead pid → reaped

    def test_reap_preserves_dead_pid_unpushed_work(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-535: a dead-pid orphan with a LOCAL-ONLY commit (not on origin) + an
        # uncommitted untracked file must be PRESERVED — bundled to the quarantine dir
        # — before the worktree+branch are GC'd. The old `_reap_one` destroyed both
        # unconditionally (the #1 data-loss risk); preservation is the safety net.
        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: False)  # no remote/gh in the test
        reaped_root = tmp_path / "reaped"
        monkeypatch.setenv("COS_REAPED_ROOT", str(reaped_root))
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        # a local-only commit (never pushed) + an untracked uncommitted file — the work at risk
        (wt / "feature.py").write_text("VALUE = 42\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(wt), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(wt), "commit", "-q", "-m", "feat: unpushed work"], check=True
        )
        (wt / "dirty.txt").write_text("uncommitted", encoding="utf-8")
        # positive death evidence: a recorded pid that is not alive on this host
        sess_dir = repo / ".coding-os" / "claude" / "sessions"
        sess_dir.mkdir(parents=True, exist_ok=True)
        (sess_dir / "ses-test-abc.json").write_text(
            json.dumps({"session_id": "ses-test-abc", "pid": 2147483646}), encoding="utf-8"
        )
        res = runner.invoke(cli, ["pr", "reap", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        # worktree GC'd (disposable) + branch deleted (work is safe in the bundle)...
        assert "adhoc-ses-test-abc" not in self._worktrees(repo)
        assert "agents/adhoc/ses-test-abc" not in self._branches(repo)
        # ...and the unpushed work is recoverable from the preserved bundle.
        bundles = list(reaped_root.rglob("*.bundle"))
        assert bundles, "reaper must preserve unpushed work as a bundle before GC"
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "fetch",
                str(bundles[0]),
                "refs/heads/agents/adhoc/ses-test-abc:refs/recovered/x",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        log = subprocess.run(
            ["git", "-C", str(repo), "log", "--oneline", "refs/recovered/x"],
            capture_output=True,
            text=True,
        ).stdout
        assert "unpushed work" in log  # the agent's local-only commit survived

    def test_has_required_check_scopes_cwd_to_repo(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # D4: the gh api call must run with cwd=repo so {owner}/{repo} resolves from
        # THIS repo's remote — a submit from another checkout would else probe the
        # wrong repo's branch protection.
        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: True)
        monkeypatch.setattr(
            prc,
            "_git_out",
            lambda args, **kw: "https://github.com/o/r.git" if "config" in args else "",
        )
        captured: dict[str, object] = {}

        def fake_run(args, **kw):
            if args[:2] == ["gh", "api"]:
                captured["cwd"] = kw.get("cwd")
                return subprocess.CompletedProcess(args, 0, "{}", "")
            return subprocess.CompletedProcess(args, 0, "", "")

        monkeypatch.setattr(prc, "_run", fake_run)
        assert prc._has_required_check(str(repo), "main") is True
        assert captured["cwd"] == str(repo)

    def test_preserve_reaped_returns_none_on_commit_failure(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # D2: if the capture commit fails, the dirty work never reaches the branch —
        # _preserve_reaped must return None (so the caller keeps the worktree) instead
        # of bundling only the old tip and reporting success.
        import cli.pr_commands as prc

        monkeypatch.setattr(
            prc, "_git_out", lambda args, **kw: "?? new.py" if args[:1] == ["status"] else ""
        )

        def fake_git(args, **kw):
            rc = 1 if "commit" in args else 0
            return subprocess.CompletedProcess(["git", *args], rc, "", "")

        monkeypatch.setattr(prc, "_git", fake_git)
        assert prc._preserve_reaped(str(repo), repo, "agents/x/y") is None

    def test_reap_keeps_worktree_when_preservation_fails(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # D2: when preservation fails on a dead orphan with dirty work, the worktree may
        # hold the ONLY copy — it must be KEPT (not force-removed), flagged needs_attention.
        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: False)
        monkeypatch.setattr(prc, "_preserve_reaped", lambda r, w, b: None)  # simulate failure
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        (wt / "dirty.txt").write_text(
            "uncommitted work at risk", encoding="utf-8"
        )  # dirty → preserve needed
        sess_dir = repo / ".coding-os" / "claude" / "sessions"
        sess_dir.mkdir(parents=True, exist_ok=True)
        (sess_dir / "ses-test-abc.json").write_text(
            json.dumps({"session_id": "ses-test-abc", "pid": 2147483646}), encoding="utf-8"
        )
        res = runner.invoke(cli, ["pr", "reap", "--repo", str(repo), "--json"])
        assert res.exit_code == 0, res.output
        entry = json.loads(res.output)["detail"][0]
        assert entry["worktree_removed"] is False and entry["needs_attention"] is True
        assert "adhoc-ses-test-abc" in self._worktrees(repo)  # worktree KEPT on disk
        assert "agents/adhoc/ses-test-abc" in self._branches(repo)  # branch KEPT

    def test_pr_close_keeps_entry_when_list_fails(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # review finding 1: a failed `gh pr list` (timeout rc!=0, empty stdout) must
        # NOT be read as "no open PR" — _pr_close returns False so the ledger entry
        # is kept for a later retry instead of silently dropped (PR leak).
        import cli.pr_commands as prc

        def fake_run(args, **kw):
            if args[:3] == ["gh", "pr", "list"]:
                return subprocess.CompletedProcess(args, 124, "", "timed out")
            return subprocess.CompletedProcess(args, 0, "", "")

        monkeypatch.setattr(prc, "_run", fake_run)
        assert prc._pr_close(str(repo), "agents/x/y") is False

    def test_reap_keeps_live_session_worktree(
        self, runner: CliRunner, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import time

        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: False)
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        sess_dir = repo / ".coding-os" / "claude" / "sessions"
        sess_dir.mkdir(parents=True, exist_ok=True)
        (sess_dir / "ses-test-abc.json").write_text(
            json.dumps(
                {"session_id": "ses-test-abc", "last_tool_at": int(time.time()), "pid": os.getpid()}
            )
        )
        res = runner.invoke(cli, ["pr", "reap", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "agents/adhoc/ses-test-abc" in self._branches(repo)  # live → kept

    def test_reap_drains_cleanup_ledger(
        self, runner: CliRunner, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: False)
        ledger = repo / ".coding-os" / ".pr-cleanup-ledger.json"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            json.dumps(
                [{"branch": "agents/old/dead", "remote_pending": False, "pr_pending": False}]
            )
        )
        res = runner.invoke(cli, ["pr", "reap", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert json.loads(ledger.read_text()) == []  # completable entry drained

    # --- self-heal budget + circuit-breaker (TASK-520) ---------------------

    def test_heal_budget_escalates_after_max(
        self, runner: CliRunner, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("COS_PR_HEAL_MAX", "2")
        ok1 = runner.invoke(cli, ["pr", "heal", "--adhoc", "--repo", str(repo)])
        ok2 = runner.invoke(cli, ["pr", "heal", "--adhoc", "--repo", str(repo)])
        boom = runner.invoke(cli, ["pr", "heal", "--adhoc", "--repo", str(repo)])
        assert ok1.exit_code == 0 and "1/2" in ok1.output
        assert ok2.exit_code == 0 and "2/2" in ok2.output
        # 3rd attempt exceeds the budget → escalate + non-zero "stop" signal.
        assert boom.exit_code == 2, boom.output
        assert "escalated" in boom.output.lower()
        budget = json.loads((repo / ".coding-os" / ".pr-heal-budget.json").read_text())
        assert budget["agents/adhoc/ses-test-abc"] == 3
