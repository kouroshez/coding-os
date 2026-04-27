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

set -eu

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
cos_log_hook auto-reindex-shell-ops enter || true

INPUT="$(cat 2>/dev/null || true)"
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
if ! printf '%s' "$CMD" | grep -qE '\.(py|ts|tsx|md|sh|yaml|yml|go|rs|java|toml|json)\b|core/|cli/|adapters/|templates/|docs/|tests/'; then
  exit 0
fi

STATE_DIR="${COS_STATE_DIR:-${COS_AGENT_DIR:-.coding-os/claude}}"
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

# Detached background reindex — Bash tool returns immediately.
ERR_LOG="${STATE_DIR}/.reindex-shell-ops.log"
(
  (
    cos graph-reindex --force >>"$ERR_LOG" 2>&1
    rm -f "$SENTINEL" 2>/dev/null || true
  ) &
) &

cos_log_hook auto-reindex-shell-ops scheduled "cmd_head=$(printf '%.80s' "$CMD")" || true
exit 0
