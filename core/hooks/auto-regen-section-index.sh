#!/usr/bin/env bash
# PostToolUse hook (TASK-165): after Write/Edit on a fat .md file (≥400
# lines or ≥5k tokens), regenerate the sidecar `<file>.INDEX.md` so
# `cos_doc_section` can route to a stable slug + fresh line range.
#
# Design:
#   - Scoped: only fires for `*.md` outside `*/.coding-os/*` etc, and skips
#     the index sidecars themselves (`*.INDEX.md`, `00-index.md`).
#   - Threshold-aware: the Python regen script decides whether to write —
#     this hook just dispatches. Sub-threshold edits are silently skipped
#     by the script (so we never auto-create an INDEX for a small file).
#   - Debounced: 5-second per-file lockfile suppresses regen storms when
#     an agent edits the same file in quick succession.
#   - Fire-and-forget: worker forks to background, hook returns in <50 ms.
#   - Fail-open: missing python or missing script = silent skip into
#     $COS_STATE_DIR/.section-index-errors.log (bounded ~200 lines).
#   - Adapter-agnostic: reads COS_STATE_DIR / COS_PROJECT_ROOT from
#     cos-env.sh; never hardcodes `.claude/` (Rule 1).
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi


INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
[[ -z "$FILE_PATH" ]] && exit 0

# Scope: only .md files. Skip sidecars and dir-level indices — the
# `auto-regen-doc-index.sh` hook owns those.
case "$FILE_PATH" in
  *.md) ;;
  *) exit 0 ;;
esac
case "$FILE_PATH" in
  *.INDEX.md|*/00-index.md) exit 0 ;;
  */.coding-os/*|*/.claude/*|*/.codex/*|*/node_modules/*) exit 0 ;;
  */tests/*|*/scaffold/*) exit 0 ;;
esac

cos_log_hook auto-regen-section-index fire "file=${FILE_PATH}"

PROJECT_ROOT="${COS_PROJECT_ROOT:-$PWD}"
SCRIPT_PATH=""
for candidate in \
  "${PROJECT_ROOT}/scripts/regen_section_index.py" \
  "$(dirname "$0")/../../scripts/regen_section_index.py"; do
  if [[ -f "$candidate" ]]; then
    SCRIPT_PATH="$candidate"
    break
  fi
done

if [[ -z "$SCRIPT_PATH" ]]; then
  cos_log_hook auto-regen-section-index skip "reason=script_missing"
  exit 0
fi

# ── Debounce ─────────────────────────────────────────────────────────
_DEBOUNCE_TTL=5
_STATE_BASE="${COS_STATE_DIR:-${PROJECT_ROOT}/.coding-os}"
_SAFE_PATH=$(printf '%s' "$FILE_PATH" | tr '/' '_' | tr ' ' '_')
_DEBOUNCE_FILE="${_STATE_BASE}/.regen-section-index-debounce-${_SAFE_PATH}"
_NOW=$(date +%s)
if [[ -f "$_DEBOUNCE_FILE" ]]; then
  _LAST=$(cat "$_DEBOUNCE_FILE" 2>/dev/null || echo 0)
  if (( _NOW - _LAST < _DEBOUNCE_TTL )); then
    cos_log_hook auto-regen-section-index skip "reason=debounced file=${FILE_PATH##*/}"
    exit 0
  fi
fi
mkdir -p "$(dirname "$_DEBOUNCE_FILE")"
echo "$_NOW" > "$_DEBOUNCE_FILE"

ERR_LOG="${_STATE_BASE}/.section-index-errors.log"
mkdir -p "$(dirname "$ERR_LOG")"

# ── Fire-and-forget regen in background ──────────────────────────────
# Failures land in $ERR_LOG (bounded 200 lines). The script itself
# silently skips files below the size threshold, so a no-op edit on a
# small doc is invisible here.
(
  "${COS_PYTHON:-python3}" "$SCRIPT_PATH" "$FILE_PATH" >/dev/null 2>>"$ERR_LOG" &
) &

if [[ -f "$ERR_LOG" ]]; then
  LINES=$(wc -l < "$ERR_LOG" 2>/dev/null || echo 0)
  if (( LINES > 200 )); then
    tail -n 200 "$ERR_LOG" > "${ERR_LOG}.tmp" && mv "${ERR_LOG}.tmp" "$ERR_LOG"
  fi
fi

cos_log_hook auto-regen-section-index dispatched "file=${FILE_PATH}"
exit 0
