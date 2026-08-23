"""Canonical UTC clock — the one producer per timestamp storage class.

Contract + rationale: docs/engineering/timestamp-contract.md. Lives under
logging_os because that is the one leaf package every silo (thinking_os,
graph_os, board_os, web, cli, scheduled, hook helpers) already imports, and
because logging_os owned the canonical ISO-Z format first. Stdlib only, no
intra-package imports — safe on the hot hook path.
"""

from __future__ import annotations

from datetime import datetime, timezone

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
DAY_FORMAT = "%Y-%m-%d"


def now_epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime(ISO_FORMAT)


def now_day() -> str:
    return datetime.now(timezone.utc).strftime(DAY_FORMAT)
