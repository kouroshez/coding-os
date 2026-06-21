"""Tests for the pre-commit reap-timeout wrapper (TASK-169).

The wrapper must bound a hung child to <timeout>+grace, kill the whole
process subtree (no orphans), and pass success/failure codes through.
"""

from __future__ import annotations

import errno
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
    / "run_with_reap_timeout.sh"
)


def _run(script: str, timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=timeout)


def test_reaps_hanging_command_within_grace():
    script = f'source "{HELPER}"; cos_run_with_reap_timeout 1 sleep 60; echo "rc=$?"'
    start = time.monotonic()
    res = _run(script)
    elapsed = time.monotonic() - start
    assert elapsed < 8, f"wrapper took {elapsed:.1f}s: {res.stdout}{res.stderr}"
    rc = next(line for line in res.stdout.splitlines() if line.startswith("rc="))
    assert rc.split("=", 1)[1] in ("143", "137"), res.stdout


def test_passthrough_success():
    res = _run(f'source "{HELPER}"; cos_run_with_reap_timeout 5 true; echo "rc=$?"')
    assert "rc=0" in res.stdout


def test_passthrough_failure_code():
    res = _run(f'source "{HELPER}"; cos_run_with_reap_timeout 5 bash -c "exit 7"; echo "rc=$?"')
    assert "rc=7" in res.stdout


def test_reaps_grandchild_subtree(tmp_path):
    # The wrapped command backgrounds a grandchild sleeper; after the reap the
    # grandchild must be dead, proving the recursive tree-kill works.
    pidfile = tmp_path / "gc.pid"
    child = tmp_path / "child.sh"
    child.write_text(f'sleep 60 &\necho $! > "{pidfile}"\nwait\n')
    script = f'source "{HELPER}"; cos_run_with_reap_timeout 1 bash "{child}"; sleep 1'
    _run(script, timeout=15)
    gc_pid = int(pidfile.read_text().strip())
    alive = True
    try:
        os.kill(gc_pid, 0)
    except OSError as exc:
        alive = exc.errno != errno.ESRCH
    assert not alive, f"grandchild {gc_pid} survived the reap"
