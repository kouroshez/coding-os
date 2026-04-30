#!/usr/bin/env bash
# PreToolUse Write|Edit — block edits that violate scaffold-boundary.yaml.
#
# Reads the aggregated boundary file at $COS_STATE_DIR/scaffold-boundary.yaml
# (written by `cos init` when stacks are installed). When the file is absent
# or no boundary applies, the hook exits 0 — no policy means no enforcement.
#
# Boundary semantics (see docs/governance/scaffold-boundary-contract.md):
#   - Each stack declares roots / file_patterns / forbids_writing_in.
#   - The hook blocks a Write/Edit when the target path lives inside another
#     stack's `forbids_writing_in` and is not owned by any installed stack.
#
# Real Python lives in _enforce_scaffold_boundary.py — Rule 8 forbids
# heredoc inside `$(...)` with python3 (bash 5.3 deadlock surface).
# Fail-open by design: parser errors → silent skip + log entry, never block.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

PROJECT_ROOT="${COS_PROJECT_ROOT:-$PWD}"
BOUNDARY_FILE="${COS_STATE_DIR:-$PROJECT_ROOT/.coding-os}/scaffold-boundary.yaml"

if [[ ! -f "$BOUNDARY_FILE" ]]; then
  exit 0
fi

# Normalise to project-relative.
case "$FILE_PATH" in
  "${PROJECT_ROOT}/"*) REL_PATH="${FILE_PATH#${PROJECT_ROOT}/}" ;;
  /*)                  REL_PATH="$FILE_PATH" ;;
  *)                   REL_PATH="$FILE_PATH" ;;
esac

cos_log_hook enforce-scaffold-boundary fire "file=${REL_PATH}"

PY_DELEGATE="$(dirname "$0")/_enforce_scaffold_boundary.py"
if [[ ! -f "$PY_DELEGATE" ]]; then
  exit 0
fi

OUTPUT="$("${COS_PYTHON:-python3}" "$PY_DELEGATE" "$BOUNDARY_FILE" "$REL_PATH" "$PROJECT_ROOT" 2>&1)" || RC=$?
RC=${RC:-0}

if [[ $RC -eq 2 ]]; then
  echo "$OUTPUT" >&2
  cos_log_hook enforce-scaffold-boundary block "file=${REL_PATH}"
  exit 2
fi

if [[ -n "$OUTPUT" ]]; then
  echo "$OUTPUT" >&2
  cos_log_hook enforce-scaffold-boundary warn "file=${REL_PATH}"
fi

exit 0
