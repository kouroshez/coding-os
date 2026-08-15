"""Only score an envelope whose coverage is provably complete.

The graph reports incompleteness two ways, and conflating them breaks a benchmark in
opposite directions:

``walk_truncated``
    The traversal hit a node-visit cap. Whatever count the envelope carries is an
    artifact of that cap, not a fact about the codebase. This is the defect this
    module exists to prevent: the published README row for ``init_db`` reported 508
    impacted at the default ``visit_limit``; at a sufficient budget it is 1,494.

``result_truncated`` / ``truncated``
    Either the row list hit its ``limit``, or the token-budget trimmer shortened it
    after a complete walk. The flag alone cannot tell you which, so treating it as
    "incomplete" throws away perfectly good answers — a `references` call that
    reports 96 total and returns 75 rows knows exactly how many exist.

So completeness is decided **empirically**, not from a flag: widen the budget and
watch the totals. A count that stops growing is a real count. A row list shorter
than that count is a ranked sample, which is a legitimate answer — "1,494 impacted,
here are the 60 riskiest" — as long as the report says so instead of implying it
returned every row.

Spec: docs/engineering/third-party-token-bench.md
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Widening ladder. A probe whose totals are still growing at the top is reported
# incomplete and never scored.
BUDGET_LADDER = (500, 2_000, 10_000, 50_000)

COMPLETE = "complete"
COUNT_PLUS_SAMPLE = "count+sample"
INCOMPLETE = "incomplete"

_TOTAL_KEYS = ("total_count", "impacted_count")
_ROW_KEYS = ("references", "results", "sites", "contracts", "edges", "call_sites")


@dataclass(frozen=True)
class Reading:
    tokens: int
    total_count: int
    rows_shown: int
    walk_truncated: bool
    budget: int


@dataclass(frozen=True)
class Envelope:
    tokens: int
    total_count: int
    rows_shown: int
    budget_used: int
    answer_shape: str

    @property
    def scorable(self) -> bool:
        return self.answer_shape != INCOMPLETE


def _as_dict(raw: object) -> dict[str, Any]:
    if isinstance(raw, str):
        parsed: object = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    return raw if isinstance(raw, dict) else {}


def _nested(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _total_in(data: dict[str, Any]) -> int:
    for key in _TOTAL_KEYS:
        value = data.get(key)
        if isinstance(value, int):
            return value
    # rename_plan reports one total per section rather than a single figure.
    section_totals = [
        v for k, v in data.items() if k.endswith("_total_count") and isinstance(v, int)
    ]
    if section_totals:
        return sum(section_totals)
    return _rows_in(data)


def _rows_in(data: dict[str, Any]) -> int:
    tiers = data.get("tiers")
    if isinstance(tiers, dict):
        return sum(len(rows) for rows in tiers.values() if isinstance(rows, list))
    matched = [len(data[key]) for key in _ROW_KEYS if isinstance(data.get(key), list)]
    if matched:
        return sum(matched)
    count = data.get("count")
    return count if isinstance(count, int) else 0


def read(raw: object, *, budget: int) -> Reading:
    data = _nested(_as_dict(raw), "data")
    meta = _nested(data, "meta")
    return Reading(
        tokens=max(1, int(meta.get("tokens_estimated") or 0)),
        total_count=_total_in(data),
        rows_shown=_rows_in(data),
        walk_truncated=bool(meta.get("walk_truncated")),
        budget=budget,
    )


def _classify(reading: Reading, *, totals_settled: bool) -> str:
    if reading.walk_truncated or not totals_settled:
        return INCOMPLETE
    return COMPLETE if reading.rows_shown >= reading.total_count else COUNT_PLUS_SAMPLE


def resolve_complete(call: Callable[[int], object], *, widens: bool = True) -> Envelope:
    """Call the tool, widening its budget until the reported total stops growing.

    `call` takes a budget and returns the raw envelope. Pass `widens=False` for a
    tool with no budget knob — one call, and its own total is taken at face value.
    """
    ladder = BUDGET_LADDER if widens else BUDGET_LADDER[:1]
    reading = read(call(ladder[0]), budget=ladder[0])
    settled = not widens

    for budget in ladder[1:]:
        wider = read(call(budget), budget=budget)
        settled = wider.total_count <= reading.total_count and not wider.walk_truncated
        reading = wider
        if settled:
            break

    return Envelope(
        tokens=reading.tokens,
        total_count=reading.total_count,
        rows_shown=reading.rows_shown,
        budget_used=reading.budget,
        answer_shape=_classify(reading, totals_settled=settled),
    )


__all__ = [
    "BUDGET_LADDER",
    "COMPLETE",
    "COUNT_PLUS_SAMPLE",
    "INCOMPLETE",
    "Envelope",
    "Reading",
    "read",
    "resolve_complete",
]
