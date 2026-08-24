#!/usr/bin/env bash
# UserPromptSubmit hook — surface the humanizer skill on prose-writing intent.
#
# Purpose: The skill-enforcement table gates prose that lands in a FILE
# (README, docs/blog). It cannot see the case that actually costs
# credibility: prose drafted in the reply itself — a forum post, a launch
# announcement, a comment reply — which never touches Write/Edit and so
# passes every PreToolUse gate. This hook closes that leg by matching the
# intent in the prompt instead of the path in the tool call.
#
# Debounced per session per intent class. Always exits 0.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty' 2>/dev/null || echo "")

LEN=${#PROMPT}
if [[ "$LEN" -lt 12 ]]; then
  exit 0
fi

MARKER_DIR="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.humanizer-nudge"
mkdir -p "$MARKER_DIR" 2>/dev/null || true

PL=$(printf '%s' "$PROMPT" | tr '[:upper:]' '[:lower:]')

# Intent class → marker name. First match wins, so the narrower classes
# come before the generic authoring verbs. Each class covers English and
# the Persian phrasings this project is actually driven in, because a
# prompt written in Persian produces English prose all the same.
declare -a PATTERNS=(
  # someone already called the output machine-written — highest priority
  "reads? like (an? )?ai|sounds? like (an? )?ai|ai.generated|ai slop|too polished|humanize|هیومنایز|شبیه ai|مثل ربات:flagged"
  # community and social posts — the surface that burned us
  "reddit|hacker ?news|linkedin|twitter|forum post|subreddit|community post|announcement|launch post|پست|ردیت:community"
  # long-form published prose
  "blog|article|essay|newsletter|release notes|changelog entry|landing page|marketing copy|مقاله|بلاگ:longform"
  # repo-facing prose a stranger reads
  "readme|contributing|pr (body|description)|pull request (body|description)|issue reply|reply to (the )?(comment|reviewer):repo"
  # generic authoring verbs, last
  "(write|draft|compose|rewrite|edit) (me )?(a |an |the )?(post|text|copy|blurb|summary for|intro|pitch|bio):generic"
)

MATCHED=""
for entry in "${PATTERNS[@]}"; do
  re="${entry%:*}"
  cls="${entry##*:}"
  if printf '%s' "$PL" | grep -qE "$re" 2>/dev/null; then
    MATCHED="$cls"
    break
  fi
done

if [[ -z "$MATCHED" ]]; then
  exit 0
fi

MARKER="${MARKER_DIR}/${MATCHED}"
if [[ -f "$MARKER" ]]; then
  exit 0
fi

cos_log_hook nudge-humanizer fire "class=${MATCHED} len=${LEN}"
touch "$MARKER" 2>/dev/null || true

CONTEXT="[humanizer nudge] This turn produces prose a human reads outside the repo (class=${MATCHED}). Load 'Skill humanizer' BEFORE drafting, not after. Non-negotiable: keep every claim, invent no fact, and never manufacture personality to sound human. Run technical-writing first when the deliverable is a document. Community posts: flat title, no formula reused across posts, no performed humility, short."
printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":$(printf '%s' "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"

exit 0
