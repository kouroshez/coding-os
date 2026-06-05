"""Tests for cos_wait_for_git_index_lock (TASK-170).

The helper must: return immediately when no lock is held; wait out a fresh
lock held by a concurrent commit and proceed once it clears; and reap a
VERIFIED-stale lock (old mtime) exactly once — never blocking the commit.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

HELPER = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "core"
    / "hooks"
    / "_helpers"
    / "git_index_lock.sh"
)


def _git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def _run(snippet: str, cwd: Path, timeout: int = 20) -> subprocess.CompletedProcess:
    script = f'source "{HELPER}"\n{snippet}'
    return subprocess.run(
        ["bash", "-c", script], cwd=cwd, capture_output=True, text=True, timeout=timeout
    )


def test_no_lock_returns_immediately(tmp_path):
    repo = _git_repo(tmp_path)
    start = time.monotonic()
    res = _run('cos_wait_for_git_index_lock; echo "rc=$?"', repo)
    assert "rc=0" in res.stdout
    assert time.monotonic() - start < 2


def test_stale_lock_is_reaped(tmp_path):
    repo = _git_repo(tmp_path)
    lock = repo / ".git" / "index.lock"
    lock.write_text("")
    old = time.time() - 60
    os.utime(lock, (old, old))
    start = time.monotonic()
    _run("cos_wait_for_git_index_lock", repo)
    assert not lock.exists(), "stale lock should be reaped"
    assert time.monotonic() - start < 3


def test_fresh_lock_waits_then_proceeds(tmp_path):
    repo = _git_repo(tmp_path)
    lock = repo / ".git" / "index.lock"
    lock.write_text("")  # fresh mtime
    # A concurrent commit releases the lock after ~0.6s.
    snippet = '( sleep 0.6; rm -f .git/index.lock ) & cos_wait_for_git_index_lock; echo "rc=$?"'
    start = time.monotonic()
    res = _run(snippet, repo)
    elapsed = time.monotonic() - start
    assert "rc=0" in res.stdout
    assert not lock.exists(), "lock should be cleared by the concurrent op"
    assert 0.4 < elapsed < 5, f"should wait ~0.6s, not the 10s ceiling: {elapsed:.1f}s"
