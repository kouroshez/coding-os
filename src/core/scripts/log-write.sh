#!/usr/bin/env bash
# Write a structured log entry to changes.log.
# Format: 3 lines per entry (title + impact + files). Always provide WHAT and FILES.
set -euo pipefail
source "$(dirname "$0")/_lib.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: $0 [TASK] <TYPE> <MSG> <WHAT> <FILES>"
  echo ""
  echo "Write a structured entry to changes.log. Always provide WHAT and FILES."
  echo ""
  echo "Arguments:"
  echo "  TASK    Task number or ID (optional — omit for ad-hoc work)"
  echo "  TYPE    One of: feat, fix, refactor, docs, test, infra"
  echo "  MSG     Title summary (max 80 chars, quoted)"
  echo "  WHAT    Impact description (optional, max 120 chars)"
  echo "  FILES   Key files changed (optional, max 120 chars)"
  echo ""
  echo "Entry format (1-3 lines):"
  echo "  - TASK-###: <type> — <title>"
  echo "    What: <impact>"
  echo "    Files: <files>"
  echo ""
  echo "Examples:"
  echo "  make log-write TYPE=fix MSG=\"optimized session-init\""
  echo "  make log-write TASK=014 TYPE=fix MSG=\"SSOT restructured\" WHAT=\"8 bugs fixed\""
  echo "  make log-write TASK=014 TYPE=fix MSG=\"SSOT restructured\" WHAT=\"8 bugs fixed\" FILES=\"task-create.sh, task-context.sh\""
  exit 0
fi

RAW_TASK="${1:-${TASK:-}}"
TYPE="${2:-${TYPE:-}}"
MSG="${3:-${MSG:-}}"
WHAT="${4:-${WHAT:-}}"
FILES="${5:-${FILES:-}}"

# If first arg looks like a type (not a number), shift: no TASK provided
if [ -n "$RAW_TASK" ] && echo "feat fix refactor docs test infra" | grep -qw "$RAW_TASK"; then
  FILES="$WHAT"
  WHAT="$MSG"
  MSG="$TYPE"
  TYPE="$RAW_TASK"
  RAW_TASK=""
fi

if [ -z "$TYPE" ] || [ -z "$MSG" ]; then
  echo "Usage: $0 [TASK] <TYPE> <MSG> <WHAT> <FILES>"
  echo "TYPE and MSG required, TASK optional. Always provide WHAT and FILES."
  exit 1
fi

# Validate type
VALID_TYPES="feat fix refactor docs test infra"
if ! echo "$VALID_TYPES" | grep -qw "$TYPE"; then
  err "TYPE must be one of: $VALID_TYPES"
fi

# Validate lengths
if [ "${#MSG}" -gt 80 ]; then
  err "MSG must be 80 chars or fewer (got ${#MSG})"
fi
if [ -n "$WHAT" ] && [ "${#WHAT}" -gt 120 ]; then
  err "WHAT must be 120 chars or fewer (got ${#WHAT})"
fi
if [ -n "$FILES" ] && [ "${#FILES}" -gt 120 ]; then
  err "FILES must be 120 chars or fewer (got ${#FILES})"
fi

echo "=== log-write ==="

python3 - "$RAW_TASK" "$TYPE" "$MSG" "$WHAT" "$FILES" <<'PY'
from pathlib import Path
from datetime import date
import re
import sys

raw_task, entry_type, msg, what, files = sys.argv[1:6]
today = date.today().isoformat()

# Resolve task ID if provided
task_id = ""
if raw_task:
    match = re.fullmatch(r"(?:TASK-?)?(\d+)", raw_task)
    if not match:
        raise SystemExit("ERROR: Invalid task format. Use: 14, 014, TASK-14, or TASK-014")
    task_num = int(match.group(1))
    task_id = f"TASK-{task_num:03d}"

    # Validate task exists
    index_path = Path("docs/tasks.md")
    if index_path.exists() and task_id not in index_path.read_text():
        raise SystemExit(f"ERROR: {task_id} not found in {index_path}")

# Build entry (1-3 lines)
if task_id:
    line1 = f"- {task_id}: {entry_type} — {msg}"
else:
    line1 = f"- {entry_type} — {msg}"

entry = line1
if what:
    entry += f"\n  What: {what}"
if files:
    entry += f"\n  Files: {files}"

# Write to changes.log
log_path = Path("changes.log")
if log_path.exists():
    log_text = log_path.read_text()
else:
    log_text = "# Project Change Log\n"

date_header = f"## {today}"
if date_header not in log_text:
    first_newline = log_text.find("\n")
    if first_newline == -1:
        log_text += f"\n\n{date_header}\n\n"
    else:
        log_text = log_text[:first_newline + 1] + f"\n{date_header}\n\n" + log_text[first_newline + 1:]

# Insert entry under today's date header
date_pos = log_text.find(date_header)
insert_pos = date_pos + len(date_header)
# Skip exactly one newline after date header, then insert
if insert_pos < len(log_text) and log_text[insert_pos] == "\n":
    insert_pos += 1
log_text = log_text[:insert_pos] + "\n" + entry + "\n" + log_text[insert_pos:]

log_path.write_text(log_text)
print(entry)
PY
