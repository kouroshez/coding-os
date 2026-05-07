"""Aggregate the per-turn activity log into a one-line pulse summary.

Reads .turn-activity.log, counts by category, formats compact summary
(memory:N graph:N task:T-NN skill:X), then truncates the log so the
next turn starts clean. Called by core/hooks/session-context.sh on
UserPromptSubmit. Bounded — silent on any error.
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path


def _agent_dir() -> Path | None:
    base = os.environ.get("COS_AGENT_DIR")
    if base:
        return Path(base)
    state = os.environ.get("COS_STATE_DIR") or ".coding-os"
    agent = os.environ.get("COS_AGENT") or "claude"
    return Path(state) / agent


def main(argv: list[str]) -> int:
    target = _agent_dir()
    if target is None:
        return 0
    log = target / ".turn-activity.log"
    if not log.exists():
        return 0
    try:
        raw = log.read_text(encoding="utf-8")
    except OSError:
        return 0
    if not raw.strip():
        return 0

    counts: Counter[str] = Counter()
    last_detail: dict[str, str] = {}
    for line in raw.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 2:
            continue
        cat, detail = parts[0], parts[1]
        if not cat:
            continue
        counts[cat] += 1
        if detail:
            last_detail[cat] = detail

    if not counts:
        try:
            log.write_text("", encoding="utf-8")
        except OSError:
            pass
        return 0

    fragments: list[str] = []
    order = ["memory", "worklog", "graph", "task", "skill"]
    seen = set(order)
    for cat in order + [c for c in counts if c not in seen]:
        if cat not in counts:
            continue
        n = counts[cat]
        if cat in {"task", "skill"}:
            tail = last_detail.get(cat, "")
            fragments.append(f"{cat}:{tail}" if tail else f"{cat}:{n}")
        else:
            fragments.append(f"{cat}:{n}")

    sys.stdout.write(" ".join(fragments))
    try:
        log.write_text("", encoding="utf-8")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
