"""The canonical UTC clock — one producer per timestamp storage class.

Contract: docs/engineering/timestamp-contract.md (Critical Rule 28). The shapes
asserted here are what the strict `%Y-%m-%dT%H:%M:%SZ` readers in logs.py and
observability.py accept; drifting any of them silently drops records from every
Hub view rather than raising.
"""

from __future__ import annotations

import calendar
import re
import time
from datetime import datetime, timezone

from core.logging_os import clock

ISO_SHAPE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DAY_SHAPE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def test_now_iso_matches_the_strict_reader_shape() -> None:
    assert ISO_SHAPE.match(clock.now_iso())


def test_now_iso_is_parseable_by_the_hub_readers() -> None:
    """logs.py / observability.py both use this exact strptime form."""
    parsed = calendar.timegm(time.strptime(clock.now_iso(), "%Y-%m-%dT%H:%M:%SZ"))
    assert abs(parsed - time.time()) < 120


def test_now_iso_round_trips_through_fromisoformat_as_aware_utc() -> None:
    parsed = datetime.fromisoformat(clock.now_iso().replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(None)


def test_now_epoch_is_utc_seconds() -> None:
    assert abs(clock.now_epoch() - int(time.time())) < 120


def test_now_day_is_the_utc_day_not_the_local_day() -> None:
    assert DAY_SHAPE.match(clock.now_day())
    assert clock.now_day() == datetime.now(timezone.utc).strftime("%Y-%m-%d")


def test_now_day_is_the_prefix_of_now_iso() -> None:
    assert clock.now_iso().startswith(clock.now_day())


def test_format_constants_are_the_ones_the_producers_use() -> None:
    assert clock.ISO_FORMAT == "%Y-%m-%dT%H:%M:%SZ"
    assert clock.DAY_FORMAT == "%Y-%m-%d"
