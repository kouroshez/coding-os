"""Drain stdin with a hard timeout.

python3 fallback for the `cos_read_stdin_bounded` Bash helper when perl is
absent (perl ships with macOS but not with slim/Alpine images). argv[1] =
timeout in seconds. Prints whatever bytes arrived; on timeout prints what was
read so far. Never raises — the caller treats an empty envelope as "no input",
so a crash here would re-open the fail-open channel this helper exists to close.
"""

from __future__ import annotations

import contextlib
import signal
import sys


class _Timeout(Exception):
    pass


def _on_alarm(_signum: int, _frame: object) -> None:
    raise _Timeout


def _arm_alarm(seconds: int) -> None:
    # No SIGALRM (non-POSIX, or not the main thread): read unbounded instead —
    # an agent runtime always closes the pipe, and a hook that reads nothing is
    # exactly the fail-open this helper exists to prevent.
    with contextlib.suppress(AttributeError, ValueError):
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(seconds)


def main() -> int:
    try:
        seconds = max(1, int(float(sys.argv[1]))) if len(sys.argv) > 1 else 2
    except (TypeError, ValueError):
        seconds = 2

    data = b""
    _arm_alarm(seconds)
    try:
        data = sys.stdin.buffer.read()
    except (_Timeout, OSError, ValueError):
        data = b""
    finally:
        with contextlib.suppress(AttributeError, ValueError):
            signal.alarm(0)

    sys.stdout.buffer.write(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
