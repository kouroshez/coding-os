#!/usr/bin/env python3
"""mypy gate: a count ratchet over the kernel, plus zero-tolerance error codes.

Spec: docs/engineering/ci-gates.md. Lower BASELINE in the same commit that
fixes errors — the count may only fall. FATAL_CODES must stay at zero: a
count budget of several thousand cannot surface one genuine new bug.
"""

from __future__ import annotations

import re
import subprocess
import sys

# Measured in the CI environment, which reports ~16 more than a local run
# (the documented dual `board_os.*`/`core.board_os.*` counting artifact) —
# always re-measure from a CI log, never from a laptop. History + rationale:
# docs/engineering/ci-gates.md § Recorded exceptions.
BASELINE = 4474
SCOPE = ["src/core/thinking_os", "src/core/board_os", "src/core/graph_os"]

# Bug classes a refactor actually produces, each measured at zero when added.
# Widening the scope beyond SCOPE is safe precisely because these are zero:
# src/cli and src/core/web carry no count baseline, so they were ungated.
FATAL_CODES = ("return", "call-arg", "used-before-def")
FATAL_SCOPE = [*SCOPE, "src/cli", "src/core/web"]


def _fatal_findings(scope: list[str]) -> list[str]:
    proc = subprocess.run(
        ["uv", "run", "mypy", *scope], capture_output=True, text=True, check=False
    )
    wanted = {f"[{code}]" for code in FATAL_CODES}
    return [
        line
        for line in proc.stdout.splitlines()
        if ": error:" in line and line.rsplit(" ", 1)[-1] in wanted
    ]


def main() -> int:
    fatal = _fatal_findings(FATAL_SCOPE)
    if fatal:
        print(
            f"mypy-ratchet: FAIL — {len(fatal)} zero-tolerance error(s): {', '.join(FATAL_CODES)}"
        )
        print("These name real defects, not legacy debt — fix them, never baseline them:")
        for line in fatal:
            print(f"  {line}")
        return 1

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
