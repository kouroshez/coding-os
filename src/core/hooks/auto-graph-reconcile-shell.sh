#!/usr/bin/env bash
# auto-graph-reconcile-shell.sh
# PostToolUse Bash — single ordered reconciler that replaces the pair
# auto-reindex-shell-ops.sh + auto-prune-deleted-files.sh. Both used to
# fire on the same rm/mv and hit the graph DB in two unordered background
# jobs (the N10 race). This walks the touched paths ONCE and, in one job,
# prunes the gone paths FIRST then reindexes the present ones — serialized,
# never interleaved.
#
# Fire-and-forget, debounced, fail-open: detection is regex-only and all
# heavy work runs detached so the Bash tool returns immediately.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

# Every suffix the graph routes (tools/_reindex_routing.py::_EXT_MAP) plus docs;
# test_reindex_hook_suffixes.py keeps it from falling behind again.
ROUTED_SUFFIXES='py|ts|tsx|mts|cts|js|jsx|mjs|cjs|astro|sh|bash|zsh|yaml|yml|go|mod|php|json|toml|rs|rb|java|c|h|cc|cpp|cxx|hpp|hh|cs|scala|kt|kts|lua|md|mdx'

INPUT="$(cos_read_stdin_bounded 4)"

# Fast-path: only file-mutating verbs matter — bail before any jq spawn.
case "$INPUT" in
  *mv*|*cp*|*rm*|*git*|*find*) ;;
  *) exit 0 ;;
esac

TOOL="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")"
[[ "$TOOL" != "Bash" ]] && exit 0

# Only reconcile on success — a failed rm/mv left the tree unchanged.
EXIT_CODE="$(printf '%s' "$INPUT" | jq -r '.tool_response.exit_code // .tool_response.exitCode // 0' 2>/dev/null || echo 0)"
[[ "$EXIT_CODE" != "0" ]] && exit 0

CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")"
[[ -z "$CMD" ]] && exit 0

# Gate: a file-mutating verb AND a source-touching path.
if ! printf '%s' "$CMD" | grep -qE '(\bmv\b|\bcp\b|\brm\b|git[[:space:]]+(mv|rm|checkout|restore|reset|stash)|find[[:space:]].*-delete)'; then
  exit 0
fi
if ! printf '%s' "$CMD" | grep -qE "\.(${ROUTED_SUFFIXES})\b|src/|core/|cli/|adapters/|templates/|docs/|tests/"; then
  exit 0
fi

