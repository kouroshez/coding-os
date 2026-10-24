#!/usr/bin/env bash
# Pre/post search-count verification for rename + cross-cutting edits.
# Use BEFORE a rename to lock the ground-truth count, then AFTER to
# assert zero remaining matches.
#
# Usage:
#   bash verify-count.sh before "TASK-XXX" "old_symbol"
#       → prints baseline count + saves snapshot
#   bash verify-count.sh after "TASK-XXX" "old_symbol"
#       → re-counts; fails (exit 1) if any match remains
#
# Designed to be the assertion the `search` skill describes.

set -euo pipefail

# Safety: ensure core POSIX tools resolvable even when caller PATH is restricted.
export PATH="/usr/bin:/bin:/usr/local/bin:${PATH:-}"

if [ $# -lt 3 ]; then
  echo "usage: $0 {before|after} <slug> <pattern> [extra grep flags...]" >&2
  exit 2
fi

PHASE="$1"
SLUG="$2"
PATTERN="$3"
shift 3
EXTRA_FLAGS=("$@")

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
AGENT_DIR="${COS_AGENT_DIR:-${COS_STATE_DIR:-$REPO_ROOT/.coding-os}/${COS_AGENT:-shared}}"
mkdir -p "$AGENT_DIR/search-snapshots"
SNAP="$AGENT_DIR/search-snapshots/${SLUG}.count"

# Run the count. Use git grep when in a repo (respects .gitignore,
# fast). Fall back to grep -r.
count() {
  if [ -d "$REPO_ROOT/.git" ]; then
    git -C "$REPO_ROOT" grep -c "${EXTRA_FLAGS[@]+"${EXTRA_FLAGS[@]}"}" -F "$PATTERN" 2>/dev/null | awk -F: '{s+=$2} END {print s+0}'
  else
    grep -rc "${EXTRA_FLAGS[@]+"${EXTRA_FLAGS[@]}"}" -F "$PATTERN" "$REPO_ROOT" 2>/dev/null | awk -F: '{s+=$2} END {print s+0}'
  fi
}

case "$PHASE" in
  before)
    n=$(count)
    echo "$n" > "$SNAP"
    echo "[search verify-count] BEFORE: $n matches for '$PATTERN' saved to $SNAP"
    if [ "$n" -eq 0 ]; then
      echo "[search verify-count] WARNING: baseline is already 0 — nothing to rename?" >&2
    fi
    ;;
  after)
    n=$(count)
    if [ ! -f "$SNAP" ]; then
      echo "[search verify-count] ERROR: no baseline at $SNAP. Run 'before' first." >&2
      exit 2
    fi
    baseline=$(cat "$SNAP")
    echo "[search verify-count] BEFORE: $baseline | AFTER: $n"
    if [ "$n" -gt 0 ]; then
      echo "[search verify-count] FAIL: $n match(es) remain for '$PATTERN'" >&2
      echo "Run: git grep -F '$PATTERN'  to see remaining sites" >&2
      exit 1
    fi
    echo "[search verify-count] OK: all $baseline match(es) cleared."
    ;;
  *)
    echo "phase must be 'before' or 'after', got: $PHASE" >&2
    exit 2
    ;;
esac
