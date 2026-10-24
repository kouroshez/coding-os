#!/usr/bin/env python3
"""Duplicate-code ratchet: fail on a copy-paste the committed baseline does not record.

Spec: docs/engineering/graph_os-queries.md § Duplicate ratchet.

Usage:
    python check_graph_duplicates.py [--baseline PATH] [--update]
Exit 0 when nothing is new (or no graph index: [SKIP]), 1 on a new or grown
clone group, 2 when the graph cannot be read.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_BASELINE = Path(".coding-os/graph-duplicates-baseline.json")
PAGE_SIZE = 500
QUERY_TIMEOUT_SECONDS = 300
REPRO = "cos graph-duplicates --pretty"


def _live_groups() -> tuple[dict[str, dict], int]:
    groups: dict[str, dict] = {}
    offset = 0
    while True:
        proc = subprocess.run(
            ["cos", "graph-duplicates", "--top", str(PAGE_SIZE), "--offset", str(offset)],
            capture_output=True,
            text=True,
            timeout=QUERY_TIMEOUT_SECONDS,
            check=False,
        )
        envelope = json.loads(proc.stdout)
        if not envelope.get("ok"):
            raise RuntimeError(envelope.get("error", {}).get("message") or proc.stderr[-300:])
        data = envelope["data"]
        for group in data["groups"]:
            groups[group["fingerprint"]] = {
                "members": len(group["members"]),
                "example": group["members"][0]["uid"],
            }
        offset += PAGE_SIZE
        if offset >= data["total_count"]:
            return groups, data["meta"]["fingerprinted_symbols"]


def _regressions(live: dict[str, dict], baseline: dict[str, dict]) -> list[str]:
    found = []
    for fingerprint, group in sorted(live.items()):
        recorded = baseline.get(fingerprint)
        if recorded is None:
            found.append(f"new clone group ({group['members']} copies), e.g. {group['example']}")
        elif group["members"] > recorded["members"]:
            found.append(
                f"group grew {recorded['members']} -> {group['members']} copies, "
                f"e.g. {group['example']}"
            )
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="Duplicate-code ratchet")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--update", action="store_true", help="shrink the baseline to today")
    args = parser.parse_args()

    try:
        live, fingerprinted = _live_groups()
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, RuntimeError) as exc:
        print(f"[FAIL] graph-duplicates: could not read the graph ({exc}) — run: {REPRO}")
        return 2
    if fingerprinted == 0:
        print("[SKIP] graph-duplicates: no graph index — run `cos graph-reindex` first")
        return 0

    baseline_exists = args.baseline.is_file()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if baseline_exists else {}
    regressions = _regressions(live, baseline) if baseline_exists else []

    if args.update:
        if regressions:
            print(
                f"[FAIL] graph-duplicates: --update never grows the baseline ({len(regressions)})"
            )
            for line in regressions:
                print(f"  {line}")
            return 1
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(dict(sorted(live.items())), indent=2) + "\n"
        args.baseline.write_text(text, encoding="utf-8")
        print(f"[OK] graph-duplicates: baseline now {len(live)} group(s) ({args.baseline})")
        return 0

    if not baseline_exists:
        print(f"[FAIL] graph-duplicates: no baseline at {args.baseline} — create it with --update")
        return 1
    if regressions:
        print(f"[FAIL] graph-duplicates: {len(regressions)} new copy-paste(s) — run: {REPRO}")
        for line in regressions:
            print(f"  {line}")
        return 1
    removed = len(baseline) - len(live.keys() & baseline.keys())
    hint = f"; {removed} gone — shrink with --update" if removed else ""
    print(f"[OK] graph-duplicates: {len(live)} group(s), none new{hint}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
