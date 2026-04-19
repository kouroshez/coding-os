#!/usr/bin/env bash
# PostToolUse hook: warn if AGENTS.md approaches Codex's 32 KiB read cap.
#
# Codex CLI reads AGENTS.md up to project_doc_max_bytes (default 32768).
# When this file overflows, Codex silently truncates the tail — agents
# get a partial brain with no error. This hook surfaces the drift early.
#
# Non-blocking: warns only. AGENTS.md is often the biggest SSOT file and
# legitimately grows; the hook's job is to make the user aware, not to
# prevent legitimate growth.
set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[[ -z "$FILE_PATH" ]] && exit 0
case "$FILE_PATH" in
  */AGENTS.md|AGENTS.md) ;;
  *) exit 0 ;;
esac

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
cos_log_hook check-agents-md-size fire "path=${FILE_PATH}"

CODEX_CAP=32768
WARN_AT=28672   # ~28 KiB — gives ~4 KiB buffer before Codex truncates

if [[ ! -f "$FILE_PATH" ]]; then
  exit 0
fi

SIZE=$(wc -c < "$FILE_PATH" | tr -d ' ')

if [[ "$SIZE" -ge "$CODEX_CAP" ]]; then
  cos_log_hook check-agents-md-size error "size=${SIZE} >= ${CODEX_CAP}"
  echo "⚠️  AGENTS.md is ${SIZE} bytes — OVER Codex's ${CODEX_CAP} cap." >&2
  echo "   Codex will silently truncate. Move detail into core/rules/ or docs/," >&2
  echo "   keep only high-signal navigation + invariants here." >&2
  exit 0  # warn, never block — user may be mid-edit
fi

if [[ "$SIZE" -ge "$WARN_AT" ]]; then
  cos_log_hook check-agents-md-size warn "size=${SIZE} nearing cap ${CODEX_CAP}"
  echo "ℹ️  AGENTS.md is ${SIZE} bytes (~$((SIZE * 100 / CODEX_CAP))% of Codex's ${CODEX_CAP} cap)." >&2
fi

cos_log_hook check-agents-md-size ok "size=${SIZE}"
exit 0
