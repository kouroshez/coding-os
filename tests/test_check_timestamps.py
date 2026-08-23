"""Tests for the timestamp warn-tier helper behind block-bad-patterns.sh.

The helper is the write-time half of Critical Rule 28; the repo-wide static gate
is tests/test_timestamp_discipline.py. Contract:
docs/engineering/timestamp-contract.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "core" / "hooks" / "_helpers"))

import check_timestamps as ct


def _one(source: str) -> str:
    warnings = ct.collect_python_warnings(source)
    assert len(warnings) == 1, f"expected exactly one warning, got {warnings}"
    return warnings[0]


def test_utcnow_flagged() -> None:
    assert "utcnow()" in _one("import datetime\nx = datetime.datetime.utcnow()\n")


def test_utcfromtimestamp_flagged() -> None:
    assert "utcfromtimestamp()" in _one("x = datetime.utcfromtimestamp(1)\n")


def test_fromtimestamp_without_tz_flagged() -> None:
    assert "without `tz=`" in _one("x = datetime.fromtimestamp(1)\n")


def test_fromtimestamp_with_tz_is_clean() -> None:
    assert ct.collect_python_warnings("x = datetime.fromtimestamp(1, tz=timezone.utc)\n") == []


def test_nested_call_does_not_defeat_the_tz_check() -> None:
    """A regex lookahead stops at the first `)` and false-positives here."""
    source = "x = datetime.fromtimestamp(float(raw), tz=timezone.utc)\n"
    assert ct.collect_python_warnings(source) == []


def test_naive_now_flagged() -> None:
    assert "naive local" in _one("x = datetime.now()\n")


def test_aware_now_is_clean() -> None:
    assert ct.collect_python_warnings("x = datetime.now(timezone.utc)\n") == []


def test_mktime_over_strptime_flagged() -> None:
    source = 'x = time.mktime(time.strptime(v, "%Y-%m-%dT%H:%M:%SZ"))\n'
    assert "calendar.timegm" in _one(source)


def test_mktime_over_something_else_is_clean() -> None:
    assert ct.collect_python_warnings("x = time.mktime(other_struct)\n") == []


def test_unguarded_replace_tzinfo_flagged() -> None:
    assert "OVERWRITES" in _one("x = dt.replace(tzinfo=timezone.utc)\n")


def test_replace_without_tzinfo_is_clean() -> None:
    assert ct.collect_python_warnings("x = s.replace('a', 'b')\n") == []


def test_ts_allow_marker_suppresses_the_line() -> None:
    source = "x = datetime.now()  # ts-allow: launchd Hour is local\n"
    assert ct.collect_python_warnings(source) == []


def test_syntax_error_is_not_a_crash() -> None:
    assert ct.collect_python_warnings("def broken(:\n") == []


def test_shell_local_day_flagged() -> None:
    warnings = ct.collect_shell_warnings("today=$(date +%Y-%m-%d)\n")
    assert len(warnings) == 1
    assert "date -u +%Y-%m-%d" in warnings[0]


def test_shell_utc_day_is_clean() -> None:
    assert ct.collect_shell_warnings("today=$(date -u +%Y-%m-%d)\n") == []


def test_shell_comment_is_not_flagged() -> None:
    assert ct.collect_shell_warnings("# never use date +%Y-%m-%d here\n") == []
