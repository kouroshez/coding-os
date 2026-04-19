#!/usr/bin/env bash
# Resolve REF:* codes from docs/foundation-map.md.
set -euo pipefail
source "$(dirname "$0")/_lib.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: $0 [REF_CODE] [--read]"
  echo ""
  echo "Resolve REF:* shortcodes to file paths from docs/foundation-map.md."
  echo ""
  echo "Modes:"
  echo "  $0                          List all REF codes"
  echo "  $0 PLAYBOOK-BACKEND         Resolve to file path"
  echo "  $0 REF:PLAYBOOK-BACKEND     Same (REF: prefix optional)"
  echo "  $0 PLAYBOOK-BACKEND --read  Output the file content"
  echo ""
  echo "Examples:"
  echo "  make ref                            # list all"
  echo "  make ref REF=PLAYBOOK-BACKEND       # show path"
  echo "  make ref REF=SCHEMA --read          # show file content"
  exit 0
fi

MAP_FILE="docs/foundation-map.md"

if [ ! -f "$MAP_FILE" ]; then
  err "$MAP_FILE not found"
fi

REF_CODE="${1:-${REF:-}}"
READ_FLAG="${2:-}"

# List all REF codes if no argument
if [ -z "$REF_CODE" ]; then
  grep -oE '`REF:[A-Z0-9_-]+`' "$MAP_FILE" | tr -d '`' | sort
  exit 0
fi

# Normalize: strip REF: prefix if provided
REF_CODE="${REF_CODE#REF:}"
FULL_REF="REF:$REF_CODE"

# Find in foundation-map
MATCH=$(grep "\`$FULL_REF\`" "$MAP_FILE" | head -1)

if [ -z "$MATCH" ]; then
  err "$FULL_REF not found in $MAP_FILE"
fi

# Extract path from: - `REF:CODE` → `./path/to/file.md`
PATH_VALUE=$(echo "$MATCH" | sed -n 's/.*→ `\([^`]*\)`.*/\1/p')

if [ -z "$PATH_VALUE" ]; then
  err "Could not parse path for $FULL_REF"
fi

# Resolve relative path from docs/ directory and normalize
RESOLVED=$(python3 -c "import os; print(os.path.normpath('docs/$PATH_VALUE'))")

if [ "$READ_FLAG" = "--read" ]; then
  if [ -f "$RESOLVED" ]; then
    cat "$RESOLVED"
  else
    err "File not found: $RESOLVED"
  fi
else
  echo "$RESOLVED"
fi
