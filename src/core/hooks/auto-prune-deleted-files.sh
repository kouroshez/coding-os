#!/usr/bin/env bash
# PostToolUse Bash hook — counterpart to auto-reindex-docs.sh. When the
# agent runs `rm` / `git rm` / `mv` on a code or markdown file, prune
# graph_nodes (cascade to edges + evidence), document_chunks, and
# file_index_state so a deleted-then-recreated file doesn't survive as
# zombie graph rows. Closes the gap left by reindex-on-write.
#
# Design:
#   - Scoped: only fires when stdin command starts with `rm` / `git rm` /
#     `mv` / `git mv` and contains a code/doc extension.
#   - Fire-and-forget: forks the prune script in background, returns in
#     <50 ms. Worst-case freshness lag = one dispatch cycle.
#   - Fail-open: missing python / missing script = silent skip into
#     $COS_STATE_DIR/.prune-errors.log (bounded ~200 lines).
#   - No debounce: prune is idempotent and rare (no storms). If the
#     command fails, the agent re-runs and we re-prune harmlessly.
#   - Adapter-agnostic: reads COS_STATE_DIR / COS_PROJECT_ROOT from
#     cos-env.sh; never hardcodes `.claude/` (Rule 1).
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi


INPUT="$(cos_read_stdin_bounded 4)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
[[ "$TOOL" != "Bash" ]] && exit 0

# Only run on success (non-zero exit code → file likely still exists).
EXIT_CODE=$(echo "$INPUT" | jq -r '.tool_response.exit_code // .tool_response.exitCode // 0' 2>/dev/null || echo 0)
[[ "$EXIT_CODE" != "0" ]] && exit 0

CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")
[[ -z "$CMD" ]] && exit 0

# Match destructive verbs at word boundaries. Keep the pattern tight —
# we don't want `xrm-mode` or a comment containing "rm" to trigger.
# (`*rm *` already covers `*git rm *` since glob is greedy; same for mv.)
case "$CMD" in
  *rm\ *|*mv\ *) ;;
  *) exit 0 ;;
esac

# Extract candidate file paths via a minimal tokenizer. We rely on the
# Python helper for the heavy lifting; this script just routes raw
# arguments. The Python side runs `--force` only when the path is gone.
PROJECT_ROOT="${COS_PROJECT_ROOT:-$PWD}"
SCRIPT_PATH=""
for candidate in \
  "${PROJECT_ROOT}/src/scripts/prune_deleted_path.py" \
  "${PROJECT_ROOT}/scripts/prune_deleted_path.py" \
  "$(dirname "$0")/../../scripts/prune_deleted_path.py"; do
  if [[ -f "$candidate" ]]; then
    SCRIPT_PATH="$candidate"
    break
  fi
done

if [[ -z "$SCRIPT_PATH" ]]; then
  cos_log_hook auto-prune-deleted-files skip "reason=script_missing"
  exit 0
fi

# Naive path extraction: take all tokens that look like repo paths
# (start with `./`, `docs/`, `src/`, `core/`, `scripts/`, `cli/`, `adapters/`,
# `templates/`, `tests/`, or end in known code/doc extensions).
PATHS=()
# Word-splitting is intentional below — $CMD is a command line, not a
# single argument. shellcheck disable=SC2206
# shellcheck disable=SC2206
TOKENS=( $CMD )
for tok in "${TOKENS[@]}"; do
  case "$tok" in
    ./*|docs/*|src/*|core/*|scripts/*|cli/*|adapters/*|templates/*|tests/*) ;;
    *.py|*.ts|*.tsx|*.go|*.sh|*.md|*.yaml|*.yml) ;;
    *) continue ;;
  esac
  PATHS+=( "$tok" )
done

if [[ ${#PATHS[@]} -eq 0 ]]; then
  cos_log_hook auto-prune-deleted-files skip "reason=no_indexable_paths"
  exit 0
fi

cos_log_hook auto-prune-deleted-files fire "paths=${#PATHS[@]} cmd=${CMD:0:60}"

ERR_LOG="${COS_STATE_DIR:-${PROJECT_ROOT}/.coding-os}/.prune-errors.log"
mkdir -p "$(dirname "$ERR_LOG")"

(
  "${COS_PYTHON:-python3}" "$SCRIPT_PATH" "${PATHS[@]}" --quiet \
    >/dev/null 2>>"$ERR_LOG" &
) &

if [[ -f "$ERR_LOG" ]]; then
  LINES=$(wc -l < "$ERR_LOG" 2>/dev/null || echo 0)
  if (( LINES > 200 )); then
    tail -n 200 "$ERR_LOG" > "${ERR_LOG}.tmp" && mv "${ERR_LOG}.tmp" "$ERR_LOG"
  fi
fi

cos_log_hook auto-prune-deleted-files dispatched "paths=${#PATHS[@]}"

# Visible signal — record activity + emit systemMessage. count is int.
cos_record_activity graph "prune ${#PATHS[@]}" 2>/dev/null || true
printf '%s' "{\"systemMessage\":\"[graph] prune ${#PATHS[@]}\"}"

exit 0
