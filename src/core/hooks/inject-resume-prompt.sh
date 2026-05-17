#!/usr/bin/env bash
# SessionStart hook — surface active audits left from prior sessions.
#
# When a session begins (startup, compact, resume), scan
# docs/tasks/audits/ for audit-*.md files with status:in_progress.
# If any found, inject a one-line additionalContext block listing
# them with their first unchecked category — so the agent picks up
# exactly where it left off rather than re-discovering the gap.
#
# This closes the "context compacted, audit forgotten" failure mode
# that the compaction-resilient artifact (G12) exists to defeat.
# Always exits 0.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

AUDIT_DIR="docs/tasks/audits"
if [[ ! -d "$AUDIT_DIR" ]]; then
  exit 0
fi

# Collect active audit files (status:in_progress in frontmatter).
ACTIVE_FILES=()
while IFS= read -r f; do
  [[ -n "$f" ]] && ACTIVE_FILES+=("$f")
done < <(grep -l "^status: in_progress" "$AUDIT_DIR"/audit-*.md 2>/dev/null || true)

if [[ ${#ACTIVE_FILES[@]} -eq 0 ]]; then
  exit 0
fi

cos_log_hook inject-resume-prompt fire "count=${#ACTIVE_FILES[@]}"

# Build the resume summary. For each active audit, extract audit_id +
# count rows where Verified column is 'no'.
SUMMARY="Active audits to resume:"
for f in "${ACTIVE_FILES[@]}"; do
  AID=$(grep -m1 "^audit_id:" "$f" 2>/dev/null | sed 's/audit_id:[[:space:]]*//')
  TID=$(grep -m1 "^task_id:" "$f" 2>/dev/null | sed 's/task_id:[[:space:]]*//')
  # Count unchecked rows — table cells where Verified=no.
  # Match rows that look like data rows (start with `|` and contain `| no |`).
  UNCHECKED=$(grep -cE '^\|.*\| no \|' "$f" 2>/dev/null || echo 0)
  SUMMARY="${SUMMARY} · ${AID} (task=${TID}, ${UNCHECKED} unchecked rows) at ${f}"
done

CONTEXT="[Audit resume] ${SUMMARY}. The completion guardian still expects every row in these files to end with Verified=yes and Hits after=0 before any 'done' claim. Re-open the file before continuing — do NOT re-derive scope from chat history."

printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":$(printf '%s' "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"

exit 0
