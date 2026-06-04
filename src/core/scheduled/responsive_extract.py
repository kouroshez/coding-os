#!/usr/bin/env python3
"""Responsive learn_extract trigger — fired by session-end.sh (Stop hook).

When at least ``responsive_extract_threshold`` new task_outcomes have accrued
since the last extract, mine patterns now instead of waiting for the nightly
daemon — so same-day outcomes feed ``cos_learn_suggest`` in the next session.
Bounded, fire-and-forget; shares the ``.last-extract`` marker with nightly so
the two paths stay idempotent. No-op when scheduled config has enabled=false.

argv: <session_id> <active_task> <db_path>  (passed by session-end run_bounded_python)
Contract: docs/engineering/scheduled-jobs.md § Configurable cadence + responsive extraction.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parent
_THINKING_OS = _CORE / "thinking_os"
for _p in (str(_CORE), str(_THINKING_OS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scheduled._activity import outcomes_since_marker  # noqa: E402
from scheduled._state import state_dir, touch_marker  # noqa: E402
from scheduled.config import load_config  # noqa: E402


def main() -> int:
    if len(sys.argv) < 4:
        return 0
    db_path = Path(sys.argv[3])
    if not db_path.exists():
        return 0
    # db lives at <root>/.coding-os/coding-os.db → project_root is two up.
    project_root = db_path.parent.parent
    try:
        cfg = load_config(project_root)
        if not cfg["enabled"]:
            return 0
        marker = state_dir(project_root) / ".last-extract"
        if outcomes_since_marker(db_path, marker) < int(cfg["responsive_extract_threshold"]):
            return 0
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            total = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]
            if total < int(cfg["learn_extract_min_outcomes"]):
                return 0
            from tools.learning import learn_extract

            learn_extract(conn)
        touch_marker(marker)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
