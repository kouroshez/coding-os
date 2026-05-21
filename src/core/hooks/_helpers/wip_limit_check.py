import json
import os
import sys
from pathlib import Path

try:
    from board_os.config import load_config
    from board_os.parser import extract_frontmatter, is_lean_format
    from board_os.workflow import check_wip
except ImportError:
    sys.exit(0)

try:
    data = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)

tool_input = data.get("tool_input", {})
content = tool_input.get("content") or ""
if "new_string" in tool_input and "old_string" in tool_input:
    p = Path(tool_input.get("file_path", ""))
    if p.exists():
        try:
            content = p.read_text(encoding="utf-8").replace(
                tool_input["old_string"],
                tool_input["new_string"],
            )
        except Exception as exc:  # fail-open: log + continue (Rule 6)
            print(f"wip_limit_check: simulate-edit failed: {exc}", file=sys.stderr)

if not content or not is_lean_format(content):
    sys.exit(0)

fm = extract_frontmatter(content)
if fm is None:
    sys.exit(0)

new_status = fm.get("status")
if new_status not in {"in_progress", "emergency"}:
    sys.exit(0)

# Distinguish transition from same-status body edit. If the on-disk
# task already has the same status we're writing back, this is just
# a body update (Outcome / Acceptance / Work Log) — not a new WIP slot.
# Only count cap usage when the status actually changes.
target_path = Path(tool_input.get("file_path", ""))
if target_path.exists():
    try:
        existing = target_path.read_text(encoding="utf-8")
        existing_fm = extract_frontmatter(existing)
        if existing_fm and existing_fm.get("status") == new_status:
            sys.exit(0)
    except Exception as exc:  # fail-open: log + continue (Rule 6)
        print(f"wip_limit_check: read existing failed: {exc}", file=sys.stderr)

if os.environ.get("COS_WIP_OVERRIDE") == "1":
    sys.exit(0)

project_root = Path(os.environ.get("COS_PROJECT_ROOT", os.getcwd())).resolve()
try:
    config = load_config(project_root)
except (FileNotFoundError, Exception):
    sys.exit(0)

import sqlite3

try:
    from thinking_os.database import resolve_db_path  # type: ignore

    db_path = str(resolve_db_path(project_root))
except ImportError:
    db_path = os.environ.get(
        "COS_DB_PATH",
        str(project_root / ".coding-os" / "coding-os.db"),
    )
if not Path(db_path).exists():
    sys.exit(0)

conn = sqlite3.connect(db_path)
state = check_wip(conn, config)
conn.close()

cap = state.caps.get(new_status)
current = state.counts.get(new_status, 0)
if cap is not None and current >= cap:
    print(
        f"ERROR enforce-wip-limit: WIP cap reached for {new_status}: "
        f"{current}/{cap}. Complete another task first or set "
        f"COS_WIP_OVERRIDE=1 to force.",
        file=sys.stderr,
    )
    sys.exit(2)

sys.exit(0)
