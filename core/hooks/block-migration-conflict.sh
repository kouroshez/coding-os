#!/usr/bin/env bash
# PreToolUse Write|Edit hook: block duplicate migration versions.
#
# Source of truth: CLAUDE.md Critical Rule #10 — "Schema migrations are
# append-only. New tables → migration vN+1, never edit past migrations."
#
# Scope: runs only on files named `db.py` (migration registries in
# thinking-os) and on files under `*/migrations/` for frameworks that
# use numbered migration files (Django, Alembic).
#
# For db.py-style files: detects `MIGRATIONS.append((N, ...))` in the
# new content and rejects N if it already exists in the current file.
#
# For framework migration files: detects attempts to create a file
# named with a version prefix that already exists in the same dir
# (0003_foo.py + 0003_bar.py = conflict).
#
# Fail-closed — a duplicate-version DB is corrupt and silent: this must
# block, not warn.
set -euo pipefail

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[[ -z "$FILE_PATH" ]] && exit 0

# --- db.py-style registries ------------------------------------------
# Fires when the changed file is named db.py OR when the diff adds a
# MIGRATIONS.append line — whichever comes first.
BASENAME=$(basename "$FILE_PATH")

if [[ "$BASENAME" == "db.py" ]]; then
  # Extract proposed new version from the tool input.
  if [[ "$TOOL" == "Write" ]]; then
    CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty')
  else
    CONTENT=$(echo "$INPUT" | jq -r '.tool_input.new_string // empty')
  fi

  # Find any N in `MIGRATIONS.append((N, ...))` patterns in the new content.
  PROPOSED_VERSIONS=$(echo "$CONTENT" | grep -oE 'MIGRATIONS\.append\(\([[:space:]]*[0-9]+' | grep -oE '[0-9]+' | sort -u)

  if [[ -z "$PROPOSED_VERSIONS" ]]; then
    # No migration addition in this diff → allow.
    exit 0
  fi

  # Current versions in the existing file.
  if [[ -f "$FILE_PATH" ]]; then
    EXISTING_VERSIONS=$(grep -oE 'MIGRATIONS\.append\(\([[:space:]]*[0-9]+' "$FILE_PATH" | grep -oE '[0-9]+' | sort -u)
  else
    EXISTING_VERSIONS=""
  fi

  CONFLICTS=()
  for v in $PROPOSED_VERSIONS; do
    if echo "$EXISTING_VERSIONS" | grep -qw "$v"; then
      # Edit tool rewrites a line — only flag if the OLD string didn't
      # already contain this version (i.e. truly adding a dup, not
      # renaming an existing one).
      if [[ "$TOOL" == "Edit" ]]; then
        OLD_STRING=$(echo "$INPUT" | jq -r '.tool_input.old_string // empty')
        if echo "$OLD_STRING" | grep -qE "MIGRATIONS\.append\(\([[:space:]]*${v}[^0-9]"; then
          continue  # this edit is replacing the v entry in-place
        fi
      fi
      CONFLICTS+=("$v")
    fi
  done

  if [[ ${#CONFLICTS[@]} -gt 0 ]]; then
    NEXT=$(echo "$EXISTING_VERSIONS" | sort -n | tail -1)
    NEXT=$(( NEXT + 1 ))
    echo "BLOCKED: duplicate migration version(s): ${CONFLICTS[*]}" >&2
    echo "  File: $FILE_PATH" >&2
    echo "  Existing versions: $(echo "$EXISTING_VERSIONS" | paste -sd',' -)" >&2
    echo "  CLAUDE.md Rule #10 — migrations are append-only." >&2
    echo "  Use the next available version: $NEXT" >&2
    exit 2
  fi
  exit 0
fi

# --- Numbered framework migrations -----------------------------------
# Typical layout: backend/apps/<app>/migrations/NNNN_name.py
# New Write creating 0003_foo.py when 0003_bar.py exists → conflict.
if [[ "$FILE_PATH" == *migrations/*.py ]] && [[ "$TOOL" == "Write" ]]; then
  if [[ ! -f "$FILE_PATH" ]]; then
    DIR=$(dirname "$FILE_PATH")
    NEW_PREFIX=$(basename "$FILE_PATH" | grep -oE '^[0-9]+' || true)
    if [[ -n "$NEW_PREFIX" ]] && [[ -d "$DIR" ]]; then
      EXISTING=$(find "$DIR" -maxdepth 1 -name "${NEW_PREFIX}_*.py" ! -path "$FILE_PATH" | head -3)
      if [[ -n "$EXISTING" ]]; then
        echo "BLOCKED: migration prefix ${NEW_PREFIX} already used in $DIR:" >&2
        echo "$EXISTING" | sed 's/^/  - /' >&2
        echo "  Use the next available prefix. Regenerate with \`makemigrations\`." >&2
        exit 2
      fi
    fi
  fi
fi

exit 0
