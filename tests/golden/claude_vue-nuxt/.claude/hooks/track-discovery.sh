#!/usr/bin/env bash
# Discovery Protocol auto-trigger (PostToolUse).
# Spec: docs/phase-n-role-based-routing-plan.md §2.7
#
# Scans agent Write/Edit output for discovery signal phrases. If any match,
# emits a non-blocking reminder asking the agent to call cos_discovery
# with impact assessment + decision (backtrack_now | record_for_later).
#
# formulas-en.md §Navigation Protocol §4 (Discovery Protocol) mandates:
#   Never ignore a new discovery. Ignoring = hidden gap.
# This hook surfaces discoveries automatically rather than relying on
# the agent to remember the rule.
#
# Signal phrases (regex, case-insensitive):
#   - "I notice" / "I noticed" / "I observed"
#   - "found a new" / "discovered that" / "turns out"
#   - "missing (actor|dependency|capability|constraint|edge case)"
#   - "undocumented" / "undefined" / "hidden"
#   - "not listed" / "not in the" / "not defined"
#
# This hook never blocks — it only reminds. Agent autonomy preserved.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook "track-discovery" "entry"

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")

# Only scan Write/Edit — these carry agent-authored prose in file_contents
# (for Write) or new_string (for Edit). Skip binary/content-free tools.
case "$TOOL" in
  Write|Edit|TodoWrite) ;;
  *) exit 0 ;;
esac

# Pull the body that might contain a discovery signal
BODY=""
case "$TOOL" in
  Write)
    BODY=$(echo "$INPUT" | jq -r '.tool_input.content // empty' 2>/dev/null || echo "")
    ;;
  Edit)
    BODY=$(echo "$INPUT" | jq -r '.tool_input.new_string // empty' 2>/dev/null || echo "")
    ;;
  TodoWrite)
    BODY=$(echo "$INPUT" | jq -r '.tool_input.todos // [] | tostring' 2>/dev/null || echo "")
    ;;
esac

if [[ -z "$BODY" ]]; then
  exit 0
fi

# Regex library — match ≥2 phrases before prompting (reduces false positives)
PATTERNS=(
  "I not(e|ice)d?"
  "I observed"
  "discovered that"
  "found a new"
  "turns out"
  "missing (actor|dependency|capability|constraint|edge case|scenario)"
  "undocumented"
  "undefined (capability|contract|endpoint|behavior)"
  "hidden (dependency|coupling|state)"
  "not (listed|defined|in the)"
  "unknown (actor|dependency|behavior)"
)

MATCHES=0
MATCHED_PHRASES=""
for pat in "${PATTERNS[@]}"; do
  if echo "$BODY" | grep -Eqi "$pat"; then
    MATCHES=$((MATCHES + 1))
    # Capture first 40 chars around the match for context
    SAMPLE=$(echo "$BODY" | grep -Eoi "$pat" | head -1)
    MATCHED_PHRASES="${MATCHED_PHRASES}[${SAMPLE}] "
    if [[ $MATCHES -ge 3 ]]; then
      break
    fi
  fi
done

# Threshold: need at least 2 distinct signal phrases to avoid FP noise
if [[ $MATCHES -lt 2 ]]; then
  exit 0
fi

# Check if agent already called cos_discovery recently (skip to avoid spam)
MARKER="${COS_PANEL_DIR:-${COS_AGENT_DIR:-.coding-os/claude}}/.last-discovery-reminder"  # panel-first: per-panel cooldown
NOW=$(date +%s)
if [[ -f "$MARKER" ]]; then
  LAST=$(cat "$MARKER" 2>/dev/null || echo "0")
  # Reminder cooldown: 5 minutes between reminders
  if (( NOW - LAST < 300 )); then
    exit 0
  fi
fi
echo "$NOW" > "$MARKER"

cos_log_hook "track-discovery" "reminder" "matches=$MATCHES phrases=$MATCHED_PHRASES"

cat >&2 <<EOF
[Discovery Protocol] Detected $MATCHES discovery signal phrase(s) in your output:
  ${MATCHED_PHRASES}

formulas-en.md §Navigation Protocol §4 mandates: record new discoveries
immediately. If you identified a new actor, state, dependency, constraint,
or risk during this formula's execution, call:

  cos_discovery(
    kind=<actor|state|dependency|constraint|risk>,
    summary="<one-line>",
    impact_assessment="<which prior formulas are affected>",
    decision=<"backtrack_now"|"record_for_later">
  )

Non-blocking — continuing. But if ignored, the discovery becomes a
hidden gap (Reviewer Layer 3 will flag it as an uncovered edge case).
EOF

exit 0
