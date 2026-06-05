#!/usr/bin/env bash
# Show the last N log entries from changes.log (default: 1).
# An "entry" is a line starting with "- " plus any indented continuation lines.
# INPUT:  optional N (entry count, default 1) | --help.
# OUTPUT: the N most-recent log entries on stdout.
# DEPS:   _lib.sh, $COS_STATE_DIR/changes.log.
set -euo pipefail
source "$(dirname "$0")/_lib.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: $0 [N]"
  echo ""
  echo "Show the last N log entries from changes.log."
  echo "Default: 1 (most recent entry only)."
  echo ""
  echo "Arguments:"
  echo "  N    Number of entries to show (default 1, or 'all' for today's entries)"
  echo ""
  echo "Examples:"
  echo "  make log-latest           # last entry"
  echo "  make log-latest N=5       # last 5 entries"
  echo "  make log-latest N=all     # all entries from today"
  exit 0
fi

# --compact: internal flag used by session-init to show single-line summaries
COMPACT=0
if [ "${1:-}" = "--compact" ]; then
  COMPACT=1
  shift
fi
N="${1:-${N:-1}}"
LOG_FILE="changes.log"

if [ ! -f "$LOG_FILE" ]; then
  info "No changes.log found."
  exit 0
fi

if [ "$N" = "all" ]; then
  # Show all entries from today's date
  TODAY=$(date +%Y-%m-%d)
  HEADER="## $TODAY"
  if ! grep -q "$HEADER" "$LOG_FILE"; then
    info "No entries for today ($TODAY)."
    exit 0
  fi
  # Print from today's header until next ## header or end of file (cross-platform)
  python3 -c "
import sys
lines = open('$LOG_FILE').readlines()
in_section = False
for line in lines:
    if line.startswith('## $TODAY'):
        in_section = True
        print(line, end='')
        continue
    if in_section:
        if line.startswith('## ') and '$TODAY' not in line:
            break
        print(line, end='')
"
else
  # Show last N entries (entry = line starting with "- " + indented continuation lines)
  # Each entry is prefixed with [YYYY-MM-DD] from its parent date section
  python3 -c "
import re, sys
entries = []
current = []
current_date = ''
for line in open('$LOG_FILE'):
    date_match = re.match(r'^## (\d{4}-\d{2}-\d{2})', line)
    if date_match:
        if current:
            entries.append((current_date, ''.join(current)))
            current = []
        current_date = date_match.group(1)
        continue
    if line.startswith('- '):
        if current:
            entries.append((current_date, ''.join(current)))
        current = [line]
    elif current and (line.startswith('  ') or line.strip() == ''):
        if line.strip() == '' and current:
            entries.append((current_date, ''.join(current)))
            current = []
        else:
            current.append(line)
    else:
        if current:
            entries.append((current_date, ''.join(current)))
            current = []
if current:
    entries.append((current_date, ''.join(current)))
compact = $COMPACT
for date_str, e in entries[:$N]:
    prefix = f'[{date_str}] ' if date_str else ''
    first_line, *rest = e.splitlines(True)
    print(f'{prefix}{first_line}', end='')
    if not compact:
        for r in rest:
            print(r, end='')
    if not e.endswith('\n'):
        print()
"
fi
