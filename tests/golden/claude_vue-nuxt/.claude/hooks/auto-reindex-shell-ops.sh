#!/usr/bin/env bash
# PostToolUse hook: catch bulk file operations the Write/Edit auto-
# reindex hook misses (mv/cp/rm/git checkout/git restore/git mv) and
# schedule a full reindex so the graph doesn't drift after a bulk
# rename or branch switch.
#
# Design:
#   - Fire-and-forget: detection is regex-only; the heavy reindex
#     runs in a detached background subshell so the Bash tool returns
#     immediately.
#   - Conservative: we only schedule when the command pattern strongly
#     suggests source-tree changes (touches *.py / *.ts / *.tsx / *.md
#     / *.sh / *.yaml or a known repo subtree). Pure cwd-only commands
#     never trigger.
#   - Debounced: a sentinel file `$COS_STATE_DIR/.reindex-scheduled`
#     is created with a 30s TTL; multiple ops in quick succession
#     coalesce into one reindex.
#   - Fail-open: missing tools / parse errors all silently skip.

set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cat 2>/dev/null || true)"

# Fast-path: this hook only schedules a reindex after a file-mutating shell
# verb (mv/cp/rm/git mv|checkout|restore|reset|stash/find -delete). If the raw
# payload mentions none of those tokens there is nothing to reindex — bail
# before any jq spawn (fires on EVERY Bash tool call). The precise verb+path
# regex below still gates the actual work.
case "$INPUT" in
  *mv*|*cp*|*rm*|*git*|*find*) ;;
  *) exit 0 ;;
esac

TOOL="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")"
if [[ "$TOOL" != "Bash" ]]; then
  exit 0
fi

CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")"
if [[ -z "$CMD" ]]; then
  exit 0
fi

# Pattern: any file-mutating shell verb followed by a path that looks
# like source. We don't try to be exhaustive — just enough to cover
# the common rename / cleanup / checkout flows.
if ! printf '%s' "$CMD" | grep -qE '(\bmv\b|\bcp\b|\brm\b|git[[:space:]]+(mv|checkout|restore|reset|stash)|find[[:space:]].*-delete)'; then
  exit 0
fi
if ! printf '%s' "$CMD" | grep -qE '\.(py|ts|tsx|md|sh|yaml|yml|go|rs|java|toml|json)\b|src/|core/|cli/|adapters/|templates/|docs/|tests/'; then
  exit 0
fi

# Deferred entry — only log when the hook is actually about to do work
# (matched file-mutation verb + source-tree-touching path). Avoids
# flooding the hook stream with `enter` rows for every Bash invocation.
cos_log_hook auto-reindex-shell-ops enter || true

# Agent-agnostic last-resort fallback (Rule 1/P2) — never hardcode an agent
# name. cos-env.sh normally exports both vars; .coding-os is the shared state
# root used only if it failed to source.
STATE_DIR="${COS_STATE_DIR:-${COS_AGENT_DIR:-.coding-os}}"
SENTINEL="${STATE_DIR}/.reindex-scheduled"
mkdir -p "$STATE_DIR" 2>/dev/null || true

# Debounce — skip if another op already scheduled within last 30s.
if [[ -f "$SENTINEL" ]]; then
  AGE=$(($(date +%s) - $(stat -f %m "$SENTINEL" 2>/dev/null || stat -c %Y "$SENTINEL" 2>/dev/null || echo 0)))
  if (( AGE < 30 )); then
    cos_log_hook auto-reindex-shell-ops debounced "age=${AGE}s" || true
    exit 0
  fi
fi

date +%s > "$SENTINEL" 2>/dev/null || true

ERR_LOG="${STATE_DIR}/.reindex-shell-ops.log"

# Bulk patterns force a full walk; everything else can dispatch the
# explicit paths it touched and skip the 17s repo walk.
BULK_RE='git[[:space:]]+(checkout|restore|reset|stash)([[:space:]]+\.|[[:space:]]+--[[:space:]]+\.|[[:space:]]*$)|find[[:space:]].*-delete|rm[[:space:]]+-rf'
EXPLICIT_PATHS="$(printf '%s' "$CMD" | grep -oE '[A-Za-z0-9_./-]+\.(py|ts|tsx|md|sh|yaml|yml|go|rs|java|toml|json)\b' | sort -u)"

if printf '%s' "$CMD" | grep -qE "$BULK_RE" || [[ -z "$EXPLICIT_PATHS" ]]; then
  (
    (
      cos graph-reindex --force >>"$ERR_LOG" 2>&1
      rm -f "$SENTINEL" 2>/dev/null || true
    ) &
  ) &
  cos_log_hook auto-reindex-shell-ops full "cmd_head=$(printf '%.80s' "$CMD")" || true
  cos_record_activity graph "full reindex" 2>/dev/null || true
  printf '%s' '{"systemMessage":"[graph] full reindex"}'
  exit 0
fi

(
  (
    while IFS= read -r path; do
      [[ -f "$path" ]] || continue
      "${COS_PYTHON:-python3}" -c "
import sys
sys.path.insert(0, 'src/core')
sys.path.insert(0, 'src/core/thinking_os')
from graph_os.tools.reindex_dispatch import dispatch
dispatch('${path}', project_root='$(pwd)', force=True)
" >>"$ERR_LOG" 2>&1
    done < <(printf '%s\n' "$EXPLICIT_PATHS")  # process-sub, not <<<: no bash heredoc deadlock on large path lists
    rm -f "$SENTINEL" 2>/dev/null || true
  ) &
) &

_N=$(printf '%s' "$EXPLICIT_PATHS" | grep -c . || true)
cos_log_hook auto-reindex-shell-ops paths "${_N} files" || true
cos_record_activity graph "reindex ${_N} files" 2>/dev/null || true
printf '%s' "{\"systemMessage\":\"[graph] reindex ${_N} files\"}"
exit 0
