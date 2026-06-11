"""Detect a task status TRANSITION in a Write/Edit payload.

Exit 2 (BLOCK) when the diff mutates a `status:` frontmatter value, a
`**Status:**` body line, or ticks a previously-empty checkbox `[ ] -> [x]`.
Exit 0 otherwise. Fail-open on any parse error (never block on a bug).

A transition is a workflow action that must route through cos_task_move /
cos task-done so the board DB, WIP caps, and DoD gates stay consistent.
A raw hand-Edit silently desyncs them.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

STATUS_FM = re.compile(r"^\s*status:\s*(\S+)", re.M)
STATUS_MD = re.compile(r"^\s*\*\*Status:\*\*\s*(.+?)\s*$", re.M)
CHECKED = re.compile(r"-\s*\[[xX]\]")

BLOCK_MSG = """BLOCKED: task status is a workflow transition — do not hand-edit it.
  File: {file_path}
  Detected: a status:/**Status:**/checkbox change in the diff.

  Route the transition through the board, not a text edit:
    - Move state:  cos_task_move(task_id="TASK-NNN", to="testing"|"blocked"|...)
                   (CLI: cos task-move TASK-NNN --to testing)
    - Mark done:   cos task-done TASK-NNN   (or cos_task_move ... to="complete")

  Escape hatches (rare, legitimate):
    - Governance task in flight: write-state.sh .task-current "docs-update-<slug>"
    - One-shot override:         COS_ALLOW_TASK_EDIT=1 (this invocation only)
"""


def _statuses(text: str) -> tuple[list[str], list[str]]:
    fm = STATUS_FM.findall(text or "")
    md = [m.strip() for m in STATUS_MD.findall(text or "")]
    return fm, md


def main() -> int:
    try:
        data = json.loads(sys.argv[1])
    except Exception:
        return 0

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if "old_string" in tool_input and "new_string" in tool_input:
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
    else:
        # Write: compare new content against the on-disk file. A brand-new
        # file has no prior state — that is a creation, not a transition.
        new = tool_input.get("content", "")
        p = Path(file_path)
        try:
            old = p.read_text(encoding="utf-8") if p.exists() else ""
        except Exception:
            return 0
        if not old:
            return 0

    old_fm, old_md = _statuses(old)
    new_fm, new_md = _statuses(new)
    status_changed = (old_fm and new_fm and old_fm != new_fm) or (
        old_md and new_md and old_md != new_md
    )
    checkbox_ticked = len(CHECKED.findall(new)) > len(CHECKED.findall(old))

    if status_changed or checkbox_ticked:
        print(BLOCK_MSG.format(file_path=file_path), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
