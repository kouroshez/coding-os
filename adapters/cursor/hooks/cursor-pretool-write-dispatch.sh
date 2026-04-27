#!/usr/bin/env bash
# Cursor preToolUse Write matcher: run Write|Edit enforcement chain (registry order).
set -euo pipefail

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$HOOK_DIR/cos-env.sh" 2>/dev/null || source "$HOOK_DIR/../../../core/hooks/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then
  cos_log_hook() { :; }
fi

INPUT=$(cat)
COS_HOOK_RUNTIME_MODEL="$(printf '%s' "$INPUT" | jq -r '.model // empty' 2>/dev/null || true)"
export COS_HOOK_RUNTIME_MODEL
cos_log_hook cursor-pretool-write-dispatch fire "tool=Write"

delegate_path() {
  local delegate="$1"
  if [[ -f "$HOOK_DIR/$delegate" ]]; then
    echo "$HOOK_DIR/$delegate"
  else
    echo "$HOOK_DIR/../../../core/hooks/$delegate"
  fi
}

run_delegate() {
  local delegate="$1" errf rc
  errf=$(mktemp "${TMPDIR:-/tmp}/cursor-pwrite-err.XXXXXX")
  set +e
  bash "$(delegate_path "$delegate")" <<<"$INPUT" >/dev/null 2>"$errf"
  rc=$?
  set -e

  if [[ "$rc" -eq 0 ]]; then
    rm -f "$errf"
    return 0
  fi
  if [[ "$rc" -eq 2 ]]; then
    cos_log_hook cursor-pretool-write-dispatch block "delegate=${delegate}"
    cat "$errf" >&2
    rm -f "$errf"
    exit 2
  fi
  cos_log_hook cursor-pretool-write-dispatch warn "delegate=${delegate} rc=${rc}"
  if [[ -s "$errf" ]]; then
    cat "$errf" >&2
  fi
  rm -f "$errf"
  return 0
}

# Two-phase dispatch (Wave 0 D1):
#   Phase A — stateless block-* checks run in parallel; if any blocks
#             (rc=2), bail before paying the serial-enforce cost.
#   Phase B — serial enforce-* + state-aware checks. These read/mutate
#             session markers and must remain sequential to keep the
#             ordering contract with thinking_os state files.
#
# Hooks that touch shared state (gate / task / anchor / memory / zoom /
# graph-context / rename-plan / wip / template-drift / anti-ambiguity)
# stay in Phase B. Pure stdin scanners go to Phase A.

run_phase_a_parallel() {
  local pids=() rc=0 errs=()
  local d errf
  for d in "$@"; do
    errf=$(mktemp "${TMPDIR:-/tmp}/cursor-pwrite-pa.XXXXXX")
    bash "$(delegate_path "$d")" <<<"$INPUT" >/dev/null 2>"$errf" &
    pids+=("$!:$d:$errf")
  done
  for entry in "${pids[@]}"; do
    local pid="${entry%%:*}"
    local rest="${entry#*:}"
    local d_name="${rest%%:*}"
    local errfile="${rest#*:}"
    if ! wait "$pid"; then
      local child_rc=$?
      if [[ "$child_rc" -eq 2 ]]; then
        cos_log_hook cursor-pretool-write-dispatch block "delegate=${d_name} phase=A"
        cat "$errfile" >&2
        rm -f "$errfile"
        # Drain remaining background pids before exiting so we don't leak.
        for other in "${pids[@]}"; do
          local other_pid="${other%%:*}"
          local other_rest="${other#*:}"
          local other_errfile="${other_rest#*:}"
          [[ "$other_pid" == "$pid" ]] && continue
          wait "$other_pid" 2>/dev/null || true
          rm -f "$other_errfile"
        done
        exit 2
      fi
      cos_log_hook cursor-pretool-write-dispatch warn "delegate=${d_name} phase=A rc=${child_rc}"
      [[ -s "$errfile" ]] && cat "$errfile" >&2
    fi
    rm -f "$errfile"
  done
  return 0
}

# Phase A — stateless / read-only blockers (no shared-state side effects).
run_phase_a_parallel \
  block-secrets.sh \
  block-bad-patterns.sh \
  block-protected-files.sh \
  block-migration-conflict.sh \
  block-hardcoded-literals.sh \
  validate-task-frontmatter.sh \
  warn-template-drift.sh

# Phase B — serial state-aware enforcement (order matters here).
for delegate in \
  enforce-template.sh \
  thinking_os-gate.sh \
  enforce-task-start.sh \
  enforce-doc-anchor.sh \
  enforce-memory-check.sh \
  enforce-skill.sh \
  enforce-zoom.sh \
  enforce-graph-context.sh \
  enforce-rename-plan.sh \
  enforce-wip-limit.sh \
  enforce-anti-ambiguity.sh; do
  run_delegate "$delegate"
done

exit 0
