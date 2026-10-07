"""Workers of parent_bound_pool must die with their parent and never before it."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path

import pytest

from cli._parent_bound_pool import PARENT_POLL_SECONDS, _exit_when_parent_dies, parent_bound_pool

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
WORKERS = 3
STARTUP_TIMEOUT_S = 30
ORPHAN_GRACE_S = 3 * PARENT_POLL_SECONDS + 1

POOL_SCRIPT = textwrap.dedent(
    """
    import os, sys, time
    from cli._parent_bound_pool import parent_bound_pool

    def hold(pid_dir):
        open(os.path.join(pid_dir, str(os.getpid())), "w").close()
        time.sleep(600)

    if __name__ == "__main__":
        pool = parent_bound_pool(int(sys.argv[2]))
        for _ in range(int(sys.argv[2])):
            pool.submit(hold, sys.argv[1])
        time.sleep(600)
    """
)


def _sleep_then_report(seconds: float) -> int:
    time.sleep(seconds)
    return os.getpid()


def _children_of(pid: int) -> set[int]:
    table = subprocess.run(
        ["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True, check=True
    )
    pairs = (line.split() for line in table.stdout.splitlines())
    return {int(child) for child, parent in pairs if int(parent) == pid}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _wait_until(condition, timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.1)
    return condition()


@pytest.mark.parametrize("kill_signal", [signal.SIGKILL, signal.SIGTERM])
def test_workers_exit_when_parent_is_killed_mid_task(tmp_path: Path, kill_signal: int) -> None:
    script = tmp_path / "pool_parent.py"
    script.write_text(POOL_SCRIPT)
    pid_dir = tmp_path / "pids"
    pid_dir.mkdir()
    env = {**os.environ, "PYTHONPATH": str(SRC_ROOT)}
    parent = subprocess.Popen([sys.executable, str(script), str(pid_dir), str(WORKERS)], env=env)
    try:
        assert _wait_until(lambda: len(list(pid_dir.iterdir())) == WORKERS, STARTUP_TIMEOUT_S)
        descendants = _children_of(parent.pid)
        busy_workers = {int(path.name) for path in pid_dir.iterdir()}
        assert busy_workers <= descendants

        parent.send_signal(kill_signal)
        parent.wait(timeout=5)

        survivors = lambda: {pid for pid in descendants if _alive(pid)}  # noqa: E731
        assert _wait_until(lambda: not survivors(), ORPHAN_GRACE_S), f"orphans left: {survivors()}"
    finally:
        if parent.poll() is None:
            parent.kill()
        for path in pid_dir.iterdir():
            if _alive(int(path.name)):
                os.kill(int(path.name), signal.SIGKILL)


INTERRUPT_SCRIPT = textwrap.dedent(
    """
    import sys, time
    from cli._parent_bound_pool import parent_bound_pool

    def step(_):
        time.sleep(0.5)

    if __name__ == "__main__":
        with parent_bound_pool(2) as pool:
            for _ in range(int(sys.argv[1])):
                pool.submit(step, 0)
            print("queued", flush=True)
            time.sleep(600)
    """
)


def test_ctrl_c_drops_queued_work_instead_of_draining_it(tmp_path: Path) -> None:
    script = tmp_path / "interrupted.py"
    script.write_text(INTERRUPT_SCRIPT)
    queued_tasks = 120
    drain_seconds = queued_tasks * 0.5 / 2
    env = {**os.environ, "PYTHONPATH": str(SRC_ROOT)}
    parent = subprocess.Popen(
        [sys.executable, str(script), str(queued_tasks)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
    try:
        assert parent.stdout.readline().strip() == "queued"
        time.sleep(1)
        os.killpg(parent.pid, signal.SIGINT)
        started = time.monotonic()
        parent.wait(timeout=drain_seconds)
        assert time.monotonic() - started < drain_seconds / 4
    finally:
        if parent.poll() is None:
            os.killpg(parent.pid, signal.SIGKILL)


def test_worker_outlives_the_poll_interval_while_parent_is_alive() -> None:
    with parent_bound_pool(2) as pool:
        futures = [pool.submit(_sleep_then_report, 2.5 * PARENT_POLL_SECONDS) for _ in range(2)]
        worker_pids = [future.result(timeout=STARTUP_TIMEOUT_S) for future in futures]
    assert all(worker_pids)


@pytest.mark.skipif(sys.platform == "win32", reason="forkserver is POSIX-only")
def test_watchdog_tracks_the_forkserver_not_the_pool_owner() -> None:
    pool = ProcessPoolExecutor(
        max_workers=1, mp_context=get_context("forkserver"), initializer=_exit_when_parent_dies
    )
    with pool:
        worker_pid = pool.submit(_sleep_then_report, 2.5 * PARENT_POLL_SECONDS).result(
            timeout=STARTUP_TIMEOUT_S
        )
    assert worker_pid != os.getpid()
