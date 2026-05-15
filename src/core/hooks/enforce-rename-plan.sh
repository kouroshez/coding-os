#!/usr/bin/env bash
# enforce-rename-plan.sh (Phase I.14)
# Warn when an agent attempts a multi-file rename operation without
# having consulted cos_graph_rename_plan earlier in the session.
# Heuristic: we flag Write/Edit to multiple files matching a rename
# pattern. Block mode (`COS_ENFORCE_RENAME_PLAN=strict`) rejects the
# tool call.

set -eu

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook enforce-rename-plan enter || true

MODE="${COS_ENFORCE_RENAME_PLAN:-1}"
if [[ "$MODE" == "0" ]]; then
  cos_log_hook enforce-rename-plan disabled || true
  exit 0
fi

PAYLOAD="$(cat 2>/dev/null || true)"
OLD_NEW="$(printf '%s' "$PAYLOAD" | python3 -c '
import sys, json
try:
    payload = json.loads(sys.stdin.read() or "{}")
except Exception:
    print("")
    raise SystemExit(0)
ti = payload.get("tool_input", {}) or {}
old = ti.get("old_string", "") or ti.get("find", "")
new = ti.get("new_string", "") or ti.get("replace", "")
print(f"{old}|{new}")
' 2>/dev/null || true)"

OLD="${OLD_NEW%%|*}"
NEW="${OLD_NEW#*|}"
# Very rough rename heuristic: both sides are short identifiers of
# different values but same shape.
if [[ -z "$OLD" || -z "$NEW" ]]; then
  cos_log_hook enforce-rename-plan no-strings || true
  exit 0
fi
if [[ "$OLD" == "$NEW" ]]; then
  cos_log_hook enforce-rename-plan unchanged || true
  exit 0
fi
if [[ "${#OLD}" -gt 80 || "${#NEW}" -gt 80 ]]; then
  cos_log_hook enforce-rename-plan non-rename || true
  exit 0
fi
if ! [[ "$OLD" =~ ^[A-Za-z_][A-Za-z0-9_.]*$ ]]; then
  cos_log_hook enforce-rename-plan non-rename || true
  exit 0
fi
if ! [[ "$NEW" =~ ^[A-Za-z_][A-Za-z0-9_.]*$ ]]; then
  cos_log_hook enforce-rename-plan non-rename || true
  exit 0
fi

MARKER="${COS_AGENT_DIR:-.coding-os/claude}/.rename-plan-$OLD"
if [[ -f "$MARKER" ]]; then
  cos_log_hook enforce-rename-plan ok || true
  exit 0
fi

MSG="rename-plan missing for identifier '$OLD' → '$NEW'.
  Call cos_graph_rename_plan first, then record:
    bash ${BASH_SOURCE[0]%/*}/write-state.sh \"${MARKER#$(pwd)/}\" \"reviewed\""
if [[ "$MODE" == "strict" ]]; then
  printf '%s\n' "$MSG" >&2
  cos_log_hook enforce-rename-plan block || true
  exit 2
fi
printf 'warning: %s\n' "$MSG" >&2
cos_log_hook enforce-rename-plan warn || true
exit 0
