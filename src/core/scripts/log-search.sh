#!/usr/bin/env bash
# Search changes.log for matching entries with date context.
# INPUT:  <QUERY> [N] | --help.
# OUTPUT: matching log entries (with date context) on stdout.
# DEPS:   _lib.sh, python3, $COS_STATE_DIR/changes.log.
set -euo pipefail
source "$(dirname "$0")/_lib.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: $0 <QUERY> [N]"
  echo ""
  echo "Search changes.log for entries matching QUERY."
  echo "Only entry-level lines are returned (not sub-bullets)."
  echo "Each result is prefixed with its date."
  echo ""
  echo "Arguments:"
  echo "  QUERY   Search term (case-insensitive)"
  echo "  N       Max results (default 10)"
  echo ""
  echo "Output format:"
  echo "  === N matches for \"query\" ==="
  echo "  [2026-03-14] TASK-014: fix — description"
  echo "  [2026-03-13] TASK-032: feat — description"
  echo ""
  echo "Examples:"
  echo "  make log-search QUERY=\"stripe\""
  echo "  make log-search QUERY=\"TASK-032\" N=5"
  exit 0
fi

QUERY="${1:-${QUERY:-}}"
LIMIT="${2:-${N:-10}}"

if [ -z "$QUERY" ]; then
  echo "Usage: $0 <QUERY> [N]"
  exit 1
fi

LOG_FILE="changes.log"

if [ ! -f "$LOG_FILE" ]; then
  info "No changes.log found."
  exit 0
fi

python3 - "$QUERY" "$LIMIT" "$LOG_FILE" <<'PY'
import re
import sys

query = sys.argv[1].lower()
limit = int(sys.argv[2]) if sys.argv[2].isdigit() else 10
log_file = sys.argv[3]

with open(log_file) as f:
    lines = f.readlines()

# Parse entries with date context
current_date = ""
results = []

for line in lines:
    stripped = line.strip()

    # Track date headers
    date_match = re.match(r"^## (\d{4}-\d{2}-\d{2})", stripped)
    if date_match:
        current_date = date_match.group(1)
        continue

    # Only match entry-level lines (start with "- " but NOT "  -" sub-bullets)
    if not line.startswith("- "):
        continue

    # Search in this line
    if query in stripped.lower():
        # Clean markdown bold
        clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", stripped)
        results.append(f"[{current_date}] {clean[2:]}")  # strip "- " prefix

    if len(results) >= limit:
        break

if not results:
    print(f'No matches for "{query}" in changes.log')
else:
    print(f'=== {len(results)} match{"es" if len(results) != 1 else ""} for "{query}" ===')
    for r in results:
        print(r)
PY
