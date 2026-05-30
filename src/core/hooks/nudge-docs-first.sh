#!/usr/bin/env bash
# UserPromptSubmit hook — Docs-first nudge.
#
# Purpose: When the user's prompt looks like a code-edit intent (refactor,
# rename, fix bug, add feature, change function, etc.) AND the session has
# no .doc-anchor populated yet, surface a one-line additional-context block
# telling the agent: docs are SSOT, locate the doc first via
# cos_doc_search / cos_doc_header before touching code.
#
# Closes the gap where enforce-doc-anchor.sh fires only on Write/Edit but
# the user-prompt phase already signals intent — agents that get the nudge
# at prompt time avoid the BLOCK at edit time.
#
# Debounced per session via marker file. Always exits 0.
# Bilingual: matches both English + Persian intent patterns.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty' 2>/dev/null || echo "")

LEN=${#PROMPT}
if [[ "$LEN" -lt 15 ]]; then
  exit 0
fi

# Session-scoped debounce — one nudge per session is enough.
MARKER="${COS_AGENT_DIR}/.docs-first-nudged"
if [[ -f "$MARKER" ]]; then
  exit 0
fi

# If the doc-anchor already exists for this session, the agent has already
# done the right thing — skip silently.
ANCHOR="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.doc-anchor"  # panel-first (TASK-035): write-state routes .doc-anchor to the panel dir
if [[ -f "$ANCHOR" ]] && [[ -s "$ANCHOR" ]]; then
  exit 0
fi

# Skip if task-mode marker says this is a query / chore / adhoc — those
# bypass the doc-anchor requirement anyway.
MODE_FILE="${COS_AGENT_DIR}/.task-mode"
if [[ -f "$MODE_FILE" ]]; then
  MODE=$(cat "$MODE_FILE" 2>/dev/null | head -1 | tr -d '[:space:]')
  case "$MODE" in
    query|chore|adhoc) exit 0 ;;
  esac
fi

# Lowercase prompt for matching.
PL=$(printf '%s' "$PROMPT" | tr '[:upper:]' '[:lower:]')

# Code-edit intent patterns — bilingual EN + Persian. Conservative: only
# fire on unambiguous mutation verbs paired with code targets. Asking a
# question or reading code does NOT trigger.
CODE_INTENT_RE='(\b(refactor|rename|implement|add|fix|change|modify|update|extend|patch|migrate|replace|remove|delete|introduce|wire|integrate)\b.*\b(function|method|class|module|endpoint|route|handler|component|hook|tool|test|adapter|skill|api|schema|migration|config)\b)|(\.(py|ts|tsx|go|js|jsx|rs|sh)\b)|(تغییر|اصلاح|بازنویسی|اضافه|رفع|پیاده|ریفکتور)'

if ! printf '%s' "$PL" | grep -qE "$CODE_INTENT_RE" 2>/dev/null; then
  exit 0
fi

cos_log_hook nudge-docs-first fire "len=${LEN}"
touch "$MARKER" 2>/dev/null || true

CONTEXT="[docs-first] Code-edit intent detected — docs are SSOT (Rule 0 + 19). BEFORE touching code: (1) cos_doc_search \"<topic>\" or cos_doc_header(path) to locate the spec, (2) read it, (3) cos task-start TASK=N (populates .doc-anchor from Read First) OR set the anchor by hand. Procedure: docs/governance/docs-first-protocol.md."

printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":$(printf '%s' "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"

exit 0
