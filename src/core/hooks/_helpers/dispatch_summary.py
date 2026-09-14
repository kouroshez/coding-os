"""Summarise completed cross-provider dispatches for the session pulse.

auto-dispatch-crossprovider runs detached, so its result cannot come back inline.
Without this line the operator would have to query the database to learn which
adapter and model ran a role — the exact blindness routing exists to remove.

The line carries the role's **verdict and findings**, not just its route and
price. A reviewer that ran on another provider, found three problems, and
persisted them into the evidence bundle used to reach the parent as
`reviewer@codex/gpt-5.6-sol=ok$0.5612` — which reads exactly like a clean
review. Paying for a review whose result nobody sees is worse than not
running one, because it also buys false confidence.
"""

from __future__ import annotations

import json
import sys

_MAX_ROWS = 4
_MAX_FINDINGS = 2
_FINDING_CHARS = 70


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
            "{role}@{adapter}/{model}={status}{money}{verdict}".format(
                role=entry.get("role") or "?",
                adapter=entry.get("adapter") or "?",
                model=entry.get("model") or "-",
                status=entry.get("status") or "?",
                money=money,
                verdict=_verdict_suffix(entry),
            )
        )
    return " ".join(rows[:_MAX_ROWS])


def _verdict_suffix(entry: dict) -> str:
    findings = [str(f) for f in (entry.get("findings") or []) if f]
    passed = entry.get("passed")
    if findings:
        shown = "; ".join(f[:_FINDING_CHARS] for f in findings[:_MAX_FINDINGS])
        return f" ✗{len(findings)}: {shown}"
    if passed is True:
        return " ✓clean"
    return ""


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
