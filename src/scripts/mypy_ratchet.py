#!/usr/bin/env python3
"""mypy count-ratchet gate: fail when the error count rises above BASELINE.

Spec: docs/engineering/ci-gates.md. Lower BASELINE in the same commit that
fixes errors — the count may only fall.
"""

from __future__ import annotations

import re
import subprocess
import sys

BASELINE = 4599  # measured 2026-08-08 over the scope below
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
        new_lines = [line for line in out.splitlines() if ": error:" in line]
        print("\n".join(new_lines[-40:]))
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
