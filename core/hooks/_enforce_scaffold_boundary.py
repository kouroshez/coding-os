"""Boundary check delegate for `enforce-scaffold-boundary.sh`.

PURPOSE:      Decide whether a Write/Edit at `<rel_path>` violates any
              installed stack's `scaffold-boundary.yaml::forbids_writing_in`.
              Lives as a real .py file (not heredoc) per Rule 8 — bash
              heredoc inside `$(...)` is banned.
INPUT:        argv[1] — boundary YAML path (aggregated `stacks` list).
              argv[2] — repo-relative path the agent is about to write.
              argv[3] — project root (informational only).
OUTPUT:       Exit code 0 / 2 + a single message line on stdout. Shell
              wrapper interprets `BLOCKED: …` (exit 2) and `WARN: …`
              (exit 0) lines.
DEPENDENCIES: PyYAML (fail-open if missing).
NOTES:        Fail-open on any unexpected error so a malformed boundary
              file never gates real work.
"""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        return 0
    boundary_path = Path(sys.argv[1])
    rel_path = sys.argv[2]

    try:
        import yaml  # noqa: WPS433 — runtime fail-open if missing
    except ImportError:
        return 0

    try:
        data = yaml.safe_load(boundary_path.read_text(encoding="utf-8"))
    except OSError:
        return 0
    except yaml.YAMLError:
        return 0

    stacks = data.get("stacks") if isinstance(data, dict) else None
    if not stacks:
        return 0

    owning_stack = None
    for stack in stacks:
        for pattern in stack.get("file_patterns") or []:
            if fnmatch.fnmatch(rel_path, pattern):
                owning_stack = stack
                break
        if owning_stack:
            break

    violator = None
    for stack in stacks:
        if owning_stack and stack.get("stack") == owning_stack.get("stack"):
            continue
        for forbidden_root in stack.get("forbids_writing_in") or []:
            forbidden = forbidden_root.rstrip("/")
            if rel_path == forbidden or rel_path.startswith(forbidden + "/"):
                violator = stack
                break
        if violator:
            break

    # Collision (file owned by X but Y forbids the subtree) is a static
    # config bug, not a per-write concern — caught offline by
    # `tests/test_scaffold_boundary_contract.py`. The hook only blocks
    # writes that are NOT owned by any installed stack AND fall under
    # another stack's `forbids_writing_in`.
    if owning_stack is None and violator is not None:
        print(
            f"BLOCKED: scaffold-boundary — '{rel_path}' is in a forbidden "
            f"subtree declared by stack '{violator.get('stack')}' "
            f"(forbids_writing_in: {violator.get('forbids_writing_in')}). "
            f"Edit allowed only by the stack that owns this root."
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
