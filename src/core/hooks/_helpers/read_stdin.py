"""Drain stdin with a hard timeout.

python3 fallback for the `cos_read_stdin_bounded` Bash helper when perl is
absent (perl ships with macOS but not with slim/Alpine images). argv[1] =
timeout in seconds. Prints whatever bytes arrived; on timeout prints what was
read so far. Never raises — the caller treats an empty envelope as "no input",
so a crash here would re-open the fail-open channel this helper exists to close.
"""

from __future__ import annotations

import signal
import sys


class _Timeout(Exception):
    pass


def _on_alarm(_signum: int, _frame: object) -> None:
    raise _Timeout


def main() -> int:
    try:
        seconds = max(1, int(float(sys.argv[1]))) if len(sys.argv) > 1 else 2
    except (TypeError, ValueError):
        seconds = 2

    data = b""
    try:
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(seconds)
    except (AttributeError, ValueError):
        # No SIGALRM (non-POSIX): read unbounded — the runtime always closes stdin.
        pass

    try:
        data = sys.stdin.buffer.read()
    except (_Timeout, OSError, ValueError):
        pass
    finally:
        try:
            signal.alarm(0)
        except (AttributeError, ValueError):
            pass

    sys.stdout.buffer.write(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
