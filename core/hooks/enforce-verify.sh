#!/usr/bin/env bash
# PreToolUse hook: BLOCK make task-done unless domain-appropriate verification
# has been run recently. Reads $COS_STATE_DIR/.last-verify.json for per-suite results.
#
# Domain detection: checks git diff to determine which domains changed,
# then requires the matching verification suites to have passed.
set -euo pipefail

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

# Only intercept Bash calls
if [[ "$TOOL" != "Bash" ]]; then
  exit 0
fi

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only check make task-done calls
if [[ "$COMMAND" != *"make"*"task-done"* ]]; then
  cos_log_hook enforce-verify fire "tool=Bash task_done=false"
  exit 0
fi

cos_log_hook enforce-verify fire "tool=Bash task_done=true"
VERIFY_FILE="${COS_STATE_DIR}/.last-verify.json"
MAX_AGE=1800  # 30 minutes

# ── Detect changed domains ──────────────────────────────────────────

CHANGED_FILES=$(git diff --name-only HEAD 2>/dev/null || true)
if [[ -z "$CHANGED_FILES" ]]; then
  # No changes detected — allow (might be a documentation-only task)
  exit 0
fi

NEEDS_BACKEND=false
NEEDS_FRONTEND=false
NEEDS_FRONTEND_E2E=false
NEEDS_DOCS=false

while IFS= read -r file; do
  case "$file" in
    backend/*) NEEDS_BACKEND=true ;;
    frontend/app/*/checkout/*|frontend/app/*/cart/*|frontend/components/providers/cart-provider*|frontend/components/cart/*|frontend/app/*/thank-you/*)
      NEEDS_FRONTEND=true
      NEEDS_FRONTEND_E2E=true
      ;;
    frontend/*) NEEDS_FRONTEND=true ;;
    docs/*) NEEDS_DOCS=true ;;
  esac
done <<< "$CHANGED_FILES"

# Build list of required suites
REQUIRED=()
if $NEEDS_BACKEND; then
  REQUIRED+=("lint-backend" "test-backend")
fi
if $NEEDS_FRONTEND; then
  REQUIRED+=("lint-frontend")
fi
if $NEEDS_FRONTEND_E2E; then
  REQUIRED+=("test-frontend-e2e")
fi
if $NEEDS_DOCS; then
  REQUIRED+=("docs-lint")
fi

# No domain-specific requirements detected — allow
if [[ ${#REQUIRED[@]} -eq 0 ]]; then
  exit 0
fi

# ── Check verification results ──────────────────────────────────────

if [[ ! -f "$VERIFY_FILE" ]]; then
  # Fall back to legacy flat file
  LEGACY_FILE="${COS_STATE_DIR}/.last-verify"
  if [[ -f "$LEGACY_FILE" ]]; then
    LEGACY_STATUS=$(head -1 "$LEGACY_FILE")
    if [[ "$(uname)" == "Darwin" ]]; then
      LEGACY_AGE=$(( $(date +%s) - $(stat -f %m "$LEGACY_FILE") ))
    else
      LEGACY_AGE=$(( $(date +%s) - $(stat -c %Y "$LEGACY_FILE") ))
    fi
    if [[ "$LEGACY_STATUS" == "PASS" ]] && [[ "$LEGACY_AGE" -le "$MAX_AGE" ]]; then
      exit 0
    fi
  fi

  echo "BLOCKED: No verification results found. Run the required checks:" >&2
  cos_log_hook enforce-verify block "reason=missing-results suites=${#REQUIRED[@]}"
  for suite in "${REQUIRED[@]}"; do
    echo "  make $suite" >&2
  done
  exit 2
fi

NOW=$(date +%s)
MISSING=()

for suite in "${REQUIRED[@]}"; do
  # Check suite exists in JSON, has PASS status, and is fresh
  RESULT=$(python3 -c "
import json, sys
with open('$VERIFY_FILE') as f:
    data = json.load(f)
suite = '$suite'
entry = data.get(suite, {})
status = entry.get('status', 'MISSING')
ts = entry.get('ts', 0)
age = $NOW - ts
if status != 'PASS':
    print(f'FAIL:{suite}:status={status}')
elif age > $MAX_AGE:
    print(f'STALE:{suite}:age={age // 60}min')
else:
    print('OK')
" 2>/dev/null || echo "ERROR:$suite:parse_failed")

  if [[ "$RESULT" != "OK" ]]; then
    MISSING+=("$suite")
  fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
  cos_log_hook enforce-verify block "reason=missing-or-stale suites=${#MISSING[@]}"
  echo "BLOCKED: Required verifications not satisfied. Run:" >&2
  for suite in "${MISSING[@]}"; do
    echo "  make $suite" >&2
  done
  echo "" >&2
  echo "Changed domains: backend=$NEEDS_BACKEND frontend=$NEEDS_FRONTEND docs=$NEEDS_DOCS" >&2
  exit 2
fi

# ── Impact warnings (non-blocking) ─────────────────────────────────

# Warn if high-impact backend files changed (models, serializers, exceptions)
if $NEEDS_BACKEND; then
  HIGH_IMPACT=$(echo "$CHANGED_FILES" | grep -E '(models/|serializers/|exceptions\.py|services/)' | grep -v migrations || true)
  if [[ -n "$HIGH_IMPACT" ]]; then
    echo "⚠️  HIGH-IMPACT backend files changed:" >&2
    echo "$HIGH_IMPACT" | while IFS= read -r f; do echo "    → $f" >&2; done
    echo "  Verify dependent files (views, serializers, tests) are compatible." >&2
    echo "" >&2
  fi
fi

exit 0
