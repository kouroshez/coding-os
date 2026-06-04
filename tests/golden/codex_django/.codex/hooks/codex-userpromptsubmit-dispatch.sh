#!/usr/bin/env bash
# Codex UserPromptSubmit dispatcher — coalesces delegates so sequencing
# is deterministic (Codex fires matching hooks concurrently otherwise).
#
# Delegates (order matters):
#   1. session-context.sh         — same workflow banner Claude shows on prompts.
#   2. classify-task-mode.sh      — write $COS_AGENT_DIR/.task-mode (persona-aware
#                                   enforcement; docs/engineering/task-mode-matrix.md).
#   3. detect-exhaustive-intent.sh— write $COS_AGENT_DIR/.intent.json so the Stop
#                                   completion guardian enforces exhaustive intent
#                                   on Codex too (its side effect, not the nudge,
#                                   is what matters since stdout is discarded here).
#   4. nudge-thinking-os.sh       — heuristic Complexity Gate nudge.
#   5. nudge-graph-os.sh          — graph_os discovery nudge for structural Qs.
#   6. nudge-task-discovery.sh    — cos task-show over docs/tasks reads.
#   7. nudge-docs-first.sh        — docs-first SSOT discovery (declared in
#                                   adapter.yaml; was missing from this loop).
#   8. auto-compose-roles.sh      — compose role chain + learn-suggestions.
#   9. agent-presence.sh          — mark the session "active" for the live panel.
#
# Note: stdout is discarded (Codex UserPromptSubmit injection contract is not
# yet confirmed), so delegates contribute via their state-file side effects.
# Fail-open: any delegate failure is logged but does not block the prompt.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/cos-env.sh" 2>/dev/null || true

INPUT="$(cat 2>/dev/null || true)"

delegate_path() {
  local name="$1"
  if [[ -x "${SCRIPT_DIR}/${name}" ]]; then
    echo "${SCRIPT_DIR}/${name}"
  else
    # Fall back to the core hook — always available via symlink/install.
    echo "${SCRIPT_DIR}/${name}"
  fi
}

run_delegate() {
  local name="$1"
  local path
  path="$(delegate_path "$name")"
  if [[ ! -x "$path" ]]; then
    return 0
  fi
  if ! printf '%s' "$INPUT" | bash "$path" >/dev/null 2>&1; then
    cos_log_hook codex-userpromptsubmit-dispatch warn "delegate=${name} failed"
  fi
  return 0
}

for delegate in \
  session-context.sh \
  classify-task-mode.sh \
  detect-exhaustive-intent.sh \
  nudge-thinking-os.sh \
  nudge-graph-os.sh \
  nudge-task-discovery.sh \
  nudge-docs-first.sh \
  auto-compose-roles.sh \
  agent-presence.sh; do
  run_delegate "$delegate"
done

exit 0
