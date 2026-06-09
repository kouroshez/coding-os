"""Regression tests for the pre-commit batch hook runner (TASK-058).

The deadlock: a delegate hook that backgrounds a grandchild leaves that
grandchild holding the captured stdout/stderr pipe write-end, so reading the
pipe to EOF blocked until the grandchild died — every staged file paid the
full timeout and a 15+-file commit ground on for minutes (holding
.git/index.lock). The fix redirects the delegate's stdio to temp FILES (no
EOF reader) and wait()s on the direct child only, so a backgrounded
grandchild no longer stalls the runner; a genuinely-hung DIRECT child is
still SIGKILLed by group on timeout.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

_HELPER = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "core"
    / "hooks"
    / "_helpers"
    / "pre_commit_batch.py"
)

_spec = importlib.util.spec_from_file_location("pre_commit_batch", _HELPER)
pre_commit_batch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pre_commit_batch)


def _write_hook(tmp_path: Path, name: str, body: str) -> Path:
    hook = tmp_path / name
    hook.write_text("#!/usr/bin/env bash\n" + body)
    hook.chmod(0o755)
    return hook


def test_fast_hook_returns_exit_code_and_output(tmp_path: Path) -> None:
    hook = _write_hook(tmp_path, "ok.sh", "echo hello; exit 0\n")
    code, out = pre_commit_batch._run_hook(hook, "{}")
    assert code == 0
    assert "hello" in out


def test_blocking_hook_propagates_exit_2(tmp_path: Path) -> None:
    hook = _write_hook(tmp_path, "block.sh", "echo nope >&2; exit 2\n")
    code, out = pre_commit_batch._run_hook(hook, "{}")
    assert code == 2
    assert "nope" in out


def test_grandchild_pipe_holder_returns_fast(tmp_path: Path) -> None:
    # Direct child backgrounds a long-lived grandchild that inherits the
    # output fd, then exits 0 — the exact deadlock shape. With the temp-file
    # fix wait() returns the instant the direct child exits: fast SUCCESS,
    # NOT a timeout. (The old pipe design paid the full timeout per file.)
    hook = _write_hook(tmp_path, "leak.sh", "sleep 300 &\necho done\nexit 0\n")
    start = time.monotonic()
    code, out = pre_commit_batch._run_hook(hook, "{}", timeout_s=15)
    elapsed = time.monotonic() - start
    assert code == 0
    assert "done" in out
    assert elapsed < 5, f"runner paid the timeout ({elapsed:.1f}s) — stdio still pipes"


def test_hanging_direct_child_times_out(tmp_path: Path) -> None:
    # A delegate whose DIRECT child blocks (not just a backgrounded
    # grandchild) must still time out and be SIGKILLed, never hang forever.
    hook = _write_hook(tmp_path, "hang.sh", "sleep 300\n")
    start = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        pre_commit_batch._run_hook(hook, "{}", timeout_s=2)
    elapsed = time.monotonic() - start
    assert elapsed < 10, f"timeout not enforced ({elapsed:.1f}s)"


