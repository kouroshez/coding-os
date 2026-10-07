"""A process pool whose workers exit as soon as the process that started them dies."""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ProcessPoolExecutor
from types import TracebackType

PARENT_POLL_SECONDS = 1.0


def _exit_when_parent_dies() -> None:
    # Read the parent here, not from the caller's pid: under forkserver the
    # worker's parent is the server process, not the process that built the pool.
    parent_pid = os.getppid()

    def watch() -> None:
        while os.getppid() == parent_pid:
            time.sleep(PARENT_POLL_SECONDS)
        os._exit(1)

    threading.Thread(target=watch, name="parent-watchdog", daemon=True).start()


class _ParentBoundPool(ProcessPoolExecutor):
    # The stock __exit__ drains the whole queue, so Ctrl+C on a large walk kept
    # indexing for minutes; leaving on an exception drops the work not yet started.
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        self.shutdown(wait=True, cancel_futures=exc_type is not None)
        return False


def parent_bound_pool(max_workers: int) -> ProcessPoolExecutor:
    return _ParentBoundPool(max_workers=max_workers, initializer=_exit_when_parent_dies)
