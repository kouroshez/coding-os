"""cos pr — reaping abandoned worktrees without destroying live work.

Part of tests/test_cli.py — collected via the aggregator, not directly.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from _cli_suite.pr_base import PrHarness
from _cli_suite.shared import cli


class TestCosPrReap(PrHarness):
    """cos pr — reaping abandoned worktrees without destroying live work."""

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
            with contextlib.suppress(OSError):
                os.utime(path, (old, old))  # age the WHOLE tree past the threshold
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
            with contextlib.suppress(OSError):
                os.utime(path, (old, old))  # age the ENTIRE tree (top dir + every file)...
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
            with contextlib.suppress(OSError):
                os.utime(path, (old, old))  # whole tree age-stale
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
