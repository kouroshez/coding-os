#!/usr/bin/env bash
# PostToolUse hook: After Write/Edit, show verification reminder + impact warnings.
#
# 1. Reminds which verification suite to run
# 2. Detects high-impact changes (models, serializers, services) and warns
#    about files that import the changed module — prevents silent breakage
#
# Source: AGENTS.md § Verification Matrix
set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Skip empty paths
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# ── Verification reminder ─────────────────────────────────────────────

case "$FILE_PATH" in
  *docs/*.md|*.claude/rules/*.md|*.coding-os/*.md)
    echo "[hook] Doc/rule file changed: $(basename "$FILE_PATH")"
    echo "  Run: make docs-lint"
    ;;
  *backend/*.py)
    # Skip migrations and __pycache__
    if [[ "$FILE_PATH" == *migrations* ]] || [[ "$FILE_PATH" == *__pycache__* ]]; then
      exit 0
    fi
    echo "[hook] Backend file changed: $(basename "$FILE_PATH")"
    echo "  Run: make lint-backend && make test-backend"
    ;;
  *frontend/*.ts|*frontend/*.tsx|*frontend/*.js|*frontend/*.jsx)
    echo "[hook] Frontend file changed: $(basename "$FILE_PATH")"
    echo "  Run: cd frontend && npm run lint"
    ;;
  *)
    exit 0
    ;;
esac

# ── Impact analysis (backend .py only) ────────────────────────────────

if [[ "$FILE_PATH" != *backend/*.py ]]; then
  exit 0
fi

# Determine if this is a high-impact file type
BASENAME=$(basename "$FILE_PATH" .py)
DIRNAME=$(dirname "$FILE_PATH")
IS_HIGH_IMPACT=false
IMPACT_TYPE=""

case "$FILE_PATH" in
  */models/*.py|*/models.py)
    IS_HIGH_IMPACT=true
    IMPACT_TYPE="MODEL"
    ;;
  */serializers/*.py|*/serializers.py)
    IS_HIGH_IMPACT=true
    IMPACT_TYPE="SERIALIZER"
    ;;
  */services/*.py)
    IS_HIGH_IMPACT=true
    IMPACT_TYPE="SERVICE"
    ;;
  */views/*.py)
    IS_HIGH_IMPACT=true
    IMPACT_TYPE="VIEW"
    ;;
  */exceptions.py)
    IS_HIGH_IMPACT=true
    IMPACT_TYPE="EXCEPTION"
    ;;
esac

if ! $IS_HIGH_IMPACT; then
  exit 0
fi

# Find who imports this module (quick grep, max 5 results)
# Extract the module path for import matching
# e.g., backend/apps/commerce/models/order.py → apps.commerce.models.order or apps.commerce.models
MODULE_REL="${FILE_PATH#*backend/}"           # apps/commerce/models/order.py
MODULE_DOT="${MODULE_REL%.py}"                # apps/commerce/models/order
MODULE_DOT="${MODULE_DOT//\//.}"              # apps.commerce.models.order

# Also check parent package import (from apps.commerce.models import Order)
PARENT_DOT="${MODULE_DOT%.*}"                 # apps.commerce.models

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

IMPORTERS=$(grep -rl --include="*.py" \
  -e "from $MODULE_DOT" \
  -e "from $PARENT_DOT import" \
  -e "import $MODULE_DOT" \
  "$PROJECT_ROOT/backend/" 2>/dev/null | \
  grep -v __pycache__ | \
  grep -v migrations | \
  head -8 || true)

if [[ -n "$IMPORTERS" ]]; then
  COUNT=$(echo "$IMPORTERS" | wc -l | tr -d ' ')
  echo ""
  echo "  ⚠️  IMPACT: $IMPACT_TYPE changed — $COUNT file(s) import this module:"
  while IFS= read -r imp; do
    REL="${imp#$PROJECT_ROOT/}"
    echo "    → $REL"
  done <<< "$IMPORTERS"
  echo "  Check these files for compatibility after your change."
fi

# ── Cynefin complexity sanity check (non-blocking warning) ────────────
# If the agent classified as CLEAR 1 but the session is accumulating
# many changed files, warn that the classification may be too low.

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
GATE_FILE="$PROJECT_ROOT/${COS_AGENT_DIR}/.thinking_os-gate"
if [[ -f "$GATE_FILE" ]]; then
  GATE_CONTENT=$(head -1 "$GATE_FILE")
  GATE_CLASS=$(echo "$GATE_CONTENT" | awk '{print $2}')
  GATE_DIMS=$(echo "$GATE_CONTENT" | awk '{print $3}')

  if [[ "$GATE_CLASS" == "CLEAR" ]] && [[ "$GATE_DIMS" == "1" ]]; then
    # Count distinct files changed in this git session
    CHANGED_COUNT=$(git diff --name-only HEAD 2>/dev/null | wc -l | tr -d ' ')
    DIFF_LINES=$(git diff --stat HEAD 2>/dev/null | tail -1 | grep -oE '[0-9]+ insertion|[0-9]+ deletion' | awk '{s+=$1} END {print s+0}')

    if [[ "$CHANGED_COUNT" -gt 3 ]] || [[ "${DIFF_LINES:-0}" -gt 100 ]]; then
      echo ""
      echo "  ⚠️  COMPLEXITY CHECK: Classified as CLEAR 1 but $CHANGED_COUNT files / ${DIFF_LINES:-0} lines changed."
      echo "  Consider reclassifying to COMPLICATED if scope has grown."
    fi
  fi
fi

exit 0
