#!/usr/bin/env python3
"""mypy count-ratchet gate: fail when the error count rises above BASELINE.

Spec: docs/engineering/ci-gates.md. Lower BASELINE in the same commit that
fixes errors — the count may only fall.
"""

from __future__ import annotations

import re
import subprocess
import sys

# Measured in the CI environment, which reports ~16 more than a local run
# (the documented dual `board_os.*`/`core.board_os.*` counting artifact) —
# always re-measure from a CI log, never from a laptop. History + rationale:
# docs/engineering/ci-gates.md § Recorded exceptions.
BASELINE = 4651
SCOPE = ["src/core/thinking_os", "src/core/board_os", "src/core/graph_os"]


def main() -> int:
    proc = subprocess.run(
        ["uv", "run", "mypy", *SCOPE],
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout.strip()
    if "Success: no issues found" in out:
        count = 0
    else:
        match = re.search(r"Found (\d+) errors?", out)
        if not match:
            print(out[-2000:], file=sys.stderr)
            print("mypy-ratchet: could not parse mypy output", file=sys.stderr)
            return 2
        count = int(match.group(1))

    if count > BASELINE:
        print(f"mypy-ratchet: FAIL — {count} errors > baseline {BASELINE} (+{count - BASELINE})")
        # Per-file counts, not a tail of raw lines: a rise is diagnosed by
        # diffing this table against a local run. The old tail-40 output hid
        # which file grew and cost a CI round-trip to find out.
        per_file: dict[str, int] = {}
        for line in out.splitlines():
            if ": error:" in line:
                path = line.split(":", 1)[0]
                per_file[path] = per_file.get(path, 0) + 1
        print("errors per file (diff against a local `uv run mypy <scope>`):")
        for path, n in sorted(per_file.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>5}  {path}")
        return 1
    if count < BASELINE:
        print(
            f"mypy-ratchet: PASS — {count} errors < baseline {BASELINE}; "
            f"lower BASELINE to {count} in src/scripts/mypy_ratchet.py"
        )
    else:
        print(f"mypy-ratchet: PASS — {count} errors == baseline {BASELINE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
