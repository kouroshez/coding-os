#!/usr/bin/env bash
# jit-recall.sh — PreToolUse Write|Edit just-in-time recall.
#
# Right before an edit, surface (1) a past friction lesson about THIS file and
# (2) any convention-rule one-liner mapped to the path in jit-rules.tsv, so the
# reminder lands at the moment it matters. Warn-only (exit 0, stderr), debounced
# per (file, session) / (rule, session). Fail-open: never blocks a tool call.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
[[ -z "$FILE_PATH" ]] && exit 0

# Debounce markers live in the .jit-nudge/ dir so session-context.sh prunes
# them wholesale each session (same convention as .graph-nudge/ .task-nudge/).
NUDGE_DIR="${COS_PANEL_DIR:-${COS_AGENT_DIR:-.coding-os}}/.jit-nudge"
[[ -d "$NUDGE_DIR" ]] || mkdir -p "$NUDGE_DIR" 2>/dev/null || true

# Resolve the PHYSICAL hooks dir — consumers symlink the .sh files but not
# sibling data/helpers, so $(dirname "$0") lands in a dir without them.
if command -v _cos_helpers_dir >/dev/null 2>&1; then
  HOOKS_PHYS_DIR="$(dirname "$(_cos_helpers_dir)")"
else
  HOOKS_PHYS_DIR="$(dirname "$0")"
fi

# Convention-rule reminders: glob<TAB>rule_id<TAB>message, once per (rule, session).
# Globs assume a leading slash; normalize relative paths (Codex apply_patch).
MATCH_PATH="$FILE_PATH"
[[ "$MATCH_PATH" != /* ]] && MATCH_PATH="/$MATCH_PATH"
RULES_MAP="$HOOKS_PHYS_DIR/jit-rules.tsv"
if [[ -f "$RULES_MAP" ]]; then
  while IFS=$'\t' read -r pattern rule_id message; do
    [[ -z "$pattern" || "$pattern" == \#* || -z "$rule_id" || -z "$message" ]] && continue
    # shellcheck disable=SC2053  # unquoted RHS is the point: pattern is a glob
    if [[ "$MATCH_PATH" == $pattern ]]; then
      RULE_MARKER="$NUDGE_DIR/rule-${rule_id}"
      [[ -f "$RULE_MARKER" ]] && continue
      : > "$RULE_MARKER" 2>/dev/null || true
      printf 'warning: 📏 [rule] %s\n' "$message" >&2
      cos_log_hook jit-recall rule-surfaced || true
    fi
  done < "$RULES_MAP"
fi

# Debounce once per (file, session) — only set the marker when we actually surface.
FILE_HASH=$(printf '%s' "$FILE_PATH" | shasum 2>/dev/null | cut -c1-12 || echo "nohash")
MARKER="$NUDGE_DIR/file-${FILE_HASH}"
[[ -f "$MARKER" ]] && exit 0

DB="${COS_DB_PATH:-${COS_STATE_DIR:-.coding-os}/coding-os.db}"
[[ -f "$DB" ]] || exit 0

LESSON="$(python3 "$HOOKS_PHYS_DIR/_helpers/jit_recall.py" "$DB" "$FILE_PATH" 2>/dev/null || true)"
if [[ -n "$LESSON" ]]; then
  : > "$MARKER" 2>/dev/null || true
  printf 'warning: 🧠 [recall] past lesson for this file — %s\n' "$LESSON" >&2
  cos_log_hook jit-recall warn || true
  exit 0
fi
cos_log_hook jit-recall ok || true
exit 0
