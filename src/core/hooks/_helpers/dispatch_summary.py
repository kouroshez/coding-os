"""Summarise completed cross-provider dispatches for the session pulse.

auto-dispatch-crossprovider runs detached, so its result cannot come back inline.
Without this line the operator would have to query the database to learn which
adapter and model ran a role — the exact blindness routing exists to remove.
"""

from __future__ import annotations

import json
import sys

_MAX_ROWS = 4


def summarise(lines: list[str]) -> str:
    rows = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        cost = entry.get("cost_usd")
        money = f"${cost:.4f}" if isinstance(cost, (int, float)) else ""
        rows.append(
            "{role}@{adapter}/{model}={status}{money}".format(
                role=entry.get("role") or "?",
                adapter=entry.get("adapter") or "?",
                model=entry.get("model") or "-",
                status=entry.get("status") or "?",
                money=money,
            )
        )
    return " ".join(rows[:_MAX_ROWS])


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return 0
    try:
        with open(argv[1], encoding="utf-8") as handle:
            print(summarise(handle.readlines()))
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
