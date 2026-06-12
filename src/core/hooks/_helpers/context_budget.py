"""Print a context-size warning when the live session exceeds the budget.

Called by session-context.sh (UserPromptSubmit) with the transcript path from
the hook payload. Reads the tail of the transcript, finds the most recent
``usage`` record, and prints ``<ctx_k>k><budget_k>k`` (e.g. ``412k>150k``)
when context exceeds COS_CONTEXT_BUDGET (default 150000). Prints nothing when
under budget or on any error — fire-and-forget, never blocks the prompt.
Spec: docs/playbooks/doctor-checks.md § Tokens, src/core/rules/transparency-banner.md.
"""

from __future__ import annotations

import json
import os
import sys

DEFAULT_CONTEXT_BUDGET_TOKENS = 150_000
TAIL_BYTES = 262_144


def last_context_tokens(transcript_path: str) -> int:
    with open(transcript_path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - TAIL_BYTES))
        tail = handle.read().decode("utf-8", errors="ignore")
    for line in reversed(tail.splitlines()):
        if '"usage"' not in line:
            continue
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        usage = (record.get("message") or {}).get("usage") or {}
        if not usage:
            continue
        return sum(
            usage.get(key) or 0
            for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
        )
    return 0


def main() -> None:
    if len(sys.argv) < 2:
        return
    transcript_path = sys.argv[1]
    if not transcript_path or not os.path.isfile(transcript_path):
        return
    budget = int(os.environ.get("COS_CONTEXT_BUDGET", DEFAULT_CONTEXT_BUDGET_TOKENS))
    try:
        context_tokens = last_context_tokens(transcript_path)
    except OSError:
        return
    if context_tokens > budget:
        print(f"{context_tokens // 1000}k>{budget // 1000}k")


if __name__ == "__main__":
    main()
