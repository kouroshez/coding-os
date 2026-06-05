"""Estimate token count + cost for a prompt or context file.

PURPOSE:      Budget context windows and cost without a tokenizer dependency —
              a fast heuristic range so the agent sizes a prompt before sending.
INPUT:        text file path or --file; or text on stdin. [--rate <usd_per_1m>]
              price per 1M tokens for a cost estimate (default 0 = skip cost).
              [--json]
OUTPUT:       Estimated token range (+ cost) on stderr; midpoint int on stdout.
              Exit 0. Exit 2 on usage.
DEPENDENCIES: stdlib only — no tokenizer/model download.
NOTES:        Heuristic: real BPE tokenizers vary ~±15%; this brackets with two
              independent estimates (script-aware char weighting + words*1.33).
              Non-ASCII chars count ~1 token each so non-Latin isn't undercounted.
              Pure estimate() is unit-testable. Spec: docs/playbooks/skill-authoring.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CHARS_PER_TOKEN = 4.0
TOKENS_PER_WORD = 1.33


def _by_script(text: str) -> float:
    # ASCII ~4 chars/token; non-ASCII (CJK / Arabic / Cyrillic) BPE-splits far
    # denser, so count each non-ASCII char as ~1 token. Plain chars/4 undercounts
    # non-Latin text 2-3x — the bug this heuristic exists to avoid.
    ascii_chars = len(text.encode("ascii", "ignore"))
    non_ascii = len(text) - ascii_chars
    return ascii_chars / CHARS_PER_TOKEN + non_ascii


def estimate(text: str) -> tuple[int, int, int]:
    """Return (low, mid, high) token estimates from two heuristics."""
    by_script = _by_script(text)
    by_words = len(text.split()) * TOKENS_PER_WORD
    low = int(min(by_script, by_words))
    high = int(max(by_script, by_words))
    mid = round((low + high) / 2)
    return low, mid, high


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("path", nargs="?", default=None)
    parser.add_argument("--file", default=None)
    parser.add_argument("--rate", default=0.0, type=float, help="USD per 1M tokens")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    target = args.file or args.path
    text = Path(target).read_text(encoding="utf-8") if target else sys.stdin.read()
    if not text:
        print("error: no text (file or stdin)", file=sys.stderr)
        return 2

    low, mid, high = estimate(text)
    print(f"  tokens ~{low}-{high} (mid {mid})", file=sys.stderr)
    cost = None
    if args.rate:
        cost = mid / 1_000_000 * args.rate
        print(f"  cost ~${cost:.4f} at ${args.rate}/1M", file=sys.stderr)
    if args.as_json:
        print(json.dumps({"low": low, "mid": mid, "high": high, "cost_usd": cost}))
    else:
        print(mid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
