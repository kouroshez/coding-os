#!/usr/bin/env bash
# SessionStart hook: Re-inject critical workflow context after compaction, resume, or startup.
# Agent-aware: session-id + volatile state live in COS_AGENT_DIR so two agents
# on the same project never share ephemeral state. Shared artifacts (DB, log)
# stay at COS_STATE_DIR. Full design in docs/engineering/state-files.md.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

# Resolve physical hooks dir — required for consumer projects where
# .claude/hooks/ is a real dir but each hook FILE is a symlink to
# src/core/hooks/. pwd -P only resolves symlinked directories, not files,
# so dirname+"$0" stays in .claude/hooks/ and ../thinking_os misses.
# BASH_SOURCE[0]+readlink follows the file symlink to its physical target.
_cos_src="${BASH_SOURCE[0]}"
while [ -L "$_cos_src" ]; do
  _cos_dir="$(cd -P "$(dirname "$_cos_src")" && pwd)"
  _cos_src="$(readlink "$_cos_src")"
  [[ "$_cos_src" != /* ]] && _cos_src="${_cos_dir}/${_cos_src}"
done
_COS_HOOKS_PHYS="$(cd -P "$(dirname "$_cos_src")" && pwd)"
unset _cos_src _cos_dir

INPUT="$(cos_read_stdin_bounded 2)"

# Upgrade panel-id from stdin session_id BEFORE any state file is touched.
# After this call, $COS_PANEL_ID / $COS_PANEL_DIR / $COS_SESSION_FILE reflect
# the strongest available signal (Claude/Codex/Cursor hook payload UUID).
# All subsequent reads/writes in this hook target the right panel dir.
cos_panel_upgrade_from_payload "$INPUT" 2>/dev/null || true

COS_HOOK_RUNTIME_MODEL="$(printf '%s' "$INPUT" | jq -r '.model // empty' 2>/dev/null || true)"
export COS_HOOK_RUNTIME_MODEL

# Persist the model so hooks that don't receive it in stdin (PostToolUse
# that dispatches an async worker, CLI-originated task-done, etc.) can
# stamp task_outcomes.model and feed routing_weights.  File is truncated
# each write — only the latest signal matters.
if [[ -n "$COS_HOOK_RUNTIME_MODEL" ]] && [[ -n "${COS_AGENT_DIR:-}" ]]; then
  mkdir -p "$COS_AGENT_DIR" 2>/dev/null || true
  printf '%s' "$COS_HOOK_RUNTIME_MODEL" > "$COS_AGENT_DIR/.model" 2>/dev/null || true
fi
# SessionStart payloads carry `.source`; UserPromptSubmit carries `.prompt`.
# Treat prompt submits as their own source so Codex doesn't rotate session-id
# or clear volatile state on every prompt.
SOURCE=$(echo "$INPUT" | jq -r '
  if has("source") and (.source | type == "string") then .source
  elif has("prompt") then "user-prompt-submit"
  else "startup"
  end
' 2>/dev/null || echo "startup")
cos_log_hook session-context fire "source=${SOURCE}"

# Ensure all dirs exist — COS_STATE_DIR for shared, COS_AGENT_DIR for
# per-agent shared, COS_PANEL_DIR for per-panel private.
mkdir -p "$COS_STATE_DIR" "$COS_AGENT_DIR" "$COS_PANEL_DIR"

# Refresh the .agent marker whenever cos-env.sh detected the runtime.
# Stale markers (e.g. `cursor` left over after switching to Claude) mis-route
# fallback paths in cos_retrieve / capture.py — rewrite on every session
# boundary so the *last* adapter to start is authoritative.
if [[ -n "${COS_AGENT:-}" ]] && [[ "$COS_AGENT" != "unknown" ]]; then
  _AGENT_MARKER="$COS_STATE_DIR/.agent"
  if [[ ! -f "$_AGENT_MARKER" ]] || [[ "$(cat "$_AGENT_MARKER" 2>/dev/null)" != "$COS_AGENT" ]]; then
    printf '%s' "$COS_AGENT" > "$_AGENT_MARKER" 2>/dev/null || true
    cos_log_hook session-context agent-refresh "agent=${COS_AGENT}"
  fi
  unset _AGENT_MARKER
fi

# Refresh the agent-level "latest active session" pointer that the
# long-lived MCP server reads for attribution (it has no $COS_PANEL_DIR,
# so it cannot read the strict per-panel session-id). On a non-startup
# prompt the panel session-id already exists; mirror it here so a task
# created via MCP this turn is attributed to the live session, not a
# stale fossil. Last-writer-wins across concurrent panels — documented
# approximation in docs/engineering/state-files.md. Startup writes it
# after id generation below.
if [[ "$SOURCE" != "startup" ]] && [[ -n "${COS_SESSION_FILE:-}" ]] && [[ -f "$COS_SESSION_FILE" ]]; then
  tr -d '\n\r' < "$COS_SESSION_FILE" > "$COS_AGENT_DIR/.active-session" 2>/dev/null || true
fi

# Generate session ID ONLY on fresh startup — NOT on compact or resume.
if [[ "$SOURCE" == "startup" ]]; then
  # Orphan recovery: if the PREVIOUS session in THIS PANEL had observations
  # but never got a clean Stop, its session_summaries row was never built.
  # We rebuild it here before the ID is overwritten. session_summary.py is
  # idempotent (UPSERT) so this is a no-op when Stop fired cleanly.
  # Falls back to legacy flat $COS_AGENT_DIR/session-id during the
  # migration window.
  PREV_SESSION_ID=""
  if [ -f "$COS_SESSION_FILE" ]; then
    PREV_SESSION_ID=$(cat "$COS_SESSION_FILE" 2>/dev/null || true)
  elif [ -f "${COS_AGENT_DIR}/session-id" ]; then
    PREV_SESSION_ID=$(cat "${COS_AGENT_DIR}/session-id" 2>/dev/null || true)
  fi

  if [ -n "$PREV_SESSION_ID" ] && [ -f "$COS_DB_PATH" ]; then
    SUMMARY_PY="${_COS_HOOKS_PHYS}/../thinking_os/session_summary.py"
    if [ -f "$SUMMARY_PY" ]; then
      python3 "$SUMMARY_PY" "$PREV_SESSION_ID" "" "$COS_DB_PATH" 2>/dev/null || true
      cos_log_hook session-context recovered "prev_session=${PREV_SESSION_ID}"
    fi
  fi

  # Session-id is agent-prefixed so logs and state files are self-describing.
  # Format: ses-<agent>-YYYYMMDD-HHMMSS-xxxx. Two agents (Claude+Codex) on
  # the same repo get distinct ids; two PANELS of the same agent get
  # distinct ids too because each panel writes to its own $COS_SESSION_FILE
  # (which now lives in $COS_PANEL_DIR, not $COS_AGENT_DIR).
  SESSION_ID="ses-${COS_AGENT}-$(date +%Y%m%d-%H%M%S)-$(head -c 4 /dev/urandom | xxd -p | head -c 4)"
  echo "$SESSION_ID" > "$COS_SESSION_FILE"
  # Seed the agent-level active-session pointer for the MCP server (see
  # the non-startup refresh above for rationale).
  printf '%s' "$SESSION_ID" > "$COS_AGENT_DIR/.active-session" 2>/dev/null || true

  # Clear volatile markers from previous sessions. Scope is THIS PANEL's
  # private dir — sibling panels of the same agent are untouched, and the
  # other agent's state is also untouched. Files that intentionally remain
  # shared (.task-mode, .model, .swimlane, .last-verify) are NOT cleared.
  CLEARED=0
  for STATE_FILE in \
    "${COS_PANEL_DIR}/.thinking_os-gate" \
    "${COS_PANEL_DIR}/.task-current" \
    "${COS_PANEL_DIR}/.zoom-checkpoint" \
    "${COS_PANEL_DIR}/.active-skill" \
    "${COS_PANEL_DIR}/.doc-anchor" \
    "${COS_PANEL_DIR}/.memory-check" \
    "${COS_PANEL_DIR}/.learn-suggestions" \
    "${COS_PANEL_DIR}/.active-formula" \
    "${COS_PANEL_DIR}/.doc-anchor-override" \
    "${COS_PANEL_DIR}/.memory-check-override" \
    "${COS_PANEL_DIR}/.uv-heredoc-override" \
    "${COS_PANEL_DIR}/.zoom-prompt-suggested" \
    "${COS_PANEL_DIR}/.docs-first-nudged" \
    "${COS_PANEL_DIR}/.roles-composed" \
    "${COS_PANEL_DIR}/.roles" \
    "${COS_PANEL_DIR}/.role" \
    "${COS_PANEL_DIR}/.graph-call-seen" \
    "${COS_PANEL_DIR}/.abandoned-task-warned" \
    "${COS_PANEL_DIR}/.graph-empty-warning-shown" \
    "${COS_STATE_DIR}/.capture-errors.log"; do
    if [ -e "$STATE_FILE" ]; then
      rm -f "$STATE_FILE"
      CLEARED=$((CLEARED + 1))
    fi
  done
  cos_log_hook session-context reset "cleared=${CLEARED} panel=${COS_PANEL_ID}"
fi

# On compact or resume: re-inject critical workflow reminders + current state snapshot
if [[ "$SOURCE" == "compact" ]] || [[ "$SOURCE" == "resume" ]]; then
  printf '%s\n' \
    '[Session Context Recovery]' \
    '' \
    'CRITICAL WORKFLOW RULES:' \
    '1. Task lifecycle — cos task-start/move/done (NEVER hand-edit status:/checkboxes; enforce-task-transition BLOCKS it). Look up via cos task-show / cos_task_search, not ls/grep.' \
    '2. Verification Matrix — run domain verification BEFORE marking done' \
    '3. Complexity Gate — record gate before writing code (thinking_os-gate.sh BLOCKS without it)' \
    '4. Domain skill — invoke matching skill before writing code' \
    '5. MCP tools deferred — ToolSearch("select:mcp__coding-os__cos_task_move,mcp__coding-os__cos_task_show,mcp__coding-os__cos_task_search,mcp__coding-os__cos_supervise_record_output") before first use each session' \
    ''

  # Emit dynamic state snapshot so agent knows WHERE it is after compaction.
  source "$(dirname "$0")/check-state.sh" 2>/dev/null || true
  # Helper: panel file ONLY. Reading the agent-dir fossil here would leak
  # another panel's compact/resume snapshot into this panel (TASK-035).
  _panel_or_agent() {
    local base="$1"
    if [[ -f "${COS_PANEL_DIR}/${base}" ]]; then
      echo "${COS_PANEL_DIR}/${base}"
    fi
  }
  _GATE_STATUS="not recorded"
  _GATE_FILE="$(_panel_or_agent .thinking_os-gate)"
  if [[ -n "$_GATE_FILE" ]]; then
    check_state "$_GATE_FILE" 7200
    if [[ "$STATE_VALID" == "true" ]]; then
      _GATE_STATUS="$STATE_VALUE (valid)"
    else
      _GATE_STATUS="STALE — ${STATE_REASON} — re-record: write-state.sh .thinking_os-gate \"CLEAR 1\""
    fi
  fi
  _TASK_CURRENT=""
  _TASK_FILE="$(_panel_or_agent .task-current)"
  if [[ -n "$_TASK_FILE" ]]; then
    _TASK_CURRENT=$(cat "$_TASK_FILE" 2>/dev/null | head -1 | cut -d' ' -f2- || true)
  fi
  _ACTIVE_SKILL=""
  _SKILL_FILE="$(_panel_or_agent .active-skill)"
  if [[ -n "$_SKILL_FILE" ]]; then
    _ACTIVE_SKILL=$(cat "$_SKILL_FILE" 2>/dev/null | head -1 | cut -d' ' -f2- || true)
  fi

  printf '%s\n' "[Session State] gate=${_GATE_STATUS} | task=${_TASK_CURRENT:-none} | skill=${_ACTIVE_SKILL:-none}"
  printf '%s\n' ""
fi

# On startup: show active in-progress tasks (Phase L Scrumban) so the agent
# inherits open work without having to query the board first.
if [[ "$SOURCE" == "startup" ]]; then
  if [ -d "docs/tasks" ] && [ -f "$COS_DB_PATH" ]; then
    # bash 5.3.9 deadlocks `$(python3 - <<HEREDOC)`. Form B (separate
    # .py file invoked as `python3 path/to/file.py`) is the only
    # deadlock-immune pattern. Resolve via readlink so symlinked install
    # paths still find _helpers/.
    _src="${BASH_SOURCE[0]}"
    while [ -L "$_src" ]; do
      _dir="$(cd -P "$(dirname "$_src")" && pwd)"
      _src="$(readlink "$_src")"
      [[ "$_src" != /* ]] && _src="$_dir/$_src"
    done
    HSRC="$(cd -P "$(dirname "$_src")" && pwd)"
    unset _src _dir
    WIP_HELPER="${HSRC}/_helpers/wip_lines.py"
    if [[ -f "$WIP_HELPER" ]]; then
      WIP_LINES=$(python3 "$WIP_HELPER" "$COS_DB_PATH" 2>/dev/null || true)
    else
      WIP_LINES=""
    fi
    if [ -n "$WIP_LINES" ]; then
      echo "[Session Start] Active tasks (in_progress / testing):"
      echo "$WIP_LINES"
      echo "  Resume with: cos task-show TASK-NNN  |  cos board"
    fi
  fi

  # Surface an uncommitted working tree — a prior session may have been
  # abandoned mid-task. The agent must NOT blind-commit another session's
  # WIP (see src/core/rules/git-workflow.md § Concurrent sessions).
  # Read-only; never blocks.
  if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    DIRTY=$(git status --porcelain 2>/dev/null | head -20 || true)
    if [ -n "$DIRTY" ]; then
      DIRTY_N=$(printf '%s\n' "$DIRTY" | wc -l | tr -d ' ')
      echo ""
      echo "[Uncommitted Work] ${DIRTY_N} file(s) modified — possibly a prior session's WIP:"
      printf '%s\n' "$DIRTY" | sed 's/^/  /'
      echo "  Commit with EXPLICIT paths only — never a bare 'git commit'."
    fi
  fi

  # Prime the hot task-tool family once. These cos_* tools are deferred
  # (Claude-harness-side, not repo-controllable — see mcp-schema-traps.md),
  # so front-loading one ToolSearch avoids mid-task InputValidationError
  # round-trips that push the agent back to raw Edit/Bash (TASK-059).
  echo ""
  echo "[MCP Prime] Hot tools are deferred — load the task family ONCE now so you don't fall back to raw Edit/Bash for task ops:"
  echo '  ToolSearch("select:mcp__coding-os__cos_task_move,mcp__coding-os__cos_task_show,mcp__coding-os__cos_task_board,mcp__coding-os__cos_task_search,mcp__coding-os__cos_supervise_record_output,mcp__coding-os__cos_classify_prompt")'

  # Phase G.10 — Agent digest: the always-active working-memory snapshot
  # (identity, top domains, beliefs, fading patterns, breakthroughs). The
  # digest was printed but never regenerated (cos_digest_regenerate had no
  # hook caller, so digest.md never existed) — regenerate it here first so
  # the agent inherits a FRESH memory summary each session (TASK-055).
  if [ -f "$COS_DB_PATH" ]; then
    DIGEST_REGEN="${_COS_HOOKS_PHYS}/_helpers/digest_regen.py"
    if [ -f "$DIGEST_REGEN" ]; then
      python3 "$DIGEST_REGEN" "$COS_DB_PATH" "${COS_PROJECT_ROOT:-$(pwd)}" 2>/dev/null || true
    fi
  fi
  DIGEST_PATH="${COS_STATE_DIR:-.coding-os}/digest.md"
  if [ -f "$DIGEST_PATH" ]; then
    echo ""
    echo "[Agent Digest]"
    cat "$DIGEST_PATH"
  fi

  # Phase EVO — Project Trajectory: inject latest trajectory snapshot so the
  # agent knows WHERE the project is heading (not just what tasks are open).
  # The trajectory section is already embedded in digest.md when present;
  # this helper also surfaces it as a standalone block for emphasis.
  if [ -f "$COS_DB_PATH" ]; then
    TRAJ_HELPER="${_COS_HOOKS_PHYS}/_helpers/trajectory_startup.py"
    if [ -f "$TRAJ_HELPER" ]; then
      python3 "$TRAJ_HELPER" "$COS_DB_PATH" 2>/dev/null || true
    fi
  fi

  # Phase EVO — Autonomous Routing Evolution: detect stale routing weights
  # and auto-trigger recalculate_weights when N=15 new outcomes accumulated.
  if [ -f "$COS_DB_PATH" ]; then
    ROUTING_HELPER="${_COS_HOOKS_PHYS}/_helpers/routing_evolution.py"
    if [ -f "$ROUTING_HELPER" ]; then
      python3 "$ROUTING_HELPER" "$COS_DB_PATH" 2>/dev/null || true
    fi
  fi

  # Token economics display — informational, non-blocking
  if [ -f "$COS_DB_PATH" ]; then
    STARTUP_PY="${_COS_HOOKS_PHYS}/../thinking_os/session_startup.py"
    if [ -f "$STARTUP_PY" ]; then
      python3 "$STARTUP_PY" "$COS_DB_PATH" 2>/dev/null || true
    fi
  fi
fi

# On user-prompt-submit: emit a compact per-turn workflow state via the
# Claude Code hookSpecificOutput JSON format so the operator sees the
# system pulse on every prompt (active task, complexity gate, board WIP,
# session-id tail). Mirrors the caveman-mode-tracker.js pattern so the UI
# renders this as a compact labeled "additionalContext" block.
if [[ "$SOURCE" == "user-prompt-submit" ]]; then
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
  # panels (TASK-035 regression: cos-env.sh + check-state.sh now reject
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
    # fall back to $COS_AGENT_DIR (cross-panel leak protection, TASK-035).
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

  # Composed role chain — surface the ACTIVE role + its position in the chain
  # so the banner tracks what the agent is DOING, not a frozen lead (TASK-057).
  # advance-role.sh moves .role along .roles by work phase. Both files are
  # panel-scoped (written panel-first by roles_state); read panel-first with an
  # agent-level fallback. Format: "<active> N/M" e.g. "implementer 3/4".
  ROLES_LEAD=""
  _ROLES_FILE="${COS_PANEL_DIR}/.roles"
  [ -f "$_ROLES_FILE" ] || _ROLES_FILE="${COS_AGENT_DIR}/.roles"
  _ROLE_FILE="${COS_PANEL_DIR}/.role"
  [ -f "$_ROLE_FILE" ] || _ROLE_FILE="${COS_AGENT_DIR}/.role"
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

  # Task mode (classify-task-mode.sh writes this on every UserPromptSubmit
  # via a separate hook). NOT session-prefixed — it's a single token per
  # the writer's contract. Values: formal | query | adhoc | chore |
  # system | gov-required | propose-formal. Drives banner verbosity:
  # casual modes get a minimal banner, formal modes get the full one.
  TASK_MODE=""
  if [ -f "${COS_AGENT_DIR}/.task-mode" ]; then
    TASK_MODE=$(head -1 "${COS_AGENT_DIR}/.task-mode" 2>/dev/null | tr -d '\n\r' | head -c 16)
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

  # Active audits (status:in_progress in docs/tasks/audits/audit-*.md).
  # One-line summary: count + last id. inject-resume-prompt.sh emits the
  # full block on SessionStart; here we surface a per-turn ping.
  AUDIT_ACTIVE=""
  if [ -d "docs/tasks/audits" ]; then
    # Match BOTH conventions: YAML frontmatter (template canonical:
    # `^status: in_progress`) AND markdown bold (legacy/lenient:
    # `**Status:** in_progress`). The audit-checklist-template.md mandates
    # YAML, but historic audits use the markdown form — match both so the
    # banner reflects reality, not template-purism.
    # grep -l exits 1 when no matches → wrap with `|| true` so pipefail
    # doesn't kill the whole hook.
    # Pattern: YAML frontmatter requires `^status: in_progress` (line start);
    # markdown bold `**Status:** in_progress` can appear mid-line (e.g.
    # `**Task:** TASK-032 · **Status:** in_progress`), so no `^` anchor on
    # that alternative. `**Status:**` is distinctive enough to avoid false
    # positives from prose mentioning `in_progress`.
    AUDIT_ACTIVE=$({ grep -lE "(^status:[[:space:]]+in_progress|\*\*Status:\*\*[[:space:]]+in_progress)" docs/tasks/audits/audit-*.md 2>/dev/null || true; } \
      | python3 -c '
import os, sys, re
files = [l.strip() for l in sys.stdin if l.strip()]
if not files: sys.exit(0)
last_id = ""
unchecked_total = 0
# audit-table data row: starts with "|" and contains "| no |" (Verified=no).
# Same heuristic inject-resume-prompt.sh uses — surface actionable scope,
# not just file count.
ROW = re.compile(r"^\|.*\|\s*no\s*\|")
for f in files:
    try:
        with open(f) as fh:
            for line in fh:
                if not last_id:
                    m = re.match(r"audit_id:\s*(\S+)", line)
                    if m: last_id = m.group(1)
                if ROW.match(line):
                    unchecked_total += 1
    except OSError: pass
    if not last_id:
        last_id = os.path.basename(f).replace("audit-", "").replace(".md", "")
tag = f"{len(files)}({last_id})"
if unchecked_total:
    tag += f"·{unchecked_total}-unchecked"
print(tag)
' 2>/dev/null | head -c 64 || true)
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
" 2>/dev/null | head -c 32)
  fi

  PARTS="agent=${COS_AGENT:-?}"
  [[ -n "$SES_TAIL" ]] && PARTS="${PARTS} ses=${SES_TAIL}"
  [[ -n "$TASK_CUR" ]] && PARTS="${PARTS} task=${TASK_CUR}" || PARTS="${PARTS} task=none"
  [[ -n "$GATE_STATE" ]] && PARTS="${PARTS} gate=${GATE_STATE}" || PARTS="${PARTS} gate=unset"
  [[ -n "$WIP_TOTAL" ]] && PARTS="${PARTS} wip=${WIP_TOTAL}"
  [[ -n "$SKILL_CUR" ]] && PARTS="${PARTS} skill=${SKILL_CUR}"
  [[ -n "$ROLES_LEAD" ]] && PARTS="${PARTS} roles=${ROLES_LEAD}"
  [[ -n "$AUDIT_ACTIVE" ]] && PARTS="${PARTS} audit=${AUDIT_ACTIVE}"
  [[ -n "$BLK_RECENT" ]] && PARTS="${PARTS} blocks=${BLK_RECENT}"

  # Aggregated PostToolUse activity since the previous prompt — Claude Code
  # does not render PostToolUse stdout, so each PostToolUse hook calls
  # `cos_record_activity` (cos-env.sh) which appends to .turn-activity.log.
  # turn_summary.py reads + clears it, returning a compact string like
  # `memory:5 graph:3 task:TASK-42 skill:clean-code` for inclusion below.
  ACTIVITY=""
  ACTIVITY_HELPER="${_COS_HOOKS_PHYS}/_helpers/turn_summary.py"
  if [ -f "$ACTIVITY_HELPER" ] && command -v python3 >/dev/null 2>&1; then
    ACTIVITY=$(python3 "$ACTIVITY_HELPER" 2>/dev/null | head -c 256)
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

  case "$TASK_MODE" in
    system)
      USER_BANNER=""
      ;;
    query|adhoc|chore)
      USER_BANNER="🔔 ses=${SES_TAIL:-?} · mode=${TASK_MODE}${WARN}"
      ;;
    *)
      USER_BANNER="🔔 ses=${SES_TAIL:-?} · mode=${TASK_MODE:-formal} · task=${TASK_CUR:-none} · gate=${GATE_STATE:-unset} · skill=${SKILL_CUR:--} · roles=${ROLES_LEAD:--} · audit=${AUDIT_ACTIVE:--}${WARN}"
      ;;
  esac

  if [ -n "$USER_BANNER" ]; then
    CONTEXT="[coding-os pulse] ${PARTS}
USER_BANNER (rule transparency-banner — echo as FIRST line of visible reply): ${USER_BANNER}"
  else
    CONTEXT="[coding-os pulse] ${PARTS}"
  fi
  printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":$(printf '%s' "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"
fi

exit 0
