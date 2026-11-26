#!/usr/bin/env bash
# Static-analyse SQL migration files for unsafe patterns under concurrent
# load on production-sized tables.
#
# Patterns flagged (severity in []):
#   [ERROR] ALTER TABLE ... ADD COLUMN ... NOT NULL (without DEFAULT)
#           — locks + rewrites large tables
#   [ERROR] ALTER TABLE ... ALTER COLUMN ... TYPE ... (non-trivial cast)
#           — full table rewrite
#   [WARN]  CREATE INDEX without CONCURRENTLY (Postgres)
#           — blocks writes for the duration
#   [WARN]  DROP COLUMN without IF EXISTS
#           — fails on rollback if column already removed
#   [WARN]  Migration modifies > 3 tables in one file
#           — should split for reviewability
#   [ERROR] Editing an existing migration file (git modify, not add)
#           — Rule 9: migrations are append-only
#
# Usage:
#   bash migration-safety.sh path/to/migration.sql ...
#   bash migration-safety.sh --json migrations/
#   bash migration-safety.sh --check-history  # also flag edits to existing files
#
# Exit code 1 on any ERROR.

set -euo pipefail

# Safety: ensure core POSIX tools resolvable even when caller PATH is restricted.
export PATH="/usr/bin:/bin:/usr/local/bin:${PATH:-}"

EMIT_JSON=0
CHECK_HISTORY=0
TARGETS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --json) EMIT_JSON=1; shift ;;
    --check-history) CHECK_HISTORY=1; shift ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) TARGETS+=("$1"); shift ;;
  esac
done

if [ "${#TARGETS[@]}" -eq 0 ]; then
  echo "usage: $0 [--json] [--check-history] <migration.sql | migrations-dir>" >&2
  exit 2
fi

# Expand directories
FILES=()
for t in "${TARGETS[@]}"; do
  if [ -d "$t" ]; then
    while IFS= read -r f; do FILES+=("$f"); done < <(find "$t" -name "*.sql" -type f | sort)
  elif [ -f "$t" ]; then
    FILES+=("$t")
  fi
done

declare -a FINDINGS=()
declare -i exit_code=0

add_finding() {
  local file="$1" line="$2" sev="$3" msg="$4"
  FINDINGS+=("$file|$line|$sev|$msg")
  if [ "$sev" = "ERROR" ]; then exit_code=1; fi
}

for f in "${FILES[@]}"; do
  # Append-only check (Rule 9)
  if [ "$CHECK_HISTORY" -eq 1 ] && command -v git >/dev/null 2>&1; then
    if [ -d "$(git rev-parse --show-toplevel 2>/dev/null || echo /nonexistent)" ]; then
      # Already-committed file being modified
      if git diff --cached --name-only 2>/dev/null | grep -qF "$f" \
         && git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
        # File is tracked AND staged for modification — possible Rule 9 violation
        if ! git diff --cached -- "$f" | head -1 | grep -q '^new file'; then
          add_finding "$f" "0" "ERROR" "editing existing migration (Rule 9: append-only). Create a new vN+1 migration instead."
        fi
      fi
    fi
  fi

  # Read file with line numbers for pattern checks
  while IFS=':' read -r linenum content; do
    upper=$(echo "$content" | tr 'a-z' 'A-Z')

    # ADD COLUMN ... NOT NULL without DEFAULT
    if echo "$upper" | grep -qE 'ADD COLUMN.*NOT NULL'; then
      if ! echo "$upper" | grep -qE 'DEFAULT'; then
        add_finding "$f" "$linenum" "ERROR" "ADD COLUMN NOT NULL without DEFAULT — locks table on large data. Use ADD COLUMN NULL → backfill → ALTER NOT NULL pattern."
      fi
    fi

    # ALTER COLUMN ... TYPE (full table rewrite on most types)
    if echo "$upper" | grep -qE 'ALTER COLUMN.*TYPE '; then
      add_finding "$f" "$linenum" "ERROR" "ALTER COLUMN TYPE rewrites the table. Use expand-contract pattern (add new column → backfill → switch reads → drop old)."
    fi

    # CREATE INDEX without CONCURRENTLY (Postgres specific)
    if echo "$upper" | grep -qE 'CREATE [^;]*INDEX' && ! echo "$upper" | grep -qE 'CONCURRENTLY'; then
      add_finding "$f" "$linenum" "WARN" "CREATE INDEX without CONCURRENTLY blocks writes for the duration. Add CONCURRENTLY (Postgres) for production use."
    fi

    # DROP COLUMN without IF EXISTS
    if echo "$upper" | grep -qE 'DROP COLUMN' && ! echo "$upper" | grep -qE 'IF EXISTS'; then
      add_finding "$f" "$linenum" "WARN" "DROP COLUMN without IF EXISTS fails if column already removed (poor for rollbacks)."
    fi

    # DROP TABLE (very loud)
    if echo "$upper" | grep -qE '^DROP TABLE'; then
      add_finding "$f" "$linenum" "WARN" "DROP TABLE is irreversible. Consider a rename → wait-period → drop pattern."
    fi
  done < <(grep -nv '^[[:space:]]*--' "$f" 2>/dev/null || true)

  # Multi-table change check
  table_count=$(grep -cE '^(ALTER|CREATE|DROP) (TABLE|INDEX|TRIGGER|VIEW|FUNCTION)' "$f" 2>/dev/null || echo 0)
  if [ "$table_count" -gt 3 ]; then
    add_finding "$f" "1" "WARN" "Migration touches $table_count tables/objects — consider splitting for reviewability + safer rollback."
  fi
done

# Emit
if [ "$EMIT_JSON" -eq 1 ]; then
  printf '['
  first=1
  for entry in "${FINDINGS[@]+"${FINDINGS[@]}"}"; do
    file="${entry%%|*}"; rest="${entry#*|}"
    line="${rest%%|*}"; rest="${rest#*|}"
    sev="${rest%%|*}"; msg="${rest#*|}"
    [ $first -eq 0 ] && printf ','
    printf '\n  {"file": "%s", "line": %d, "severity": "%s", "message": "%s"}' \
      "$file" "${line:-0}" "$sev" "$(echo "$msg" | sed 's/"/\\"/g')"
    first=0
  done
  printf '\n]\n'
else
  if [ "${#FINDINGS[@]}" -eq 0 ]; then
    echo "[migration-safety] OK: ${#FILES[@]} migration file(s) clean."
  else
    echo "[migration-safety] ${#FINDINGS[@]} finding(s) across ${#FILES[@]} migration(s):"
    for entry in "${FINDINGS[@]}"; do
      file="${entry%%|*}"; rest="${entry#*|}"
      line="${rest%%|*}"; rest="${rest#*|}"
      sev="${rest%%|*}"; msg="${rest#*|}"
      printf "  [%-5s] %s:%s — %s\n" "$sev" "$file" "$line" "$msg"
    done
  fi
fi

exit "$exit_code"
