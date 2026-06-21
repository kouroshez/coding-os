#!/usr/bin/env python3
"""Graph phantom-regression gate (TASK-461 / audit A2).

The graph the meta-graph-first rule tells agents to TRUST went healthy:false with
~70 phantom `cursor-*` nodes (adapter-removal staleness) and nothing caught it.
A raw `healthy:false` gate is the wrong signal — it is persistently false from
benign `orphaned_external_unresolved` (unresolved third-party imports) and
`files_with_parse_errors`, so it would be permanently red. The real corruption
signal is `orphaned_phantom`: a code node referenced but never defined.

This checker reads `cos graph-doctor` and fails when the phantom count EXCEEDS a
baseline ceiling — catching a regression (a spike like the 70 cursor nodes)
without demanding the graph first be cleaned to zero. Ratchet the baseline DOWN
as phantoms are triaged; never up without a reason.

Cost decision (acceptance #3): a full `cos graph-reindex` of the meta-repo
(~44K nodes) takes minutes and the graph DB is gitignored (absent in CI), so this
is wired into the NIGHTLY slow suite (45-min budget), not the per-PR gate. Per-PR
graph building was rejected as too slow for the value.

Usage:
    python src/scripts/check_graph_phantoms.py [--baseline N]
Exit 0 if phantom_count <= baseline, else 1.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

DEFAULT_BASELINE = 3  # current live count (2026-06-19); ratchet down, never up.


def _phantom_count() -> tuple[int, list[dict]]:
    proc = subprocess.run(
        ["cos", "graph-doctor"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    data = json.loads(proc.stdout).get("data", {})
    issues = data.get("issues", [])
    phantom = sum(int(i.get("count", 0)) for i in issues if i.get("category") == "orphaned_phantom")
    samples = [i for i in issues if i.get("category") == "orphaned_phantom"]
    return phantom, samples


def main() -> int:
    parser = argparse.ArgumentParser(description="Graph phantom-regression gate")
    parser.add_argument("--baseline", type=int, default=DEFAULT_BASELINE)
    args = parser.parse_args()

    try:
        phantom, samples = _phantom_count()
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
        print(f"check_graph_phantoms: could not read graph-doctor: {exc}", file=sys.stderr)
        return 1

    if phantom > args.baseline:
        print(
            f"GRAPH REGRESSION: {phantom} orphaned_phantom nodes > baseline {args.baseline}.",
            file=sys.stderr,
        )
        print(json.dumps(samples, indent=2)[:2000], file=sys.stderr)
        print("Run `cos graph-doctor --fix` / triage extractor staleness.", file=sys.stderr)
        return 1

    print(f"graph phantom check OK: {phantom} <= baseline {args.baseline}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
