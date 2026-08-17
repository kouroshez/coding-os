"""`hub.log` is a bounded file, not an append-forever one.

The hub is a singleton daemon whose stdout+stderr are appended to
`~/.coding-os/hub.log` for weeks, and uvicorn logged one line per request.
The UI polls presence every ~2.6s, so the file reached 65 MB of
`GET /api/presence/now 200 OK` — the same unbounded-sink shape that let the
SQLite WAL reach 59 GB. Two guards pin it: the access log is off at the
source, and `cos hub start` trims what is left to its tail.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from cli.hub_commands import (
    _HUB_LOG_KEEP_BYTES,
    HUB_LOG_MAX_BYTES,
    _truncate_hub_log,
)


def _write(path: Path, line: bytes, total: int) -> None:
    with path.open("wb") as handle:
        written = 0
        while written < total:
            handle.write(line)
            written += len(line)


def test_access_log_is_disabled_at_the_source() -> None:
    source = (REPO / "src/core/web/server.py").read_text(encoding="utf-8")
    assert '"access_log": False' in source, (
        "run_server must pass access_log=False; the per-request line is what grew hub.log to 65 MB"
    )


def test_under_cap_is_left_alone(tmp_path: Path) -> None:
    log = tmp_path / "hub.log"
    _write(log, b"INFO: startup complete\n", 1024)
    before = log.read_bytes()

    assert _truncate_hub_log(log) == 0
    assert log.read_bytes() == before


def test_over_cap_is_trimmed_to_the_tail(tmp_path: Path) -> None:
    log = tmp_path / "hub.log"
    _write(log, b"INFO: GET /api/presence/now 200 OK\n", HUB_LOG_MAX_BYTES * 2)
    size_before = log.stat().st_size

    reclaimed = _truncate_hub_log(log)

    assert reclaimed > 0
    assert log.stat().st_size <= _HUB_LOG_KEEP_BYTES
    assert reclaimed == size_before - log.stat().st_size


def test_the_tail_is_kept_not_the_head(tmp_path: Path) -> None:
    log = tmp_path / "hub.log"
    with log.open("wb") as handle:
        handle.write(b"OLDEST-MARKER\n")
        handle.write(b"filler line\n" * (HUB_LOG_MAX_BYTES // 12 + 1))
        handle.write(b"NEWEST-MARKER\n")

    _truncate_hub_log(log)
    kept = log.read_bytes()

    assert b"NEWEST-MARKER" in kept, "the newest lines explain the current failure"
    assert b"OLDEST-MARKER" not in kept


def test_trimmed_file_starts_on_a_line_boundary(tmp_path: Path) -> None:
    log = tmp_path / "hub.log"
    _write(log, b"INFO: GET /api/presence/now 200 OK\n", HUB_LOG_MAX_BYTES * 2)

    _truncate_hub_log(log)

    assert log.read_bytes().startswith(b"INFO:"), "no half-line at the top"


def test_one_giant_line_is_not_truncated_to_nothing(tmp_path: Path) -> None:
    # A traceback longer than the keep window must not blank the file: with no
    # newline in the tail slice there is no partial line to drop.
    log = tmp_path / "hub.log"
    log.write_bytes(b"X" * (HUB_LOG_MAX_BYTES * 2))

    _truncate_hub_log(log)

    assert log.stat().st_size > 0


def test_missing_file_is_a_no_op(tmp_path: Path) -> None:
    assert _truncate_hub_log(tmp_path / "absent.log") == 0