# A command that cd's away from the project, or names only absolute paths
# outside it, changed nothing the graph indexes (a scratch clone, /tmp).
PROJECT_ROOT="${COS_PROJECT_ROOT:-$PWD}"
CD_TARGET="$(printf '%s' "$CMD" | grep -oE '(^|[;&|][[:space:]]*)cd[[:space:]]+[^;&|[:space:]]+' | head -1 | sed -E 's/.*cd[[:space:]]+//' | tr -d "\"'" || true)"
if [[ -n "$CD_TARGET" && "$CD_TARGET" != "$PROJECT_ROOT" && "$CD_TARGET" != "$PROJECT_ROOT"/* ]]; then
  exit 0
fi
ABS_PATHS="$(printf '%s' "$CMD" | grep -oE '(^|[[:space:]"=])/[A-Za-z0-9_.~/-]+' | sed -E 's/^[[:space:]"=]//' || true)"
if [[ -n "$ABS_PATHS" ]] && ! printf '%s\n' "$ABS_PATHS" | grep -qF "$PROJECT_ROOT"; then
  exit 0
fi

cos_log_hook auto-graph-reconcile-shell enter || true
STATE_DIR="${COS_STATE_DIR:-${COS_AGENT_DIR:-.coding-os}}"
mkdir -p "$STATE_DIR" 2>/dev/null || true
ERR_LOG="${STATE_DIR}/.graph-reconcile.log"

EXPLICIT_PATHS="$(printf '%s' "$CMD" | grep -oE "[A-Za-z0-9_./-]+\.(${ROUTED_SUFFIXES})\b" | sort -u || true)"
BULK_RE='git[[:space:]]+(checkout|restore|reset|stash)([[:space:]]+\.|[[:space:]]+--[[:space:]]+\.|[[:space:]]*$)|find[[:space:]].*-delete|rm[[:space:]]+-rf'

# Bulk op (branch switch / wholesale delete) or no extractable path →
# one debounced full reindex; the full walk both prunes and re-adds.
if printf '%s' "$CMD" | grep -qE "$BULK_RE" || [[ -z "$EXPLICIT_PATHS" ]]; then
  # Single flight: the sentinel holds the running reindex's PID. A full
  # reindex runs for minutes, so an age-only debounce let every later command
  # start another one. The 30 s age check covers the moment before the PID lands.
  SENTINEL="${STATE_DIR}/.reindex-scheduled"
  if [[ -f "$SENTINEL" ]]; then
    RUNNING_PID="$(cat "$SENTINEL" 2>/dev/null || true)"
    AGE=$(($(date +%s) - $(stat -c %Y "$SENTINEL" 2>/dev/null || stat -f %m "$SENTINEL" 2>/dev/null || echo 0)))
    if (( AGE < 30 )) || { [[ "$RUNNING_PID" =~ ^[0-9]+$ ]] && kill -0 "$RUNNING_PID" 2>/dev/null; }; then
      cos_log_hook auto-graph-reconcile-shell debounced "age=${AGE}s pid=${RUNNING_PID}" || true
      exit 0
    fi
  fi
  : > "$SENTINEL" 2>/dev/null || true
  (
    (
      cos graph-reindex --force >>"$ERR_LOG" 2>&1
      rm -f "$SENTINEL" 2>/dev/null || true
    ) &
    printf '%s' "$!" > "$SENTINEL" 2>/dev/null || true
  ) &
  cos_log_hook auto-graph-reconcile-shell full "cmd_head=$(printf '%.80s' "$CMD")" || true
  cos_record_activity graph "full reindex" 2>/dev/null || true
  printf '%s' '{"systemMessage":"[graph] full reindex"}'
  exit 0
fi

# A consumer's hooks dir holds one symlink per hook; the shared body sits next
# to the real file, which _cos_helpers_dir walks the symlink back to.
_HOOKS_REAL="$(dirname "$(_cos_helpers_dir 2>/dev/null)")"
[[ -f "${_HOOKS_REAL}/_reindex_on_edit.sh" ]] || _HOOKS_REAL="$(dirname "$0")"
# shellcheck source=/dev/null
if ! source "${_HOOKS_REAL}/_reindex_on_edit.sh" 2>/dev/null; then
  cos_log_hook auto-graph-reconcile-shell skip "reason=reindex_body_missing" || true
  exit 0
fi

# Targeted: ONE ordered background job — the gone paths FIRST, then the
# present ones — so the graph DB never sees a prune and a reindex of the same
# file interleaved (the N10 race the two old hooks created by firing in
# parallel). A gone path runs through dispatch like any other: it prunes the
# file, re-reads the files that depended on it and relinks.
GONE=()
PRESENT=()
while IFS= read -r path; do
  [[ -n "$path" ]] || continue
  if [[ -f "$path" ]]; then
    PRESENT+=( "$path" )
  else
    GONE+=( "$path" )
  fi
done < <(printf '%s\n' "$EXPLICIT_PATHS")
cos_reindex_paths auto-graph-reconcile-shell ${GONE[@]+"${GONE[@]}"} ${PRESENT[@]+"${PRESENT[@]}"}

_N=$(printf '%s' "$EXPLICIT_PATHS" | grep -c . || true)
cos_log_hook auto-graph-reconcile-shell reconcile "${_N} paths" || true
cos_record_activity graph "reconcile ${_N} paths" 2>/dev/null || true
printf '%s' "{\"systemMessage\":\"[graph] reconcile ${_N} paths\"}"
exit 0
