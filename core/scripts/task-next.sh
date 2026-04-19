#!/usr/bin/env bash
# Show the next recommended task by scanning docs/tasks.md top-to-bottom.
# The first open (- [ ]) task in the file IS the next task — no external config needed.
set -euo pipefail
source "$(dirname "$0")/_lib.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: task-next.sh [-v|--verbose]"
  echo ""
  echo "Show the next recommended task."
  echo "Scans docs/tasks.md top-to-bottom and returns the first open task."
  echo ""
  echo "Flags:"
  echo "  -v, --verbose   Show full index line, context hints, and quick start"
  echo ""
  echo "Behavior:"
  echo "  - Returns the first '- [ ]' task found in docs/tasks.md"
  echo "  - Skips BLOCKED tasks with a message"
  echo "  - Task order comes from the file itself (phase grouping)"
  exit 0
fi

VERBOSE=0
if [ "${1:-}" = "-v" ] || [ "${1:-}" = "--verbose" ]; then
  VERBOSE=1
fi

INDEX="docs/tasks.md"

if [ ! -f "$INDEX" ]; then
  err "Task list not found: $INDEX"
fi

# Scan the file line by line — first open task wins
while IFS= read -r line; do
  # Skip lines that aren't task entries
  [[ "$line" =~ TASK-([0-9]{3}) ]] || continue
  padded="${BASH_REMATCH[1]}"

  # Check if blocked
  if echo "$line" | grep -q '^\- (BLOCKED:'; then
    if [ "$VERBOSE" -eq 1 ]; then
      warn "SKIPPING TASK-${padded} (BLOCKED)"
    fi
    continue
  fi

  # Check if open
  if echo "$line" | grep -q '\- \[ \]'; then
    detail_file=$(find docs/tasks -maxdepth 1 -name "TASK-${padded}-*" 2>/dev/null | head -1 || true)

    if [ "$VERBOSE" -eq 1 ]; then
      echo "=== Next Recommended Task ==="
      echo ""
      echo "Next open task: TASK-${padded}"
      echo "Index entry: $line"
      echo ""
      if [ -n "$detail_file" ]; then
        echo "Detail file: $detail_file"
        echo "Load context: make task-context TASK=${padded}"
      else
        echo "No detail file yet (will be created automatically)."
      fi
      echo ""
      echo "Quick start: make task-start TASK=${padded}"
    else
      ok "next=TASK-${padded}"
      echo "  file=${detail_file:-(will be created)}"
      echo "  start=make task-start TASK=${padded}"
    fi
    exit 0
  fi

  # Check if WIP (in progress)
  if echo "$line" | grep -q '\- \[/\]'; then
    if [ "$VERBOSE" -eq 1 ]; then
      info "TASK-${padded} is already in progress [/]"
    fi
    continue
  fi
done < "$INDEX"

info "All tasks are either completed or blocked. No next task available."
