#!/usr/bin/env bash
# Coding OS — the UserPromptSubmit pulse and the operator-visible transparency
# banner. Sourced by session-context.sh from its own resolved directory (the
# _cos_env_*.sh pattern); never run directly, never registered in registry.yaml.
#
# Split from session-context.sh because the two halves change for different
# reasons and answer to different contracts: SessionStart recovery/enrichment is
# governed by state-files.md §S5, while everything here is governed by
# src/core/rules/transparency-banner.md. Editing the banner should not put
# session-id seeding or the agent digest in the same review.
#
# Runs in the CALLER's shell, so it reads the environment session-context.sh has
# already established ($COS_PANEL_DIR, $_COS_HOOKS_PHYS, $INPUT).

cos_emit_session_pulse() {
  # State files written by write-state.sh have format "<session-id> <value>".
  # Verify session ownership before returning the value. Resolution order:
  #   1. panel-private $COS_SESSION_FILE (per-panel SSOT)
  #   2. agent-level legacy $COS_AGENT_DIR/session-id (transition compat —
  #      old write-state.sh / non-panel-aware writers land here)
  # Without the fallback, a panel that never ran SessionStart:startup
  # (resumed conversation, no panel session-id file) shows ses=? · all-
  # state-rejected. Mirrors cos_current_session() in cos-env.sh.
  _CURRENT_SESSION=""
  if [ -n "${COS_SESSION_FILE:-}" ] && [ -f "$COS_SESSION_FILE" ]; then
    _CURRENT_SESSION=$(head -1 "$COS_SESSION_FILE" 2>/dev/null | tr -d '\n\r')
  fi
  # Synthesise from panel-id when no session-id file exists yet (resumed
  # panel that never fired SessionStart:startup, or fresh panel where the
  # startup hook hasn't run). Without this, banner collapses to ses=?.
  # NEVER fall back to $COS_AGENT_DIR/session-id — that file is a fossil
  # belonging to a different panel and trusting it leaks state across
  # panels (cos-env.sh + check-state.sh now reject
  # the legacy file by the same rule).
  if [ -z "$_CURRENT_SESSION" ] && [ -n "${COS_PANEL_ID:-}" ]; then
    _CURRENT_SESSION="$COS_PANEL_ID"
  fi
  # Idempotently seed the panel session-id file when missing, so subsequent
  # hooks read a stable ownership token instead of recomputing the fallback.
  if [ -n "${COS_SESSION_FILE:-}" ] && [ ! -f "$COS_SESSION_FILE" ] && [ -n "$_CURRENT_SESSION" ]; then
    mkdir -p "$(dirname "$COS_SESSION_FILE")" 2>/dev/null || true
    printf '%s' "$_CURRENT_SESSION" > "$COS_SESSION_FILE" 2>/dev/null || true
  fi
  _read_state() {
    local file_input="$1" cap="$2"
    # STRICTLY panel-scoped for files in $COS_PER_PANEL_FILES — never
    # fall back to $COS_AGENT_DIR (cross-panel leak protection).
    local file=""
    local base
    base="$(basename "$file_input")"
    case " ${COS_PER_PANEL_FILES:-} " in
      *" $base "*)
        if [ -f "${COS_PANEL_DIR}/${base}" ]; then
          file="${COS_PANEL_DIR}/${base}"
        fi
        ;;
      *)
        file="$file_input"
        ;;
    esac
    [ -n "$file" ] && [ -f "$file" ] || { echo ""; return; }
    # If we can't determine the current session-id, NEVER trust any state
    # file (could be a fossil from a different session). Fail-empty.
    if [ -z "$_CURRENT_SESSION" ]; then
      echo ""; return
    fi
    local line file_session value
    line=$(head -1 "$file" 2>/dev/null) || { echo ""; return; }
    file_session=$(echo "$line" | awk '{print $1}')
    # Must match THIS panel's session-id exactly OR the agent-level
    # legacy id (transition window: pre-panel writers stamp with agent
    # session-id; panel-aware writers stamp with panel session-id; the
    # banner accepts both as owned by this panel until all writers have
    # been upgraded).
    if [ -z "$file_session" ]; then
      echo ""; return
    fi
    if [ "$file_session" != "$_CURRENT_SESSION" ]; then
      echo ""; return
    fi
    # Truncate by char count (-c is char-aware in GNU and BSD cut),
    # falling back to head -c for byte limit. Prefer cut so multi-byte
    # utf-8 (e.g. Persian skill names) doesn't get sliced mid-codepoint.
    value=$(echo "$line" | cut -d' ' -f2- | tr -d '\n\r')
    if command -v cut >/dev/null 2>&1; then
      value=$(printf '%s' "$value" | cut -c1-"$cap" 2>/dev/null || printf '%s' "$value" | head -c "$cap")
    else
      value=$(printf '%s' "$value" | head -c "$cap")
    fi
    echo "$value"
  }
  TASK_CUR=$(_read_state ".task-current" 32)
  GATE_STATE=$(_read_state ".thinking_os-gate" 24)
  SKILL_CUR=$(_read_state ".active-skill" 48)

  # The gate carries a 120-min TTL (check-state.sh). _read_state only checks
  # session-ownership, not age — so a long session would show an EXPIRED gate
  # as valid, then the next Write/Edit BLOCKs on "gate stale". Flag staleness
  # here so the banner tells the truth. Override: COS_GATE_TTL_SECONDS.
  if [ -n "$GATE_STATE" ] && [ -f "${COS_PANEL_DIR}/.thinking_os-gate" ]; then
    _GATE_MTIME=$(stat -c %Y "${COS_PANEL_DIR}/.thinking_os-gate" 2>/dev/null || stat -f %m "${COS_PANEL_DIR}/.thinking_os-gate" 2>/dev/null || echo 0)
    _GATE_AGE=$(( $(date +%s) - _GATE_MTIME ))
    if [ "$_GATE_AGE" -gt "${COS_GATE_TTL_SECONDS:-7200}" ]; then
      GATE_STATE="${GATE_STATE} ⌛stale"
    fi
  fi

  # Composed role chain — surface the ACTIVE role + its position in the chain
  # so the banner tracks what the agent is DOING, not a frozen lead.
  # advance-role.sh moves .role along .roles by work phase. STRICTLY panel-scoped,
  # with no agent-level fallback: the fallback made a panel that had composed
  # nothing render whichever chain another tab last wrote (a six-day-old
  # `roles=debugger 1/3` in a fresh panel). A neighbour's chain is a false
  # statement the operator cannot detect; '-' is a true one.
  # Format: "<active> N/M" e.g. "implementer 3/4".
  ROLES_LEAD=""
  _ROLES_FILE="${COS_PANEL_DIR}/.roles"
  _ROLE_FILE="${COS_PANEL_DIR}/.role"
  if [ -f "$_ROLES_FILE" ]; then
    ROLES_LEAD=$(python3 -c '
import json, sys
try:
    chain = json.load(open(sys.argv[1]))
    if not isinstance(chain, list) or not chain:
        sys.exit(0)
    active = ""
    try:
        active = open(sys.argv[2]).read().strip()
    except OSError:
        pass
    if active not in chain:
        active = str(chain[0])
    pos = chain.index(active) + 1
    print(f"{active} {pos}/{len(chain)}")
except Exception:
    pass
' "$_ROLES_FILE" "$_ROLE_FILE" 2>/dev/null | head -c 32 || true)
  fi

  # Supervision route — which adapter/model the active role would dispatch to,
  # resolved by resolve-supervise-route.sh (a cognition hook, so it runs before
  # this observability one). Absent file = supervision off or unrouted, and the
  # field is then omitted entirely: zero characters for a feature nobody enabled.
  # `?` suffix marks `suggest` mode, where the route is a proposal, not a plan.
  SUP_ROUTE=""
  _SUP_FILE="${COS_PANEL_DIR}/.supervise-route"
  if [ -f "$_SUP_FILE" ]; then
    SUP_ROUTE=$(python3 -c '
import json, sys
try:
    route = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
adapter = str(route.get("adapter") or "").strip()
if not adapter:
    sys.exit(0)
parts = [adapter]
for key in ("model", "effort"):
    value = str(route.get(key) or "").strip()
    if value:
        parts.append(value)
suffix = "?" if str(route.get("mode") or "") == "suggest" else ""
print("/".join(parts) + suffix)
' "$_SUP_FILE" 2>/dev/null | head -c 48 || true)
  fi

  # Task mode (classify-task-mode.sh writes this on every UserPromptSubmit
  # via a separate hook). NOT session-prefixed — it's a single token per
  # the writer's contract. Values: formal | query | adhoc | chore |
  # system | gov-required | propose-formal. Drives banner verbosity:
  # casual modes get a minimal banner, formal modes get the full one.
  TASK_MODE=""
  # panel-first: .task-mode is per-panel; agent-dir is the
  # back-compat fallback for a panel that hasn't re-written it yet.
  _TASK_MODE_FILE="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.task-mode"
  [ -f "$_TASK_MODE_FILE" ] || _TASK_MODE_FILE="${COS_AGENT_DIR}/.task-mode"
  if [ -f "$_TASK_MODE_FILE" ]; then
    TASK_MODE=$(head -1 "$_TASK_MODE_FILE" 2>/dev/null | tr -d '\n\r' | head -c 16)
  fi
  WIP_TOTAL=""
  if [ -f "$COS_DB_PATH" ] && command -v python3 >/dev/null 2>&1; then
    WIP_TOTAL=$(python3 -c "
import sqlite3, sys
try:
    c = sqlite3.connect('$COS_DB_PATH').cursor()
    n = c.execute(\"SELECT COUNT(*) FROM tasks WHERE status IN ('in_progress','testing')\").fetchone()[0]
    print(n)
except Exception:
    pass
" 2>/dev/null | head -c 6)
  fi
  # SES_TAIL: prefer env var (set by some adapters), fall back to the
  # session-id file we just read into _CURRENT_SESSION. Last 8 chars are
  # the random suffix that distinguishes panels of the same agent.
  SES_TAIL=""
  if [ -n "${COS_SESSION_ID:-}" ]; then
    SES_TAIL="${COS_SESSION_ID: -8}"
  elif [ -n "${_CURRENT_SESSION:-}" ]; then
    SES_TAIL="${_CURRENT_SESSION: -8}"
  fi

  # Recent block events from the hook log (last ~5 min). Surfaces hook
  # activity so the operator sees what's happening behind the scenes —
  # mirrors the caveman-mode-tracker visibility pattern.
  BLK_RECENT=""
  if [ -f "${COS_HOOK_LOG:-${COS_STATE_DIR}/.hooks.log}" ] && command -v python3 >/dev/null 2>&1; then
    BLK_RECENT=$(python3 -c "
import re, sys
from datetime import datetime, timedelta, timezone
log = '${COS_HOOK_LOG:-${COS_STATE_DIR}/.hooks.log}'
cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
n = 0
last_rules = []
try:
    with open(log) as f:
        for line in f.readlines()[-200:]:
            m = re.match(r'\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\]\s+\[([^\]]+)\]\s+\[block\]\s+(.*)', line)
            if not m: continue
            try:
                ts = datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
            except ValueError: continue
            if ts < cutoff: continue
            n += 1
            rm = re.search(r'rule=(\S+)', m.group(3) or '')
            if rm: last_rules.append(rm.group(1))
    if n:
        last = last_rules[-1] if last_rules else m.group(2)
        print(f'{n}({last})')
except OSError:
    pass
" 2>/dev/null | head -c 32 || true)
  fi

  PARTS="agent=${COS_AGENT:-?}"
  [[ -n "$SES_TAIL" ]] && PARTS="${PARTS} ses=${SES_TAIL}"
  [[ -n "$TASK_CUR" ]] && PARTS="${PARTS} task=${TASK_CUR}" || PARTS="${PARTS} task=none"
  [[ -n "$GATE_STATE" ]] && PARTS="${PARTS} gate=${GATE_STATE}" || PARTS="${PARTS} gate=unset"
  [[ -n "$WIP_TOTAL" ]] && PARTS="${PARTS} wip=${WIP_TOTAL}"
  [[ -n "$SKILL_CUR" ]] && PARTS="${PARTS} skill=${SKILL_CUR}"
  [[ -n "$ROLES_LEAD" ]] && PARTS="${PARTS} roles=${ROLES_LEAD}"
  [[ -n "$SUP_ROUTE" ]] && PARTS="${PARTS} sup=${SUP_ROUTE}"
  [[ -n "$BLK_RECENT" ]] && PARTS="${PARTS} blocks=${BLK_RECENT}"

  # verify-state: the most-recently-recorded matrix suite + result from the
  # verify ledger, so the agent sees whether the close-gate is already
  # satisfied without re-running. Agent-facing pulse only; one short field;
  # fail-open (a missing/garbled ledger just omits it).
  if [[ -f "${COS_STATE_DIR}/.last-verify.json" ]] && command -v jq >/dev/null 2>&1; then
    _VERIFY=$(jq -r 'to_entries|map(select(.value.ts))|sort_by(.value.ts)|last|"\(.key)=\(.value.status)"' "${COS_STATE_DIR}/.last-verify.json" 2>/dev/null || true)
    [[ -n "$_VERIFY" && "$_VERIFY" != "null=null" ]] && PARTS="${PARTS} verify=${_VERIFY}"
  fi

  # Aggregated PostToolUse activity since the previous prompt — Claude Code
  # does not render PostToolUse stdout, so each PostToolUse hook calls
  # `cos_record_activity` (cos-env.sh) which appends to .turn-activity.log.
  # turn_summary.py reads + clears it, returning a compact string like
  # `memory:5 graph:3 task:TASK-NNN skill:clean-code` for inclusion below.
  ACTIVITY=""
  ACTIVITY_HELPER="${_COS_HOOKS_PHYS}/_helpers/turn_summary.py"
  if [ -f "$ACTIVITY_HELPER" ] && command -v python3 >/dev/null 2>&1; then
    # || true: the banner is the operator's only transparency surface and MUST
    # be fail-open — a non-zero helper (or head -c closing the pipe early) under
    # `set -euo pipefail` must never abort the hook before the banner is emitted.
    ACTIVITY=$(python3 "$ACTIVITY_HELPER" 2>/dev/null | head -c 256 || true)
  fi
  [[ -n "$ACTIVITY" ]] && PARTS="${PARTS} | ${ACTIVITY}"

  # User-visible transparency banner. Verbosity is driven by .task-mode
  # (classify-task-mode.sh writes one of: formal | query | adhoc | chore |
  # system | gov-required | propose-formal). Casual modes collapse to a
  # minimal banner so chit-chat doesn't get drowned in noise; formal modes
  # render the full cognitive state. system mode suppresses entirely
  # (reserved for hook-internal Bash, never user-facing).
  #
  # ⚠️ markers surface inconsistencies (e.g. WIP=N but .task-current=none)
  # so the agent re-binds before the next edit.
  WIP_NUM="${WIP_TOTAL:-0}"
  WARN=""
  if [ -n "$WIP_NUM" ] && [ "$WIP_NUM" -gt 0 ] 2>/dev/null && [ -z "$TASK_CUR" ]; then
    WARN=" ⚠️ wip=${WIP_NUM} but task=none — cos task-start <ID>"
  fi

  # State-misroute: cos-env.sh exports COS_STATE_MISROUTE=1 when a
  # command inside a worktree cannot resolve its main repo, so cognitive state
  # (board, task, presence, work-log) binds to a quarantine dir invisible to the
  # Hub and to siblings. cos-env warns only ONCE to stderr; surface it on EVERY
  # turn so the operator fixes the misconfig instead of silently diverging.
  if [ "${COS_STATE_MISROUTE:-0}" = "1" ]; then
    WARN="${WARN} ⚠️ state misrouted — board/task state is going to a quarantine dir; export COS_PROJECT_ROOT=<main-repo>"
  fi

  # CLEAR-1 self-bypass count: surface how many times this session
  # self-exempted from the enforcement gates via a manual "CLEAR 1" gate write,
  # so the cost of bypassing is visible rather than silent. Fail-open.
  BYPASS_LOG="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.clear1-bypass-log"
  if [ -f "$BYPASS_LOG" ]; then
    # Count only THIS session's bypass lines (col 1 = session id); the log stays
    # append-only across sessions for /retro audit — don't truncate it.
    _CUR_SID=$(tr -d '\n\r' < "${COS_SESSION_FILE:-/nonexistent}" 2>/dev/null || true)
    if [ -n "$_CUR_SID" ]; then
      BYPASS_N=$(grep -cF "${_CUR_SID}$(printf '\t')" "$BYPASS_LOG" 2>/dev/null || true)
    else
      BYPASS_N=$(wc -l < "$BYPASS_LOG" 2>/dev/null | tr -d ' ' || true)
    fi
    [ -z "$BYPASS_N" ] && BYPASS_N=0
    if [ -n "$BYPASS_N" ] && [ "$BYPASS_N" -gt 0 ] 2>/dev/null; then
      WARN="${WARN} ℹ️ bypasses=${BYPASS_N} self-issued CLEAR-1"
    fi
  fi

  # Context-budget signal: the last usage record in the live transcript is
  # the session's true context size. Over COS_CONTEXT_BUDGET (default 200K)
  # surface an informational /compact hint to the USER — never a stop
  # directive (the agent keeps working through related/queued tasks; see
  # transparency-banner.md). Helper prints e.g. '412k>200k' or nothing; fail-open.
  TRANSCRIPT_PATH="$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)"
  CTX_OVER=""
  if [[ -n "$TRANSCRIPT_PATH" ]] && [ -f "${_COS_HOOKS_PHYS}/_helpers/context_budget.py" ] && command -v python3 >/dev/null 2>&1; then
    CTX_OVER=$(python3 "${_COS_HOOKS_PHYS}/_helpers/context_budget.py" "$TRANSCRIPT_PATH" 2>/dev/null | head -c 24 || true)
  fi
  if [[ -n "$CTX_OVER" ]]; then
    WARN="${WARN} ℹ️ ctx=${CTX_OVER} — optional /compact; /clear only between unrelated tasks"
  fi

  # pr-mode is the operator-relevant deviation from the trunk default, so surface
  # it in the banner only when on; trunk stays uncluttered.
  GIT_MODE_SEG=""
  [ "${COS_GIT_WORKFLOW:-trunk}" = "pr" ] && GIT_MODE_SEG=" · git=pr"
  # sup= rides every shape when supervision is on: which model answers is a
  # cost-and-capability fact the operator is owed on a one-line question too, and
  # omitting it is what made an enabled feature look switched off for days.
  SUP_SEG=""
  [ -n "$SUP_ROUTE" ] && SUP_SEG=" · sup=${SUP_ROUTE}"
  # A fresh/unresolved panel (session-id not seeded yet, so _read_state rejects
  # every state file) still gets a banner. This used to be suppressed on the
  # theory that 'ses=? · gate=unset' reads like a hung agent — but that traded a
  # legible first turn for an invisible one, and turn 1 is exactly when an
  # operator most needs to see the machinery is running. 'new' is honest.
  _SES_FIELD="${SES_TAIL:-new}"
  case "$TASK_MODE" in
    system)
      # The ONLY suppression: classify-task-mode.sh never writes `system` for a
      # user prompt — it is hook-internal Bash, where no reply exists to prefix.
      USER_BANNER=""
      ;;
    query|adhoc|chore)
      USER_BANNER="🔔 ses=${_SES_FIELD} · mode=${TASK_MODE}${SUP_SEG}${GIT_MODE_SEG}${WARN}"
      ;;
    *)
      USER_BANNER="🔔 ses=${_SES_FIELD} · mode=${TASK_MODE:-formal} · task=${TASK_CUR:-none} · gate=${GATE_STATE:-unset} · skill=${SKILL_CUR:--} · roles=${ROLES_LEAD:--}${SUP_SEG}${GIT_MODE_SEG}${WARN}"
      ;;
  esac

  # fold the test-cadence policy into the agent-only pulse so
  # it is seen in-band (agents skip test-discipline.md). Formal work only — casual
  # chat never runs suites, so the reminder would be noise. Additive; the visible
  # banner + its extraction marker are untouched (appended AFTER the banner line).
  CADENCE=""
  case "${TASK_MODE:-formal}" in
    query|adhoc|chore|system) ;;
    *) CADENCE="
[test-cadence] targeted test during dev · matrix suite ONCE at close · background heavy (>60s) suites, never idle-wait · full sweep is pre-merge only" ;;
  esac

  if [ -n "$USER_BANNER" ]; then
    CONTEXT="[coding-os pulse] ${PARTS}
USER_BANNER (rule transparency-banner — echo as FIRST line of visible reply): ${USER_BANNER}${CADENCE}"
  else
    CONTEXT="[coding-os pulse] ${PARTS}${CADENCE}"
  fi
  printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":$(printf '%s' "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"
}
