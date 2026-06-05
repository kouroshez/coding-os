#!/usr/bin/env bash
# PostToolUse hook (TASK-161): after Write/Edit on a docs/**/*.md file,
# regenerate the affected directory's 00-index.md from frontmatter.
#
# Design:
#   - Fire-and-forget: regen is a single-dir Python invocation; the
#     worker forks to background and the hook returns immediately.
#   - Scoped: only fires for paths matching `docs/**/*.md`. Reading,
#     skipping, and dispatching all happen in <50 ms.
#   - Debounced: 5-second per-directory lockfile prevents N parallel
#     regens when an agent edits multiple files in quick succession.
#   - Fail-open: missing python or missing script = silent skip into
#     $COS_STATE_DIR/.regen-doc-index-errors.log (bounded, ~200 lines).
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
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Scope: only docs/*.md and only inside the project's docs tree.
case "$FILE_PATH" in
  *.md) ;;
  *) exit 0 ;;
esac

PROJECT_ROOT="${COS_PROJECT_ROOT:-$PWD}"
DOCS_PREFIX="${PROJECT_ROOT%/}/docs/"
case "$FILE_PATH" in
  "$DOCS_PREFIX"*) ;;
  docs/*) ;;  # relative path form
  *) exit 0 ;;
esac

cos_log_hook auto-regen-doc-index fire "file=${FILE_PATH}"

# ── Resolve the target dir + the regen script ────────────────────────
TARGET_DIR=$(dirname "$FILE_PATH")
SCRIPT_PATH=""
# Resolve this hook through its (possibly symlinked) install path so a
# consumer's .claude/hooks/auto-regen-doc-index.sh → meta-repo symlink lands
# on the meta-repo's own src/scripts/regen_doc_index.py. Platform code runs
# from the platform; it is never copied into every consumer (TASK-119 — the
# script was unshipped, so the consumer-root candidates below never matched).
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
HOOK_REAL_DIR="$(cd -P "$(dirname "$_src")" && pwd 2>/dev/null)" || HOOK_REAL_DIR=""
# Primary: meta-repo script via the resolved hook. Fallbacks: a consumer that
# vendored the script under its own root (src/scripts or scripts).
for candidate in \
  "${HOOK_REAL_DIR:+${HOOK_REAL_DIR}/../../scripts/regen_doc_index.py}" \
  "${PROJECT_ROOT}/src/scripts/regen_doc_index.py" \
  "${PROJECT_ROOT}/scripts/regen_doc_index.py"; do
  if [[ -n "$candidate" && -f "$candidate" ]]; then
    SCRIPT_PATH="$candidate"
    break
  fi
done

if [[ -z "$SCRIPT_PATH" ]]; then
  cos_log_hook auto-regen-doc-index skip "reason=script_missing"
  exit 0
fi

# ── Debounce ─────────────────────────────────────────────────────────
# 5-second window per target dir. Suppresses regen storms when an agent
# saves multiple files in the same dir in quick succession.
_DEBOUNCE_TTL=5
_STATE_BASE="${COS_STATE_DIR:-${PROJECT_ROOT}/.coding-os}"
_SAFE_DIR=$(printf '%s' "$TARGET_DIR" | tr '/' '_' | tr ' ' '_')
_DEBOUNCE_FILE="${_STATE_BASE}/.regen-doc-index-debounce-${_SAFE_DIR}"
_NOW=$(date +%s)
if [[ -f "$_DEBOUNCE_FILE" ]]; then
  _LAST=$(cat "$_DEBOUNCE_FILE" 2>/dev/null || echo 0)
  if (( _NOW - _LAST < _DEBOUNCE_TTL )); then
    cos_log_hook auto-regen-doc-index skip "reason=debounced dir=${TARGET_DIR}"
    exit 0
  fi
fi
mkdir -p "$(dirname "$_DEBOUNCE_FILE")"
echo "$_NOW" > "$_DEBOUNCE_FILE"

ERR_LOG="${_STATE_BASE}/.regen-doc-index-errors.log"
mkdir -p "$(dirname "$ERR_LOG")"

# ── Fire-and-forget regen in background ──────────────────────────────
# Failures land in $ERR_LOG (bounded 200 lines). `cos hooks-log --follow`
# surfaces dispatched / skip lines; ERR_LOG is the place to look when the
# index stops refreshing. (Per-dir fail-counter removed — over-engineered
# vs. just tailing the log; TASK-162 audit walked it back.)
(
  "${COS_PYTHON:-python3}" "$SCRIPT_PATH" "$TARGET_DIR" >/dev/null 2>>"$ERR_LOG" &
) &

# Bound the error log to the last 200 lines so it can't balloon.
if [[ -f "$ERR_LOG" ]]; then
  LINES=$(wc -l < "$ERR_LOG" 2>/dev/null || echo 0)
  if (( LINES > 200 )); then
    tail -n 200 "$ERR_LOG" > "${ERR_LOG}.tmp" && mv "${ERR_LOG}.tmp" "$ERR_LOG"
  fi
fi

cos_log_hook auto-regen-doc-index dispatched "dir=${TARGET_DIR}"
exit 0
