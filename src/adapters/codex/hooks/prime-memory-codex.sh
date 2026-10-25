#!/usr/bin/env bash
# UserPromptSubmit, Codex only: hand the agent the memory index
# (.agents/memory/MEMORY.md) once per session. Claude Code loads that index
# through the memory-dir symlink ensure-agent-memory-link keeps; Codex has no
# memory dir to link, so without this the index never reaches a Codex session.
# Advisory, fail-open, once per panel (a Codex panel is one session).
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null \
  || source "$(dirname "$0")/../../../core/hooks/cos-env.sh" 2>/dev/null || true
command -v cos_log_hook >/dev/null 2>&1 || cos_log_hook() { :; }

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")"
INDEX="$REPO_ROOT/.agents/memory/MEMORY.md"
[[ -r "$INDEX" ]] || exit 0

MARKER="${COS_PANEL_DIR:-${COS_AGENT_DIR:-${COS_STATE_DIR:-.coding-os}/codex}}/.memory-primed"
[[ -f "$MARKER" ]] && exit 0
mkdir -p "$(dirname "$MARKER")" 2>/dev/null || true
touch "$MARKER" 2>/dev/null || true

CONTEXT="$(
  printf 'Durable cross-session memory for this repo. Each index line names a file under .agents/memory/; open it when the line applies to the task.\n\n'
  cat "$INDEX"
)"
cos_log_hook prime-memory-codex ok "bytes=${#CONTEXT}" || true
printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":$(printf '%s' "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"
exit 0
