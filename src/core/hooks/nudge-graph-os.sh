#!/usr/bin/env bash
# UserPromptSubmit hook — heuristic graph_os discovery nudge.
#
# Purpose: Surface the right cos_graph_* tool when the prompt asks a
# structural question (callers, blast radius, rename, contracts, trace,
# similarity, cycles, dead-code, test-gaps, centrality, ranking) OR a
# conceptual "how does X work / explain / what is" question. Closes the
# dogfood gap where the agent never reaches the graph layer because no
# other hook surfaces it — the conceptual case is the one that used to
# fall through to silence and let the agent default to memory.
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
MARKER_DIR="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.graph-nudge"  # panel-first: cleared at panel scope each SessionStart
mkdir -p "$MARKER_DIR" 2>/dev/null || true

# Lowercase, whitespace-collapsed for matching.
PL=$(printf '%s' "$PROMPT" | tr '[:upper:]' '[:lower:]')

# Each pattern → recommended cos_graph_* tool. First match wins, so
# more-specific patterns come BEFORE more-generic siblings (e.g.
# detect_changes before impact, doctor before export).
# English structural-question patterns (English-default pre-classifier).
declare -a PATTERNS=(
  # graph health / why empty / why broken — must precede generic graph words
  "graph (is |seems |looks |went )?(empty|broken|stale|down|dead)|why .* graph|graph health:cos_graph_doctor"
  # detect changes / pre-commit / diff impact / what did i change — before impact
  "pre.?commit|what did i change|diff impact|since last commit|impact of (my )?change|recent change|recent commit:cos_graph_detect_changes"
  # diff of a git range / PR review — before impact, after detect_changes
  "diff between|compare .* (commit|branch|ref|sha)|pr review|review (the )?(pr|diff|range)|blast radius of (the )?(pr|diff):cos_graph_diff"
  # rename — rename_plan
  "rename|renaming|rename plan:cos_graph_rename_plan"
  # symbol DEFINITION lookup ("defined", not "called") — before references
  "where (is|are) .* defined|defined where|find (the )?(symbol|function|class|method)|symbol named|function named|class named:cos_graph_query"
  # who calls / references / used by — references
  "who calls|who uses|where (is|are) .* (called|used|referenced)|callers of|references to|used by|^references|usages|call.?sites?:cos_graph_references"
  # blast radius / impact / what breaks — impact
  "blast radius|impact|what breaks|what will break|downstream|upstream|affected:cos_graph_impact"
  # circular dependencies / cycles / SCC
  "circular (dependency|dependencies|import|imports)|dependency cycle|cyclic|import cycle|\\bscc\\b:cos_graph_cycles"
  # dead / unused / unreferenced code
  "dead code|unused (code|function|symbol)|unreferenced|never (called|used)|can i (delete|remove)|safe to (delete|remove):cos_graph_dead_code"
  # test coverage gaps / untested
  "test gap|test coverage|untested|missing tests|coverage gap|not tested|lacks tests:cos_graph_test_gap"
  # most-connected / hub / chokepoint — centrality
  "most connected|chokepoint|bottleneck node|hub node|central node|centrality:cos_graph_centrality"
  # importance ranking / pagerank
  "most important|importance ranking|pagerank|rank .* by importance|key files:cos_graph_ranking"
  # contracts / api surface / endpoints / mcp tools
  "api surface|all endpoints|all routes|all mcp tools|all handlers|contract surface:cos_graph_contracts"
  # trace / data flow / execution path — before path (trace pattern is more
  # explicit; "from X to Y" appears in both, so put trace first when the
  # word "trace" or "execution path" or "data flow" is present)
  "^trace |trace the |trace .* execution|execution path|data flow|how does .* flow|step.?by.?step from:cos_graph_trace"
  # path between / shortest / how connected
  "shortest path|path from .* to|path between|how .* connected|how .* reach:cos_graph_path"
  # similar / duplicate / near-clone
  "similar|near.?duplicate|clone|equivalent|like .* but:cos_graph_similar"
  # subsystems / clusters / communities / map of
  "subsystem|cluster|community|map of|architecture map|onboard:cos_graph_communities"
  # context / surrounding / depend on this
  "context around|surrounding|neighbour|neighbor|depend on this|surrounding context:cos_graph_context"
  # entry points / where does it start
  "entry point|where does .* start|main entry|how do users:cos_graph_entrypoints"
  # resolve a label / path / partial id to a canonical uid
  "canonical uid|resolve .* to .* uid|which uid|partial uid:cos_graph_resolve"
  # diagram / mermaid / dot
  "diagram|mermaid|dot graph|visualize:cos_graph_export"
  # CONCEPTUAL "how does X work / explain / what is / overview" — GENERIC,
  # placed LAST so every specific structural pattern wins first. This is the
  # case that used to fall through to silence (and the agent defaulted to
  # memory). Route it to free-text code search; codebase-explorer is the
  # paired skill for end-to-end conceptual reading.
  "how (does|do|is|are) .*(work|works|implemented|structured|organi[sz]ed)|^explain |^what is |overview of|walk me through|understand (how|the):cos_graph_search"
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

CONTEXT="[graph_os nudge] Structural/conceptual code question detected — call ${MATCHED_TOOL} BEFORE Read/grep (for end-to-end conceptual reading, the codebase-explorer skill pairs with it). The graph is the code retrieval layer; one envelope (~300 tok) replaces 5–10 file reads. See docs/engineering/graph-hallucination-cures.md."
printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":$(printf '%s' "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"

exit 0
