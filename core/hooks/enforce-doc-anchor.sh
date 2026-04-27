#!/usr/bin/env bash
# PreToolUse Write|Edit hook: enforce the docs-first principle.
#
# Rule (from the project charter): "Docs are always source of truth. A
# code change must either (a) trace to a doc, or (b) be approved by the
# user explicitly." This hook checks that the active task has a
# populated "Source of Truth" or "Read First" section BEFORE any code
# Write/Edit lands.
#
# Flow:
#   1. Task file parsed by task-start.sh — on success it writes
#      $COS_AGENT_DIR/.doc-anchor with the extracted Source of Truth /
#      Read First paths.
#   2. This hook reads .doc-anchor and verifies it exists + is non-empty.
#   3. If missing / placeholder → BLOCK with a clear repair path.
#
# Scope: runs only on CODE files (.py, .ts, .tsx, .js, .jsx, .go, .rs).
# Docs, config, tests, and scaffold edits are exempt — they ARE the
# source of truth, so requiring a doc anchor is circular.
#
# Escape hatches (all one-shot):
#   - CLEAR 1 gate: agent has classified as trivial → allowed
#   - $COS_AGENT_DIR/.doc-anchor-override: manual bypass (consumed on use)
#   - Task name contains "exploratory" or "spike" → allowed
#
# Philosophy: fail-closed but with generous repair paths. The goal is to
# make "I didn't read the spec" impossible to hide, not to slow down
# every keystroke.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
# Fail-open if state dir is absent (fresh clone, mid-init, off-project cwd).
cos_sanity_check enforce-doc-anchor state_dir 2>/dev/null || true

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
[[ -z "$FILE_PATH" ]] && exit 0

# Only enforce on CODE. Docs/tests/config/state files are exempt — they
# ARE the source of truth.
case "$FILE_PATH" in
  *.py|*.ts|*.tsx|*.js|*.jsx|*.go|*.rs|*.rb) ;;
  *) exit 0 ;;
esac

BASENAME=$(basename "$FILE_PATH")
case "$BASENAME" in
  test_*|*_test.*|*.test.*|*.spec.*|conftest.py) exit 0 ;;
