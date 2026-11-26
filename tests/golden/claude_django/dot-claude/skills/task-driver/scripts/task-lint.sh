#!/usr/bin/env bash
# Lint one or more TASK-NNN-slug.md files for Scrumban discipline.
#
# Checks:
#   - Frontmatter: id, title, status, swimlane, kind exist + valid values
#   - Required body sections: Outcome, Read First, Acceptance
#   - Body size: warn > 1.5K bytes, block > 3K (Rule 14: tasks are pointers, not specs)
#   - Internal links resolve (relative paths exist)
#
# Usage:
#   bash task-lint.sh docs/tasks/TASK-NNN-slug.md
#   bash task-lint.sh docs/tasks/                  # lint a directory
#   bash task-lint.sh --json docs/tasks/
#
# Exit codes:
#   0 = all clean
#   1 = warnings only (size or recoverable)
#   2 = hard error (missing required fields)

set -euo pipefail

# Safety: ensure core POSIX tools resolvable even when caller PATH is restricted.
export PATH="/usr/bin:/bin:/usr/local/bin:${PATH:-}"

EMIT_JSON=0
TARGETS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --json) EMIT_JSON=1; shift ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) TARGETS+=("$1"); shift ;;
  esac
done

if [ "${#TARGETS[@]}" -eq 0 ]; then
  echo "usage: $0 [--json] <task.md | tasks-dir> ..." >&2
  exit 2
fi

# Expand directories to .md files
FILES=()
for t in "${TARGETS[@]}"; do
  if [ -d "$t" ]; then
    while IFS= read -r f; do
      FILES+=("$f")
    done < <(find "$t" -maxdepth 1 -name "TASK-*.md" -type f | sort)
  elif [ -f "$t" ]; then
    FILES+=("$t")
  else
    echo "Not found: $t" >&2
    exit 2
  fi
done

if [ "${#FILES[@]}" -eq 0 ]; then
  echo "No TASK-*.md files found in inputs" >&2
  exit 2
fi

VALID_STATUS="^(backlog|in_progress|testing|blocked|complete|archived)$"
VALID_SWIMLANE="^(backend|frontend|mobile|docs|meta|ops|infra|cross)$"
VALID_KIND="^(feat|fix|chore|refactor|docs|test|spike)$"

declare -i exit_code=0
declare -a FINDINGS=()

# JSON helper: emit a finding tuple
add_finding() {
  local file="$1" sev="$2" msg="$3"
  FINDINGS+=("$file|$sev|$msg")
  if [ "$sev" = "ERROR" ]; then exit_code=2; fi
  if [ "$sev" = "WARN" ] && [ "$exit_code" -lt 1 ]; then exit_code=1; fi
}

extract_fm_field() {
  local file="$1" field="$2"
  awk -v field="$field" '
    BEGIN { in_fm=0 }
    /^---$/ { in_fm = !in_fm; if (in_fm == 0) exit; next }
    in_fm == 1 && $0 ~ "^"field":" {
      sub("^"field":[ \t]*", "")
      gsub("\"", "")
      print
      exit
    }
  ' "$file"
}

has_section() {
  local file="$1" heading="$2"
  grep -qE "^##[ ]+${heading}\b" "$file"
}

for f in "${FILES[@]}"; do
  # Frontmatter checks
  if ! head -1 "$f" | grep -qE "^---$"; then
    add_finding "$f" "ERROR" "missing frontmatter (no leading '---')"
    continue
  fi

  id=$(extract_fm_field "$f" "id" || true)
  status=$(extract_fm_field "$f" "status" || true)
  swimlane=$(extract_fm_field "$f" "swimlane" || true)
  kind=$(extract_fm_field "$f" "kind" || true)
  title=$(extract_fm_field "$f" "title" || true)

  [ -z "$id" ] && add_finding "$f" "ERROR" "frontmatter missing 'id'"
  [ -z "$title" ] && add_finding "$f" "ERROR" "frontmatter missing 'title'"
  [ -z "$status" ] && add_finding "$f" "ERROR" "frontmatter missing 'status'"
  [ -z "$swimlane" ] && add_finding "$f" "WARN" "frontmatter missing 'swimlane'"
  [ -z "$kind" ] && add_finding "$f" "WARN" "frontmatter missing 'kind'"

  if [ -n "$status" ] && ! [[ "$status" =~ $VALID_STATUS ]]; then
    add_finding "$f" "ERROR" "invalid status '$status' (must be: backlog|in_progress|testing|blocked|complete|archived)"
  fi
  if [ -n "$swimlane" ] && ! [[ "$swimlane" =~ $VALID_SWIMLANE ]]; then
    add_finding "$f" "WARN" "invalid swimlane '$swimlane'"
  fi
  if [ -n "$kind" ] && ! [[ "$kind" =~ $VALID_KIND ]]; then
    add_finding "$f" "WARN" "invalid kind '$kind'"
  fi

  # Body required sections
  has_section "$f" "Outcome" || add_finding "$f" "ERROR" "missing '## Outcome' section"
  has_section "$f" "Read First" || add_finding "$f" "WARN" "missing '## Read First' section"
  has_section "$f" "Acceptance" || add_finding "$f" "ERROR" "missing '## Acceptance' section"

  # Size (Rule 14)
  bytes=$(wc -c < "$f" | tr -d ' ')
  if [ "$bytes" -gt 3000 ]; then
    add_finding "$f" "ERROR" "body size ${bytes}B > 3K — tasks are pointers, not specs (Rule 14)"
  elif [ "$bytes" -gt 1500 ]; then
    add_finding "$f" "WARN" "body size ${bytes}B > 1.5K — consider linking to a spec doc instead"
  fi
done

# Emit
if [ "$EMIT_JSON" -eq 1 ]; then
  printf '['
  first=1
  for entry in "${FINDINGS[@]+"${FINDINGS[@]}"}"; do
    file="${entry%%|*}"; rest="${entry#*|}"
    sev="${rest%%|*}"; msg="${rest#*|}"
    [ $first -eq 0 ] && printf ','
    printf '\n  {"file": "%s", "severity": "%s", "message": "%s"}' "$file" "$sev" "$(echo "$msg" | sed 's/"/\\"/g')"
    first=0
  done
  printf '\n]\n'
else
  if [ "${#FINDINGS[@]}" -eq 0 ]; then
    echo "[task-lint] OK: ${#FILES[@]} task file(s) clean."
  else
    echo "[task-lint] ${#FINDINGS[@]} finding(s) across ${#FILES[@]} file(s):"
    for entry in "${FINDINGS[@]}"; do
      file="${entry%%|*}"; rest="${entry#*|}"
      sev="${rest%%|*}"; msg="${rest#*|}"
      printf "  [%-5s] %s — %s\n" "$sev" "$file" "$msg"
    done
  fi
fi

exit "$exit_code"
