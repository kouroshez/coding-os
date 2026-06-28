#!/usr/bin/env bash
# verify-rename-callers.sh — PostToolUse Edit
#
# PURPOSE
#   When an Edit performs an identifier rename (old_string/new_string are
#   both short identifiers and look like a rename), grep the rest of the
#   repo for the OLD name. If callers still reference it, emit a warning
#   so the agent updates them in the same task.
#
#   Closes the gap left by enforce-rename-plan (which verifies a *plan*
#   exists, not that all *call sites* were updated).
#
# ESCALATION (default warn, opt-in block)
#   On unreplaced callers it records a durable `.rename-incomplete` marker
#   (so the signal survives past this turn's stderr) and warns. Default stays
#   non-blocking — >0 callers is a signal the agent judges (docs referencing a
#   historical name, a BC shim). COS_VERIFY_RENAME_CALLERS=strict promotes the
#   warning to a hard block (exit 2) for projects that enforce completeness.
#
# DESIGN NOTES
#   - Skip when old_string is too short (<4 chars) or non-identifier-shaped
#     to avoid false positives.
#   - Skip files where the old name lives in code comments or docstrings
#     about migration history (heuristic: "renamed from", "was called").
#   - Cap output at 10 callers to keep the message readable.

set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook verify-rename-callers entry 2>/dev/null || true

PAYLOAD="$(cos_read_stdin_bounded 2)"
[[ -z "$PAYLOAD" ]] && exit 0

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
fp = ti.get("file_path", "")
print(f"{fp}|{old}|{new}")
' 2>/dev/null || true)"

FILE_PATH="${OLD_NEW%%|*}"
REST="${OLD_NEW#*|}"
OLD="${REST%%|*}"
NEW="${REST#*|}"

# Bail on missing or unsuitable inputs.
if [[ -z "$OLD" || -z "$NEW" || "$OLD" == "$NEW" ]]; then
  exit 0
fi
if [[ "${#OLD}" -lt 4 || "${#OLD}" -gt 60 ]]; then
  exit 0
fi
if ! [[ "$OLD" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  exit 0
fi
if ! [[ "$NEW" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  exit 0
fi

# Cheap reject: if old_string contains spaces or newlines it isn't an
# identifier rename — likely a content edit.
case "$OLD" in
  *" "*|*$'\n'*) exit 0 ;;
esac

# Find repo root (so git grep works regardless of cwd).
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -z "$REPO_ROOT" ]] && exit 0
cd "$REPO_ROOT" || exit 0

# Search for unreplaced references. Word-regex prevents `frob` matching
# `frobnicate`. Limit -l to file list, then -n on hits, capped at 10. The
# git grep is wrapped in a 5s perl alarm (macOS lacks timeout(1)) so a
# 100K-file working tree can never hang the edit — fail-open to no warning,
# since cos_graph_rename_plan is the authoritative caller-finder. TASK-229.
HITS="$(perl -e 'alarm shift; exec @ARGV' 5 git grep -l --word-regexp -- "$OLD" 2>/dev/null | grep -v "${FILE_PATH#$REPO_ROOT/}" | head -10 || true)"
[[ -z "$HITS" ]] && {
  cos_log_hook verify-rename-callers ok "all call sites updated" 2>/dev/null || true
  exit 0
}

COUNT=$(printf '%s\n' "$HITS" | grep -c .)
cos_log_hook verify-rename-callers warn "old=${OLD} unreplaced_files=${COUNT}" 2>/dev/null || true

# Escalation marker — durable record that a rename was left incomplete, so the
# signal outlives this turn's stderr (a Stop-phase reviewer / retro can act on
# it). Panel-scoped, appended; GC'd with the rest of panel state.
MARKER_DIR="${COS_PANEL_DIR:-${COS_AGENT_DIR:-.coding-os}}"
mkdir -p "$MARKER_DIR" 2>/dev/null || true
printf '%s\t%s\t%s\t%s\n' "$OLD" "$NEW" "$COUNT" "$FILE_PATH" >> "${MARKER_DIR}/.rename-incomplete" 2>/dev/null || true

cat >&2 <<MSG
🔁 Rename caller-check — \`${OLD}\` → \`${NEW}\`
   Edited: ${FILE_PATH}
   But \`${OLD}\` still appears in ${COUNT} other file(s):
$(printf '     - %s\n' $HITS)

   Either:
   • Update those call sites in the same task, OR
   • Confirm intentional retention (docs about history, BC shim).

   Verify with: cos verify --since HEAD --refs --no-tests
MSG

if [[ "${COS_VERIFY_RENAME_CALLERS:-warn}" == "strict" ]]; then
  cos_log_hook verify-rename-callers block "old=${OLD} unreplaced_files=${COUNT}" 2>/dev/null || true
  exit 2
fi
exit 0
