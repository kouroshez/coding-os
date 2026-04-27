#!/usr/bin/env bash
# PostToolUse hook: flag dead references in AGENTS.md to core/rules or core/skills.
#
# AGENTS.md references paths like `core/rules/thinking_os.md` and
# `core/skills/clean-code/SKILL.md` so Codex (and any agent without a
# skill-system) can on-demand read the full content. If a file is
# renamed or deleted, the reference becomes dangling — the agent hits
# a dead read.
#
# This hook fires on edits to AGENTS.md OR to core/rules/** and
# core/skills/** (since renaming a referenced file also breaks things).
# Non-blocking: warns only. The fix is a one-liner edit either to the
# renamed file or to AGENTS.md.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
INPUT="$(cos_read_stdin_bounded 2)"
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
[[ -z "$FILE_PATH" ]] && exit 0

case "$FILE_PATH" in
  */AGENTS.md|AGENTS.md) ;;
  */core/rules/*.md) ;;
  */core/skills/*/SKILL.md) ;;
  *) exit 0 ;;
esac

cos_log_hook check-agents-md-refs fire "trigger=${FILE_PATH}"

# Locate AGENTS.md from the file path (may be editing from a subdir).
AGENTS_MD=""
DIR=$(dirname "$FILE_PATH")
while [[ "$DIR" != "/" && "$DIR" != "." ]]; do
  if [[ -f "${DIR}/AGENTS.md" ]]; then
    AGENTS_MD="${DIR}/AGENTS.md"
    break
  fi
  DIR=$(dirname "$DIR")
done
if [[ -z "$AGENTS_MD" && -f "AGENTS.md" ]]; then
  AGENTS_MD="AGENTS.md"
fi
[[ -z "$AGENTS_MD" ]] && exit 0

PROJECT_ROOT=$(dirname "$AGENTS_MD")

# Extract core/... references (with or without leading ./).
MISSING=()
while read -r REF; do
  [[ -z "$REF" ]] && continue
  # Normalize: strip backticks / quotes / markdown link syntax.
  CLEAN=$(echo "$REF" | sed -E 's/[][`()"]//g; s/^\.\///')
  # Handle markdown [text](path) — keep path portion only.
  CLEAN=$(echo "$CLEAN" | sed -E 's/^[A-Za-z][^]]*\]\(//; s/#L[0-9-]+$//')
  TARGET="${PROJECT_ROOT}/${CLEAN}"
  if [[ ! -e "$TARGET" ]]; then
    MISSING+=("$CLEAN")
  fi
done < <(grep -oE '(^|[^a-zA-Z0-9_/-])core/(rules|skills)/[A-Za-z0-9_./-]+' "$AGENTS_MD" \
         | sed -E 's/^[^c]*//' | sort -u)

if [[ ${#MISSING[@]} -gt 0 ]]; then
  cos_log_hook check-agents-md-refs warn "dead=${#MISSING[@]}"
  echo "⚠️  AGENTS.md references ${#MISSING[@]} path(s) that no longer exist:" >&2
  for M in "${MISSING[@]}"; do
    echo "    - $M" >&2
  done
  echo "   Fix: update AGENTS.md or restore/rename the referenced file." >&2
  exit 0
fi

cos_log_hook check-agents-md-refs ok ""
exit 0