esac
case "$FILE_PATH" in
  */tests/*|*/migrations/*|*/__pycache__/*|*/node_modules/*) exit 0 ;;
  */.venv/*|*/.coding-os/*|*/.claude/*|*/.codex/*) exit 0 ;;
  */scaffold/*) exit 0 ;;
esac

COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"

file_age_seconds() {
  local file_path="$1"
  if [[ "$(uname)" == "Darwin" ]]; then
    echo $(( $(date +%s) - $(stat -f %m "$file_path") ))
  else
    echo $(( $(date +%s) - $(stat -c %Y "$file_path") ))
  fi
}

# --- Escape hatches --------------------------------------------------

# CLEAR 1 trivial path — ad-hoc fixes don't need a doc anchor.
source "$(dirname "$0")/check-state.sh" 2>/dev/null || true
if type check_state >/dev/null 2>&1; then
  check_state "${COS_AGENT_DIR}/.thinking_os-gate" 7200
  if [[ "${STATE_VALID:-}" == "true" ]]; then
    CLASS=$(echo "${STATE_VALUE:-}" | awk '{print $1}')
    DIMS=$(echo "${STATE_VALUE:-}" | awk '{print $2}')
    if [[ "$CLASS" == "CLEAR" ]] && [[ "$DIMS" == "1" ]]; then
      exit 0
    fi
  fi
fi

# Exploratory / spike tasks — allow. The task-name marker signals intent.
if type check_state >/dev/null 2>&1; then
  check_state "${COS_AGENT_DIR}/.task-current" 28800
  if [[ "${STATE_VALID:-}" == "true" ]]; then
    TASK_NAME="${STATE_VALUE:-}"
    case "$TASK_NAME" in
      *exploratory*|*spike*|*experiment*|*scratch*|*governance*|*docs-update*)
        exit 0 ;;
    esac
  fi
fi

# One-shot manual override (consumed on use). Unified registry preferred;
# legacy $COS_AGENT_DIR/.doc-anchor-override still honoured.
if cos_one_shot_override doc-anchor 2>/dev/null; then
  exit 0
fi

# --- The actual check ------------------------------------------------

ANCHOR_FILE="$COS_AGENT_DIR/.doc-anchor"
ANCHOR_MAX_AGE=28800  # 8h — same ownership horizon as task-current.

if [[ ! -f "$ANCHOR_FILE" ]]; then
  echo "BLOCKED: No doc anchor recorded for this task." >&2
  echo "  Rule: code changes must trace to a spec / playbook / ADR." >&2
  echo "  File attempted: $FILE_PATH" >&2
  echo "" >&2
  echo "  Three ways to repair:" >&2
  echo "  1. Populate the task file's \"Source of Truth\" or \"Read First\"" >&2
  echo "     section with real doc paths, then re-run \`make task-start TASK=N\`." >&2
  echo "  2. If this is a trivial fix (typo, docstring), record CLEAR 1:" >&2
  echo "       bash \"\$COS_AGENT_DIR/hooks/write-state.sh\" \"\$COS_AGENT_DIR/.thinking_os-gate\" \"CLEAR 1\"" >&2
  echo "  3. If genuinely exploratory, set an exploratory task name:" >&2
  echo "       bash \"\$COS_AGENT_DIR/hooks/write-state.sh\" \"\$COS_AGENT_DIR/.task-current\" \"exploratory-<slug>\"" >&2
  echo "" >&2
  echo "  For a one-shot bypass (use sparingly):" >&2
  echo "    touch $COS_AGENT_DIR/.doc-anchor-override" >&2
  exit 2
fi

# Session-aware anchors use the first line as "<session-id> task:<id>".
# Legacy anchors (pre-session prefix) are allowed only while fresh.
ANCHOR_HEADER=$(head -1 "$ANCHOR_FILE" 2>/dev/null || true)
if echo "$ANCHOR_HEADER" | grep -qE '^ses-[^[:space:]]+[[:space:]]+task:'; then
  if type check_state >/dev/null 2>&1; then
    check_state "$ANCHOR_FILE" "$ANCHOR_MAX_AGE"
    if [[ "${STATE_VALID:-}" != "true" ]]; then
      echo "BLOCKED: Doc anchor is stale or belongs to another session." >&2
      echo "  File: $ANCHOR_FILE" >&2
      echo "  Reason: ${STATE_REASON:-unknown}" >&2
      echo "  Re-run \`make task-start TASK=N\` so the anchor refreshes for this session." >&2
      exit 2
    fi
  fi
  ANCHOR_CONTENT=$(tail -n +2 "$ANCHOR_FILE" | head -20)
else
  FILE_AGE=$(file_age_seconds "$ANCHOR_FILE")
  if [[ "$FILE_AGE" -gt "$ANCHOR_MAX_AGE" ]]; then
    echo "BLOCKED: Legacy doc anchor is stale and cannot prove session ownership." >&2
    echo "  File: $ANCHOR_FILE" >&2
    echo "  Re-run \`make task-start TASK=N\` to refresh the anchor with a session header." >&2
    exit 2
  fi
  ANCHOR_CONTENT=$(head -20 "$ANCHOR_FILE")
fi

if [[ -z "$(echo "$ANCHOR_CONTENT" | tr -d '[:space:]')" ]]; then
  echo "BLOCKED: Doc anchor is empty for this session." >&2
  echo "  File: $ANCHOR_FILE" >&2
  echo "  Populate Source of Truth / Read First, then re-run \`make task-start TASK=N\`." >&2
  exit 2
fi

# Check the anchor is a real reference, not a placeholder.
if echo "$ANCHOR_CONTENT" | grep -qiE '^\s*(-\s*)?(\{[^}]*\}|_\(unfilled\)_|_\(not[[:space:]]+recorded\)_|_\(to[[:space:]]+be[[:space:]]+defined\)_|none|tbd|n/a|`?docs/\.\.\.`?|`?path/to/code\.ext`?)\s*$|^\s*\*\*REQUIRED\b|^\s*-\s*Pre-implementation:\s*`?docs/\.\.\.`?\s*$|^\s*-\s*Post-implementation:\s*`?path/to/code\.ext`?\s*$'; then
  echo "BLOCKED: Doc anchor is a placeholder, not a real reference." >&2
  echo "  File: $ANCHOR_FILE" >&2
  echo "  Populate the Source of Truth / Read First in the active task file," >&2
  echo "  then re-run \`make task-start\` so the anchor gets refreshed." >&2
  exit 2
fi

exit 0
