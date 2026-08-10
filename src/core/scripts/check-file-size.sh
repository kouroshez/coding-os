#!/usr/bin/env bash
# Repo-wide half of the file-size ceiling (anti-overengineering.md sub-rule 6).
# The PreToolUse hook stops an agent authoring an oversized file; this stops one
# arriving any other way — a human commit, a generator, a merge. Wire it into
# CI so the ceiling is a gate, not an agent-only convention.
#
#   bash check-file-size.sh [path ...]      # defaults to the whole repo
#   COS_MAX_FILE_LINES=500 bash check-file-size.sh
set -euo pipefail

MAX_LINES="${COS_MAX_FILE_LINES:-800}"

EXCLUDE_RE='(^|/)(node_modules|__pycache__|dist|build|vendor|migrations|scaffold|golden|\.venv|\.git|\.build|archive)(/|$)'
SOURCE_RE='\.(py|ts|tsx|js|jsx|go|rs|rb|php|java|cs|dart|sh)$'

if [[ $# -gt 0 ]]; then
  ROOTS=("$@")
else
  ROOTS=(".")
fi

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  candidates=$(git ls-files -- "${ROOTS[@]}")
else
  candidates=$(find "${ROOTS[@]}" -type f 2>/dev/null)
fi

offenders=""
while IFS= read -r file; do
  [[ -n "$file" ]] || continue
  [[ "$file" =~ $SOURCE_RE ]] || continue
  [[ "$file" =~ $EXCLUDE_RE ]] && continue
  [[ -f "$file" ]] || continue
  lines=$(wc -l < "$file" | tr -d ' ')
  if [[ "$lines" -gt "$MAX_LINES" ]]; then
    offenders+="  $file: $lines lines"$'\n'
  fi
done <<< "$candidates"

if [[ -n "$offenders" ]]; then
  echo "ERROR: files over the ${MAX_LINES}-line ceiling — split them along their seam:" >&2
  printf '%s' "$offenders" >&2
  echo "Rationale + how to find the seam: anti-overengineering.md sub-rule 6," >&2
  echo "clean-code skill § File Design." >&2
  exit 1
fi

echo "OK: no source file exceeds ${MAX_LINES} lines"
