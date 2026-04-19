#!/usr/bin/env bash
# Show tasks with optional status filter
# Usage: bash core/scripts/task-list.sh [open|wip|blocked|done|all]
set -euo pipefail
source "$(dirname "$0")/_lib.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: task-list.sh [STATUS]"
  echo ""
  echo "List tasks filtered by status."
  echo ""
  echo "Arguments:"
  echo "  STATUS    Filter: open, wip, blocked, done, all (default: all)"
  echo ""
  echo "Output prefixes:"
  echo "  TODO:     Open tasks (- [ ])"
  echo "  WIP:      In-progress tasks ([/])"
  echo "  BLOCKED:  Blocked tasks (BLOCKED: reason)"
  echo "  DONE:     Completed tasks (- [x])"
  exit 0
fi

# Primary source: docs/tasks.md (task list with checkbox markers)
TASK_FILE="docs/tasks.md"

if [ ! -f "$TASK_FILE" ]; then
  err "Task file not found at $TASK_FILE"
fi

FILTER="${1:-all}"

case "$FILTER" in
  open)
    grep '\- \[ \]' "$TASK_FILE" | sed 's/.*- \[ \]/  TODO:/' || echo "  (none)"
    ;;
  wip)
    grep '\[/\]' "$TASK_FILE" | sed 's/.*\[\/\]/  WIP:/' || echo "  (none)"
    ;;
  blocked)
    grep '^\- (BLOCKED:' "$TASK_FILE" | sed 's/^- (BLOCKED: \([^)]*\)) /  BLOCKED (\1): /' || echo "  (none)"
    ;;
  done)
    grep '\- \[x\]' "$TASK_FILE" | sed 's/.*- \[x\]/  DONE:/' || echo "  (none)"
    ;;
  all)
    echo "=== Open ==="
    grep '\- \[ \]' "$TASK_FILE" 2>/dev/null | sed 's/.*- \[ \]/  TODO:/' || echo "  (none)"
    echo ""
    echo "=== In Progress ==="
    grep '\[/\]' "$TASK_FILE" 2>/dev/null | sed 's/.*\[\/\]/  WIP:/' || echo "  (none)"
    echo ""
    echo "=== Blocked ==="
    grep '^\- (BLOCKED:' "$TASK_FILE" 2>/dev/null | sed 's/^- (BLOCKED: \([^)]*\)) /  BLOCKED (\1): /' || echo "  (none)"
    echo ""
    DONE_COUNT=$(grep -c '\- \[x\]' "$TASK_FILE" 2>/dev/null; true)
    echo "=== Done: $DONE_COUNT tasks ==="
    ;;
  *)
    echo "Usage: $0 [open|wip|blocked|done|all]"
    exit 1
    ;;
esac
