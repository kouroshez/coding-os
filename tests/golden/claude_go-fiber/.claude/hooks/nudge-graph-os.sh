#!/usr/bin/env bash
# UserPromptSubmit hook — heuristic graph_os discovery nudge.
#
# Purpose: Surface the right cos_graph_* tool when the prompt asks a
# structural question (callers, blast radius, rename, contracts, trace,
# similarity). Closes the dogfood gap where the agent never reaches the
# graph layer because no other hook surfaces it.
#
# Debounced per session via marker file. Always exits 0.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty' 2>/dev/null || echo "")

LEN=${#PROMPT}
if [[ "$LEN" -lt 15 ]]; then
  exit 0
fi

# Per-pattern marker — different structural questions get different
# nudges. Same pattern asked twice in one session stays silent.
MARKER_DIR="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.graph-nudge"  # panel-first (TASK-107): cleared at panel scope each SessionStart
mkdir -p "$MARKER_DIR" 2>/dev/null || true

# Lowercase, whitespace-collapsed for matching.
PL=$(printf '%s' "$PROMPT" | tr '[:upper:]' '[:lower:]')

# Each pattern → recommended cos_graph_* tool. First match wins, so
# more-specific patterns come BEFORE more-generic siblings (e.g.
# detect_changes before impact, doctor before export).
# Persian + English bilingual to match this repo's user.
declare -a PATTERNS=(
  # graph health / why empty / why broken — must precede generic graph words
  "graph (empty|broken|stale|down|dead)|why .* graph|graph health|گراف خالی|گراف خراب|سلامت گراف:cos_graph_doctor"
  # detect changes / pre-commit / diff impact / what did i change — before impact
  "pre.?commit|what did i change|diff impact|since last commit|impact of (my )?change|recent change|recent commit|اثر تغییر|قبل از commit|اخیراً تغییر:cos_graph_detect_changes"
  # rename — rename_plan
  "rename|renaming|تغییر نام|rename plan:cos_graph_rename_plan"
  # who calls / references / used by — references
  "who calls|who uses|where (is|are) .* (called|used|referenced)|callers of|references to|used by|چه کسی .*صدا|کجا .*فراخوانی|کجا .*استفاده|^references|usages|call.?sites?:cos_graph_references"
  # blast radius / impact / what breaks — impact
  "blast radius|impact|what breaks|what will break|downstream|upstream|affected|چه چیزی .*شکست|چه چیزی .*خراب|تاثیر .*تغییر:cos_graph_impact"
  # contracts / api surface / endpoints / mcp tools
  "api surface|all endpoints|all routes|all mcp tools|all handlers|contract surface|سطح api|همه endpoint|همه route|همه ابزار:cos_graph_contracts"
  # trace / data flow / execution path — before path (trace pattern is more
  # explicit; "from X to Y" appears in both, so put trace first when the
  # word "trace" or "execution path" or "data flow" is present)
  "^trace |trace the |trace .* execution|execution path|data flow|how does .* flow|step.?by.?step from|پیمایش|جریان داده|مسیر اجرا:cos_graph_trace"
  # path between / shortest / how connected
  "shortest path|path from .* to|path between|how .* connected|how .* reach|مسیر کوتاه|چطور .*متصل|کوتاه‌ترین:cos_graph_path"
  # similar / duplicate / near-clone
  "similar|near.?duplicate|clone|equivalent|like .* but|مشابه|نزدیک|تکراری:cos_graph_similar"
  # subsystems / clusters / communities / map of
  "subsystem|cluster|community|map of|architecture map|onboard|زیرسیستم|کلاستر|نقشه|پرسنا:cos_graph_communities"
  # context / surrounding / depend on this
  "context around|surrounding|neighbour|neighbor|depend on this|دور و بر|پیرامون|surrounding context:cos_graph_context"
  # entry points / where does it start
  "entry point|where does .* start|main entry|how do users|نقطه شروع|ورودی برنامه:cos_graph_entrypoints"
  # diagram / mermaid / dot
  "diagram|mermaid|dot graph|visualize|نمودار|دیاگرام:cos_graph_export"
)

MATCHED_TOOL=""
for entry in "${PATTERNS[@]}"; do
  re="${entry%:*}"
  tool="${entry##*:}"
  if printf '%s' "$PL" | grep -qE "$re" 2>/dev/null; then
    MATCHED_TOOL="$tool"
    break
  fi
done

if [[ -z "$MATCHED_TOOL" ]]; then
  exit 0
fi

# Per-pattern debounce — silent only if THIS specific tool already
# nudged in this session. New structural pattern → new nudge.
PATTERN_MARKER="${MARKER_DIR}/${MATCHED_TOOL}"
if [[ -f "$PATTERN_MARKER" ]]; then
  exit 0
fi

cos_log_hook nudge-graph-os fire "tool=${MATCHED_TOOL} len=${LEN}"
touch "$PATTERN_MARKER" 2>/dev/null || true

CONTEXT="[graph_os nudge] Structural question detected — call ${MATCHED_TOOL} BEFORE Read/grep. The graph is the third retrieval layer; one envelope (~300 tok) replaces 5–10 file reads. See docs/engineering/graph-hallucination-cures.md."
printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":$(printf '%s' "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"

exit 0
