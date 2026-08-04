#!/usr/bin/env bash
set -euo pipefail

export COS_AGENT=codex
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$HOOK_DIR/cos-env.sh" 2>/dev/null || source "$HOOK_DIR/../../../core/hooks/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cat 2>/dev/null || true)"
if command -v cos_panel_upgrade_from_payload >/dev/null 2>&1; then
  cos_panel_upgrade_from_payload "$INPUT" >/dev/null 2>&1 || true
fi

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/codex-preedit.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT
NORMALIZED="$WORK_DIR/normalized.jsonl"
if ! printf '%s' "$INPUT" | python3 "$HOOK_DIR/codex-normalize-edit.py" >"$NORMALIZED" 2>"$WORK_DIR/normalize.err"; then
  cat "$WORK_DIR/normalize.err" >&2
  cos_log_hook codex-preedit-dispatch block "reason=unparseable-patch"
  exit 2
fi

delegate_path() {
  local delegate="$1"
  if [[ -f "$HOOK_DIR/$delegate" ]]; then
    printf '%s\n' "$HOOK_DIR/$delegate"
  else
    printf '%s\n' "$HOOK_DIR/../../../core/hooks/$delegate"
  fi
}

OUTPUTS=()
RUN_INDEX=0
run_delegate() {
  local payload="$1" delegate="$2" output error rc
  RUN_INDEX=$((RUN_INDEX + 1))
  output="$WORK_DIR/$RUN_INDEX.out"
  error="$WORK_DIR/$RUN_INDEX.err"
  set +e
  bash "$(delegate_path "$delegate")" <<<"$payload" >"$output" 2>"$error"
  rc=$?
  set -e
  [[ -s "$output" ]] && OUTPUTS+=("$output")
  [[ -s "$error" ]] && cat "$error" >&2
  if [[ "$rc" -eq 2 ]]; then
    cos_log_hook codex-preedit-dispatch block "delegate=$delegate"
    exit 2
  fi
  if [[ "$rc" -ne 0 ]]; then
    cos_log_hook codex-preedit-dispatch warn "delegate=$delegate rc=$rc"
  fi
}

while IFS= read -r payload; do
  for delegate in \
    block-secrets.sh \
    block-bad-patterns.sh \
    block-protected-files.sh \
    block-shared-tree-edit.sh \
    enforce-task-transition.sh \
    block-migration-conflict.sh \
    block-hardcoded-literals.sh \
    validate-task-frontmatter.sh \
    enforce-wip-limit.sh \
    enforce-template.sh \
    thinking_os-gate.sh \
    enforce-scaffold-boundary.sh \
    enforce-task-start.sh \
    enforce-doc-anchor.sh \
    enforce-memory-check.sh \
    enforce-skill.sh \
    enforce-zoom.sh \
    enforce-graph-context.sh \
    warn-destructive-edit.sh \
    enforce-rename-plan.sh \
    enforce-task-body.sh \
    enforce-anti-ambiguity.sh \
    jit-recall.sh; do
    run_delegate "$payload" "$delegate"
  done
done <"$NORMALIZED"

python3 "$HOOK_DIR/codex-merge-hook-output.py" PreToolUse "${OUTPUTS[@]}"
