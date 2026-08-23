"""Canonical UTC clock — the single producer for every stored timestamp.

Contract + rationale: docs/engineering/timestamp-contract.md. Lives under
logging_os because that is the one leaf package every silo (thinking_os,
graph_os, board_os, web, cli, scheduled, hook helpers) already imports, and
because logging_os owned the canonical ISO-Z format first. Stdlib only, no
intra-package imports — safe on the hot hook path.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
DAY_FORMAT = "%Y-%m-%d"


def now_epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime(ISO_FORMAT)


def now_day() -> str:
    return datetime.now(timezone.utc).strftime(DAY_FORMAT)


def to_iso(value: float | int | datetime) -> str:
    if isinstance(value, datetime):
        return to_utc(value).strftime(ISO_FORMAT)
    return datetime.fromtimestamp(value, tz=timezone.utc).strftime(ISO_FORMAT)


def to_utc(value: datetime) -> datetime:
    # A naive value is UTC-by-convention (SQLite's datetime('now') default);
    # an aware one is CONVERTED, never overwritten -- replacing a real +03:30
    # with UTC moves the instant by 3.5h instead of translating it.
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_utc(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return to_utc(datetime.fromisoformat(raw.strip().replace("Z", "+00:00")))
    except (ValueError, TypeError):
        return None


def parse_epoch(raw: str | None) -> int | None:
    parsed = parse_utc(raw)
    return int(parsed.timestamp()) if parsed else None


def today_utc() -> date:
    return datetime.now(timezone.utc).date()
