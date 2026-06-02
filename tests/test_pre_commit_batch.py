"""Regression tests for the pre-commit batch hook runner (TASK-058).

The deadlock: a delegate hook that backgrounds a grandchild leaves that
grandchild holding the captured stdout/stderr pipe write-end. subprocess
timeout SIGKILLs only the direct child, so the reaping read blocks on the
never-closing pipe forever — every 15+-file commit hung and held
.git/index.lock. The fix runs each delegate in its own process group and
SIGKILLs the whole group on timeout.
"""

from __future__ import annotations

import importlib.util
import subprocess
import time
from pathlib import Path

import pytest

_HELPER = (
    Path(__file__).resolve().parent.parent
    / "src" / "core" / "hooks" / "_helpers" / "pre_commit_batch.py"
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
    hook = _write_hook(tmp_path, "ok.sh", 'echo hello; exit 0\n')
    code, out = pre_commit_batch._run_hook(hook, "{}")
    assert code == 0
    assert "hello" in out


def test_blocking_hook_propagates_exit_2(tmp_path: Path) -> None:
    hook = _write_hook(tmp_path, "block.sh", 'echo nope >&2; exit 2\n')
    code, out = pre_commit_batch._run_hook(hook, "{}")
    assert code == 2
    assert "nope" in out


def test_grandchild_pipe_holder_does_not_deadlock(tmp_path: Path) -> None:
    # Direct child exits immediately but backgrounds a long-lived grandchild
    # that inherits the stdout/stderr pipe — the exact deadlock shape.
    hook = _write_hook(tmp_path, "leak.sh", "sleep 300 &\nexit 0\n")
    start = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        pre_commit_batch._run_hook(hook, "{}", timeout_s=2)
    elapsed = time.monotonic() - start
    # Must terminate near the timeout, not hang on the orphaned pipe.
    assert elapsed < 15, f"runner hung {elapsed:.1f}s — process group not killed"
