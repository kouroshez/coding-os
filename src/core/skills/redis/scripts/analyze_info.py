"""Summarize `redis-cli INFO` output into health metrics + flags.

PURPOSE:      Collapse a 200-line INFO dump into the few numbers that matter
              (hit rate, memory, evictions, eviction policy) and flag problems,
              so the agent reads a summary instead of scrolling INFO.
INPUT:        `redis-cli INFO` text on stdin, or --file <path>.
              [--min-hit-rate R] flag below this (default 0.80). [--json]
OUTPUT:       Metrics + flags on stderr; result on stdout ("clean"/"N finding(s)").
              Exit 0 clean, 1 if findings, 2 usage.
DEPENDENCIES: stdlib only. Offline — you pipe INFO in.
NOTES:        Pure parse/analyze layer is unit-testable without a server.
              Spec: docs/playbooks/skill-authoring.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_info(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _hit_rate(fields: dict[str, str]) -> float | None:
    try:
        hits = int(fields["keyspace_hits"])
        misses = int(fields["keyspace_misses"])
    except (KeyError, ValueError):
        return None
    total = hits + misses
    return hits / total if total else None


def analyze(fields: dict[str, str], min_hit_rate: float) -> tuple[dict, list[str]]:
    metrics: dict[str, object] = {
        "used_memory_human": fields.get("used_memory_human", "?"),
        "maxmemory_policy": fields.get("maxmemory_policy", "?"),
        "evicted_keys": int(fields.get("evicted_keys", 0) or 0),
        "connected_clients": fields.get("connected_clients", "?"),
        "hit_rate": _hit_rate(fields),
    }
    flags: list[str] = []

    hr = metrics["hit_rate"]
    if hr is not None and hr < min_hit_rate:
        flags.append(
            f"low hit rate {hr:.0%} (<{min_hit_rate:.0%}) — cache too small, "
            "wrong TTLs, or caching the wrong keys"
        )
    if metrics["evicted_keys"] and metrics["maxmemory_policy"] == "noeviction":
        flags.append(
            "evictions with noeviction policy — writes are being rejected; "
            "set allkeys-lru for a cache"
        )
    if metrics["maxmemory_policy"] == "noeviction" and fields.get("maxmemory", "0") not in (
        "0",
        "",
    ):
        flags.append(
            "maxmemory set with noeviction — Redis rejects writes when full "
            "(outage); use allkeys-lru/lfu for a cache"
        )
    return metrics, flags


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--file", default=None)
    parser.add_argument("--min-hit-rate", default=0.80, type=float)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    raw = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    if not raw.strip():
        print("error: no INFO text on stdin (or --file)", file=sys.stderr)
        return 2

    metrics, flags = analyze(parse_info(raw), args.min_hit_rate)
    for k, v in metrics.items():
        print(f"  {k}: {v}", file=sys.stderr)
    for f in flags:
        print(f"  ✗ {f}", file=sys.stderr)
    if args.as_json:
        print(json.dumps({"metrics": metrics, "flags": flags, "count": len(flags)}))
    else:
        print("clean" if not flags else f"{len(flags)} finding(s)")
    return 1 if flags else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
