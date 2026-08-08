"""Part of tests/test_cli.py — collected via the aggregator, not directly."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from _cli_suite.shared import (
    cli,
)


class TestCosPr:
    """cos pr executor — worktree isolation, idempotency, capability degrade (TASK-517)."""

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

    def test_reap_removes_offline_session_worktree(
        self, runner: CliRunner, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: False)  # no network in the test
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        assert "agents/adhoc/ses-test-abc" in self._branches(repo)
        # A presence record that positively says offline (ended) => reaped.
        sess_dir = repo / ".coding-os" / "claude" / "sessions"
        sess_dir.mkdir(parents=True, exist_ok=True)
        (sess_dir / "ses-test-abc.json").write_text(
            json.dumps({"session_id": "ses-test-abc", "ended_at": 1}), encoding="utf-8"
        )
        res = runner.invoke(cli, ["pr", "reap", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "agents/adhoc/ses-test-abc" not in self._branches(repo)
        assert "adhoc-ses-test-abc" not in self._worktrees(repo)

    def test_reap_keeps_session_without_presence_record(
        self, runner: CliRunner, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Fail-safe (finding 1): a FRESH worktree with no matching presence record
        # must NOT be reaped — absence of a record is not proof of death.
        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: False)
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        res = runner.invoke(cli, ["pr", "reap", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "agents/adhoc/ses-test-abc" in self._branches(repo)  # fresh + no record → kept
        assert "adhoc-ses-test-abc" in self._worktrees(repo)

    def test_reap_removes_stale_no_record_orphan(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # finding 2: a no-presence-record orphan IS reaped once its worktree is idle
        # past COS_PR_ORPHAN_MAX_AGE — so crashed/hookless orphans don't leak forever.
        # Staleness is the NEWEST file mtime in the tree, so age every file (not just
        # the top-level dir, which is blind to nested edits).
        import time

        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: False)
        monkeypatch.setenv("COS_PR_ORPHAN_MAX_AGE", "1")  # 1s staleness threshold
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        old = time.time() - 3600
        for path in [wt, *wt.rglob("*")]:
            try:
                os.utime(path, (old, old))  # age the WHOLE tree past the threshold
            except OSError:
                pass
        res = runner.invoke(cli, ["pr", "reap", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "agents/adhoc/ses-test-abc" not in self._branches(repo)  # stale + no record → reaped

    def test_reap_keeps_pid_alive_but_idle_session(
        self, runner: CliRunner, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # finding D5-1: session_presence() reports "offline" for a PID-alive agent
        # idle >30min (a long build / model turn), but that is NOT death — the reaper
        # must KEEP it. Reaping on the idle pill destroys live uncommitted work.
        import time

        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: False)
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        sess_dir = repo / ".coding-os" / "claude" / "sessions"
        sess_dir.mkdir(parents=True, exist_ok=True)
        stale = int(time.time()) - 9999  # well past PRESENT_WINDOW_SECS → presence "offline"
        (sess_dir / "ses-test-abc.json").write_text(
            json.dumps(
                {
                    "session_id": "ses-test-abc",
                    "pid": os.getpid(),  # alive
                    "last_tool_at": stale,
                    "last_prompt_at": stale,
                    "started_at": stale,
                }
            ),
            encoding="utf-8",
        )
        res = runner.invoke(cli, ["pr", "reap", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "agents/adhoc/ses-test-abc" in self._branches(repo)  # alive pid → kept

    def test_reap_keeps_no_record_orphan_with_fresh_subdir_edit(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # finding D5-2: the age fallback must track activity by the NEWEST file mtime,
        # not the top-level dir mtime (which never moves on nested src/** edits). A
        # no-record orphan with a fresh nested file is a live agent → KEEP it.
        import time

        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: False)
        monkeypatch.setenv("COS_PR_ORPHAN_MAX_AGE", "1")
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        old = time.time() - 3600
        for path in [wt, *wt.rglob("*")]:
            try:
                os.utime(path, (old, old))  # age the ENTIRE tree (top dir + every file)...
            except OSError:
                pass
        nested = wt / "src" / "deep"
        nested.mkdir(parents=True, exist_ok=True)
        (nested / "live.py").write_text(
            "x = 1\n", encoding="utf-8"
        )  # ...but one nested edit is fresh
        res = runner.invoke(cli, ["pr", "reap", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "agents/adhoc/ses-test-abc" in self._branches(repo)  # fresh nested edit → kept

    def test_reap_keeps_stale_orphan_when_lock_owner_alive(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-591: a stale, presence-less worktree whose lock reason still names a
        # LIVE owner pid (stamped at `pr open` from the then-present presence record)
        # must NOT be reaped — the owner agent is alive, its record just rotated away.
        import socket
        import time

        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: False)
        monkeypatch.setenv("COS_PR_ORPHAN_MAX_AGE", "1")
        sess_dir = repo / ".coding-os" / "claude" / "sessions"
        sess_dir.mkdir(parents=True, exist_ok=True)
        rec = sess_dir / "ses-test-abc.json"
        rec.write_text(  # PRESENT at open → `pr open` stamps owner=<pid>@<host>
            json.dumps(
                {"session_id": "ses-test-abc", "pid": os.getpid(), "host": socket.gethostname()}
            ),
            encoding="utf-8",
        )
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        rec.unlink()  # record rotates away → _session_state == "unknown"
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        old = time.time() - 3600
        for path in [wt, *wt.rglob("*")]:
            try:
                os.utime(path, (old, old))  # whole tree age-stale
            except OSError:
                pass
        res = runner.invoke(cli, ["pr", "reap", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "agents/adhoc/ses-test-abc" in self._branches(repo)  # live lock-owner → kept

    def test_reap_removes_stale_orphan_when_lock_owner_dead(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-591: a DEAD owner pid in the lock reason is no reason to keep — a
        # stale presence-less worktree is reaped exactly as it would be with no stamp.
        import socket
        import time

        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: False)
        monkeypatch.setenv("COS_PR_ORPHAN_MAX_AGE", "1")
        sess_dir = repo / ".coding-os" / "claude" / "sessions"
        sess_dir.mkdir(parents=True, exist_ok=True)
        rec = sess_dir / "ses-test-abc.json"
        rec.write_text(  # dead pid stamped at open (2147483646 is never alive)
            json.dumps(
                {"session_id": "ses-test-abc", "pid": 2147483646, "host": socket.gethostname()}
            ),
            encoding="utf-8",
        )
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        rec.unlink()
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        old = time.time() - 3600
        for path in [wt, *wt.rglob("*")]:
            with contextlib.suppress(OSError):
                os.utime(path, (old, old))
        res = runner.invoke(cli, ["pr", "reap", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "agents/adhoc/ses-test-abc" not in self._branches(repo)  # dead owner → reaped

    def test_reap_keeps_stale_orphan_with_non_ascii_host_in_lock(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-594: `git worktree list --porcelain` C-quotes a reason that carries a
        # non-ASCII host, so _lock_owner_alive must key on the ASCII pid (not the
        # quoted host) to still recognise the live owner and keep the worktree.
        import time

        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: False)
        monkeypatch.setenv("COS_PR_ORPHAN_MAX_AGE", "1")
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        subprocess.run(["git", "-C", str(repo), "worktree", "unlock", str(wt)], check=False)
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "worktree",
                "lock",
                str(wt),
                "--reason",
                f"pr-mode session ses-test-abc owner={os.getpid()}@café-höst",
            ],
            check=True,
        )
        old = time.time() - 3600
        for path in [wt, *wt.rglob("*")]:
            with contextlib.suppress(OSError):
                os.utime(path, (old, old))
        res = runner.invoke(cli, ["pr", "reap", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "agents/adhoc/ses-test-abc" in self._branches(repo)  # live pid parsed past the quote

    def test_reap_lists_worktrees_once_per_sweep(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-617: the sweep must run `git worktree list` ONCE, not once per candidate.
        # The old _lock_owner_alive forked the full porcelain list per unknown+stale
        # worktree → O(K·N) on a path pr-reap.sh backgrounds at every SessionStart.
        import time

        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: False)
        monkeypatch.setenv("COS_PR_ORPHAN_MAX_AGE", "1")
        for sid in ("ses-test-1", "ses-test-2", "ses-test-3"):
            monkeypatch.setenv("COS_AGENT_SESSION_ID", sid)
            runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        old = time.time() - 3600
        for wt in (tmp_path / "wt").rglob("adhoc-ses-test-*"):
            for path in [wt, *wt.rglob("*")]:
                with contextlib.suppress(OSError):
                    os.utime(path, (old, old))
        counts = {"wl": 0}
        real_git_out = prc._git_out

        def counting(args, **kw):
            if args[:2] == ["worktree", "list"]:
                counts["wl"] += 1
            return real_git_out(args, **kw)

        monkeypatch.setattr(prc, "_git_out", counting)
        res = runner.invoke(cli, ["pr", "reap", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert counts["wl"] == 1, (
            f"expected ONE worktree-list call for the sweep, got {counts['wl']}"
        )

    def test_reap_removes_stale_orphan_with_foreign_host_owner(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-617: owner liveness is host-local. A lock reason whose owner pid is
        # stamped on a FOREIGN host is no proof of life here — even when that pid number
        # is alive on THIS host (os.getpid()) — so the stale orphan is still reaped.
        import time

        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: False)
        monkeypatch.setenv("COS_PR_ORPHAN_MAX_AGE", "1")
        runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        wt = next((tmp_path / "wt").rglob("adhoc-ses-test-abc"))
        subprocess.run(["git", "-C", str(repo), "worktree", "unlock", str(wt)], check=False)
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "worktree",
                "lock",
                str(wt),
                "--reason",
                f"pr-mode session ses-test-abc owner={os.getpid()}@some-foreign-host",
            ],
            check=True,
        )
        old = time.time() - 3600
        for path in [wt, *wt.rglob("*")]:
            with contextlib.suppress(OSError):
                os.utime(path, (old, old))
        res = runner.invoke(cli, ["pr", "reap", "--repo", str(repo)])
        assert res.exit_code == 0, res.output
        assert "agents/adhoc/ses-test-abc" not in self._branches(repo)  # foreign host → reaped

    def test_concurrency_stress_reaper_no_double_reap_no_lost_work(
        self, runner: CliRunner, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # TASK-620: N threads hammering the reaper concurrently must (via the flock)
        # reap each orphan at most once, leave no orphan branch, write no duplicate
        # ledger entry, and never lose an unpushed commit (bundle-preserved first).
        import threading
        import time

        import cli.pr_commands as prc

        monkeypatch.setattr(prc, "_gh_ready", lambda: False)
        monkeypatch.setenv("COS_PR_ORPHAN_MAX_AGE", "1")
        monkeypatch.setenv("COS_REAPED_ROOT", str(tmp_path / "reaped"))
        monkeypatch.setattr(prc, "_emit", lambda *a, **k: None)  # silence stdout across threads

        sessions = ["ses-s1", "ses-s2", "ses-s3"]
        for sid in sessions:  # set up 3 offline orphan worktrees, distinct sessions
            monkeypatch.setenv("COS_AGENT_SESSION_ID", sid)
            runner.invoke(cli, ["pr", "open", "--adhoc", "--repo", str(repo)])
        precious_wt = next((tmp_path / "wt").rglob("adhoc-ses-s1"))
        subprocess.run(  # ses-s1 carries an unpushed commit that must NOT be lost
            ["git", "-C", str(precious_wt), "commit", "-q", "--allow-empty", "-m", "precious work"],
            check=True,
        )
        old = time.time() - 3600
        for wt in (tmp_path / "wt").rglob("adhoc-ses-s*"):
            for p in [wt, *wt.rglob("*")]:
                with contextlib.suppress(OSError):
                    os.utime(p, (old, old))

        errors: list[str] = []

        def worker(idx: int) -> None:
            time.sleep(0.001 * (idx % 3))  # fixed, deterministic stagger
            try:
                prc.pr_reap.callback(str(repo), False, False)  # raw fn, not the Click wrapper
            except Exception as exc:
                errors.append(repr(exc))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, errors  # no thread crashed under contention
        assert not any(t.is_alive() for t in threads)  # all finished within 30s
        remaining = [b for b in self._branches(repo).splitlines() if "adhoc-ses-s" in b]
        assert not remaining, remaining  # every orphan reaped, none left
        # the unpushed commit was bundle-preserved exactly (no lost work)
        bundles = list((tmp_path / "reaped").rglob("*ses-s1*.bundle"))
        assert bundles, "ses-s1's unpushed commit was not preserved"
        # ledger holds no duplicate (branch) entry — no double-reap bookkeeping
        ledger = prc._ledger_load(str(repo))
        branches = [e.get("branch") for e in ledger]
        assert len(branches) == len(set(branches)), ledger

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

    @staticmethod
    def _write_git_settings(repo: Path, **git_settings: object) -> None:
        # The Hub writes this; the CLI shell never receives COS_GIT_* (cos-env.sh
        # exports those only into hook subprocesses), so submit/open must self-read.
        state = repo / ".coding-os"
        state.mkdir(parents=True, exist_ok=True)
        (state / "hub-settings.json").write_text(
            json.dumps({"git_settings": git_settings}), encoding="utf-8"
        )

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
        import os
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
