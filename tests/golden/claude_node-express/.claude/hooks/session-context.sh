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
# the strongest available signal (Claude/Codex hook payload UUID).
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

# Loud, debounced collision diagnostic: when the panel id fell back
# to a PPID hash (no runtime session-id var exported), two sibling panels that
# share a PPID can collide on this one panel dir and clobber each other's
# task/gate/skill state. Surface it ONCE per session — a silent collision is
# the failure mode this converts into an observed, fail-safe event.
if [[ "${COS_PANEL_ID_SOURCE:-}" == "ppid" ]]; then
  _ppid_marker="${COS_PANEL_DIR}/.ppid-collision-warned"
  if [[ ! -f "$_ppid_marker" ]]; then
    echo "warning: coding-os panel id resolved via PPID fallback ('${COS_PANEL_ID}') — no runtime session-id var (CLAUDE_CODE_SESSION_ID / CODEX_SESSION_ID) exported. Sibling panels sharing this PPID may collide on one state dir and clobber task/gate/skill state. See docs/engineering/state-files.md." >&2
    printf 'panel_id=%s reason=no-runtime-session-id\n' "$COS_PANEL_ID" > "$_ppid_marker" 2>/dev/null || true
    cos_log_hook session-context warn "reason=ppid-fallback panel=${COS_PANEL_ID}" || true
  fi
fi

# Refresh the .agent marker whenever cos-env.sh detected the runtime.
# Stale markers (e.g. `codex` left over after switching to Claude) mis-route
# fallback paths in capture.py — rewrite on every session
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
      python3 "$SUMMARY_PY" "$PREV_SESSION_ID" "" "$COS_DB_PATH" >/dev/null 2>&1 || true
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
  # other agent's state is also untouched. NOT cleared: agent-shared
  # (.model, .swimlane, .last-verify) and self-refreshing (.task-mode is
  # now per-panel but rewritten every prompt by classify-task-mode).
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
    "${COS_PANEL_DIR}/.git-mode-nudged" \
    "${COS_PANEL_DIR}/.roles-composed" \
    "${COS_PANEL_DIR}/.roles" \
    "${COS_PANEL_DIR}/.role" \
    "${COS_PANEL_DIR}/.graph-call-seen" \
    "${COS_PANEL_DIR}/.abandoned-task-warned" \
    "${COS_PANEL_DIR}/.graph-empty-warning-shown" \
    "${COS_PANEL_DIR}/.last-discovery-reminder" \
    "${COS_STATE_DIR}/.capture-errors.log"; do
    if [ -e "$STATE_FILE" ]; then
      rm -f "$STATE_FILE"
      CLEARED=$((CLEARED + 1))
    fi
  done
  # Per-panel nudge debounce DIRECTORIES — rm -rf, they hold
  # one file per matched pattern/leg, not a single marker.
  for STATE_DIR_MARK in \
    "${COS_PANEL_DIR}/.graph-nudge" \
    "${COS_PANEL_DIR}/.task-nudge" \
    "${COS_PANEL_DIR}/.jit-nudge" \
    "${COS_PANEL_DIR}/.test-first-reminded"; do
    if [ -d "$STATE_DIR_MARK" ]; then
      rm -rf "$STATE_DIR_MARK"
      CLEARED=$((CLEARED + 1))
    fi
  done
  # Agent-scoped graph consult markers (.graph/ctx-* / plan-*). Prune by age,
  # not wholesale: other live panels share this dir, and freshness binding
  # already invalidates a marker whose file changed. 12h keeps a session warm.
  if [ -d "${COS_AGENT_DIR}/.graph" ]; then
    find "${COS_AGENT_DIR}/.graph" -type f -mmin +720 -delete 2>/dev/null || true
  fi
  cos_log_hook session-context reset "cleared=${CLEARED} panel=${COS_PANEL_ID}"
fi

# ---------------------------------------------------------------------------
# SessionStart cognitive emission — channel split (spec:
# src/core/rules/transparency-banner.md § SessionStart emission). Two buffers:
#   SS_HIDDEN  — agent context (recovery rules, [Session State], [MCP Prime],
#                [Agent Digest]). Claude -> ONE hidden additionalContext envelope
#                (operator never sees it). Codex -> folded into the delegate's
#                plain text (the dispatcher merges 2>&1 + re-wraps the card).
#   SS_VISIBLE — operator alerts that MUST stay in the chat ([Uncommitted Work],
#                active-tasks). Claude -> stderr (visible, like warn-mcp-down's
#                banner). Codex -> folded in with the rest.
SS_HIDDEN=""
SS_VISIBLE=""
_ss_append() {
  local _name="$1" _txt="$2"
  if [[ -n "$_txt" ]]; then
    if [[ -z "${!_name}" ]]; then
      printf -v "$_name" '%s' "$_txt"
    else
      printf -v "$_name" '%s\n%s' "${!_name}" "$_txt"
    fi
  fi
}

# On compact or resume: re-inject critical workflow reminders + current state
# snapshot (HIDDEN — agent recovery context, not operator noise).
if [[ "$SOURCE" == "compact" ]] || [[ "$SOURCE" == "resume" ]]; then
  _recovery="$(printf '%s\n' \
    '[Session Context Recovery]' \
    '' \
    'CRITICAL WORKFLOW RULES:' \
    '1. Task lifecycle — cos task-start/move/done (NEVER hand-edit status:/checkboxes; enforce-task-transition BLOCKS it). Look up via cos task-show / cos_task_search, not ls/grep.' \
    '2. Verification Matrix — run domain verification BEFORE marking done' \
    '3. Complexity Gate — record gate before writing code (thinking_os-gate.sh BLOCKS without it)' \
    '4. Domain skill — invoke matching skill before writing code' \
    '5. MCP tools deferred — ToolSearch("select:mcp__coding-os__cos_task_move,mcp__coding-os__cos_task_show,mcp__coding-os__cos_task_search,mcp__coding-os__cos_supervise_record_output") before first use each session')"

  # Emit dynamic state snapshot so agent knows WHERE it is after compaction.
  source "$(dirname "$0")/check-state.sh" 2>/dev/null || true
  # Helper: panel file ONLY. Reading the agent-dir fossil here would leak
  # another panel's compact/resume snapshot into this panel.
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

  _recovery="${_recovery}"$'\n'"[Session State] gate=${_GATE_STATUS} | task=${_TASK_CURRENT:-none} | skill=${_ACTIVE_SKILL:-none}"
  _ss_append SS_HIDDEN "$_recovery"
fi

# On startup: show active in-progress tasks (Scrumban) so the agent
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
    # Active in-progress work is an operator-facing status signal (VISIBLE).
    if [ -n "$WIP_LINES" ]; then
      _ss_append SS_VISIBLE "[Session Start] Active tasks (in_progress / testing):
${WIP_LINES}
  Resume with: cos task-show TASK-NNN  |  cos board"
    fi
  fi

  # Surface an uncommitted working tree — a prior session may have been
  # abandoned mid-task. The agent must NOT blind-commit another session's
  # WIP (see src/core/rules/git-workflow.md § Concurrent sessions).
  # Read-only; never blocks. Operator-facing safety alert (VISIBLE).
  if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    DIRTY=$(git status --porcelain 2>/dev/null | head -20 || true)
    if [ -n "$DIRTY" ]; then
      DIRTY_N=$(printf '%s\n' "$DIRTY" | wc -l | tr -d ' ')
      _ss_append SS_VISIBLE "[Uncommitted Work] ${DIRTY_N} file(s) modified — possibly a prior session's WIP:
$(printf '%s\n' "$DIRTY" | sed 's/^/  /')
  Commit with EXPLICIT paths only — never a bare 'git commit'."
    fi
  fi

  # Prime the hot task-tool family once. These cos_* tools are deferred
  # (Claude-harness-side, not repo-controllable — see mcp-schema-traps.md),
  # so front-loading one ToolSearch avoids mid-task InputValidationError
  # round-trips that push the agent back to raw Edit/Bash. Agent-only (HIDDEN).
  _ss_append SS_HIDDEN "[MCP Prime] Hot tools are deferred — load the task family ONCE now so you don't fall back to raw Edit/Bash for task ops:
  ToolSearch(\"select:mcp__coding-os__cos_task_move,mcp__coding-os__cos_task_show,mcp__coding-os__cos_task_board,mcp__coding-os__cos_task_search,mcp__coding-os__cos_supervise_record_output,mcp__coding-os__cos_classify_prompt\")"
fi

# Agent digest = memory inheritance (HIDDEN). Runs on a FRESH process only —
# startup or resume. A same-session auto-compact (Claude-only source) keeps the
# digest in working memory, so re-emitting it there is the wasted re-dump that
# put a multi-thousand-token wall mid-chat; suppress it on compact
# (src/core/rules/transparency-banner.md § SessionStart emission, state-files.md §S5).
if [[ "$SOURCE" == "startup" || "$SOURCE" == "resume" ]]; then
  # Constitution slice = the values layer the rules derive from (HIDDEN). Same
  # startup/resume gate as the digest (suppressed on compact — the slice is
  # already in working memory). SSOT is docs/governance/constitution.md; we
  # surface only the delimited slice so the file stays the single source.
  CONSTITUTION_DOC="${COS_PROJECT_ROOT:-$(pwd)}/docs/governance/constitution.md"
  if [ -f "$CONSTITUTION_DOC" ] && grep -q '<!-- SLICE:START -->' "$CONSTITUTION_DOC" 2>/dev/null && grep -q '<!-- SLICE:END -->' "$CONSTITUTION_DOC" 2>/dev/null; then
    # Both markers required: a missing SLICE:END would make sed dump the rest of
    # the file into the injection (unbounded tokens) — guard before extracting.
    CONSTITUTION_SLICE=$(sed -n '/<!-- SLICE:START -->/,/<!-- SLICE:END -->/p' "$CONSTITUTION_DOC" 2>/dev/null | grep -vE 'SLICE:(START|END)' || true)
    if [ -n "$CONSTITUTION_SLICE" ]; then
      _ss_append SS_HIDDEN "[Constitution] (values the rules derive from — full: docs/governance/constitution.md)
${CONSTITUTION_SLICE}"
    fi
  fi

  # Agent digest: the always-active working-memory snapshot
  # (identity, top domains, beliefs, fading patterns, breakthroughs). The
  # digest was printed but never regenerated (cos_digest_regenerate had no
  # hook caller, so digest.md never existed) — regenerate it here first so
  # the agent inherits a FRESH memory summary each session. The regen is a
  # side-effect (writes digest.md); its stdout is not agent content -> /dev/null.
  if [ -f "$COS_DB_PATH" ]; then
    DIGEST_REGEN="${_COS_HOOKS_PHYS}/_helpers/digest_regen.py"
    if [ -f "$DIGEST_REGEN" ]; then
      python3 "$DIGEST_REGEN" "$COS_DB_PATH" "${COS_PROJECT_ROOT:-$(pwd)}" >/dev/null 2>&1 || true
    fi
  fi
  DIGEST_PATH="${COS_STATE_DIR:-.coding-os}/digest.md"
  if [ -f "$DIGEST_PATH" ]; then
    _ss_append SS_HIDDEN "[Agent Digest]
$(cat "$DIGEST_PATH")"
  fi

  # Project Trajectory: inject latest trajectory snapshot so the
  # agent knows WHERE the project is heading (not just what tasks are open).
  # The trajectory section is already embedded in digest.md when present;
  # this helper also surfaces it as a standalone block for emphasis.
  if [ -f "$COS_DB_PATH" ]; then
    TRAJ_HELPER="${_COS_HOOKS_PHYS}/_helpers/trajectory_startup.py"
    if [ -f "$TRAJ_HELPER" ]; then
      _ss_append SS_HIDDEN "$(python3 "$TRAJ_HELPER" "$COS_DB_PATH" 2>/dev/null || true)"
    fi
  fi

  # Autonomous Routing Evolution: detect stale routing weights
  # and auto-trigger recalculate_weights when N=15 new outcomes accumulated.
  if [ -f "$COS_DB_PATH" ]; then
    ROUTING_HELPER="${_COS_HOOKS_PHYS}/_helpers/routing_evolution.py"
    if [ -f "$ROUTING_HELPER" ]; then
      _ss_append SS_HIDDEN "$(python3 "$ROUTING_HELPER" "$COS_DB_PATH" 2>/dev/null || true)"
    fi
  fi

  # Token economics display — informational, non-blocking
  if [ -f "$COS_DB_PATH" ]; then
    STARTUP_PY="${_COS_HOOKS_PHYS}/../thinking_os/session_startup.py"
    if [ -f "$STARTUP_PY" ]; then
      _ss_append SS_HIDDEN "$(python3 "$STARTUP_PY" "$COS_DB_PATH" 2>/dev/null || true)"
    fi
  fi
fi

# Emit the accumulated SessionStart blocks on the right channel. Claude: alerts
# to stderr (operator-visible, not injected); agent context as ONE hidden
# additionalContext envelope on stdout (the primers' idiom, mirrors the
# user-prompt-submit branch below). Codex: the dispatcher captures each delegate
# 2>&1 and runs one json.loads, so a JSON envelope merged with a stray stderr
# line would surface literal JSON — emit plain text only and let the dispatcher
# re-wrap the whole card (Codex has no operator-visible SessionStart chat).
if [[ "$SOURCE" == "startup" || "$SOURCE" == "compact" || "$SOURCE" == "resume" ]]; then
  if [[ "${COS_AGENT:-}" == "codex" ]]; then
    _all="$SS_VISIBLE"
    _ss_append _all "$SS_HIDDEN"
    if [[ -n "$_all" ]]; then printf '%s\n' "$_all"; fi
  else
    if [[ -n "$SS_VISIBLE" ]]; then printf '%s\n' "$SS_VISIBLE" >&2; fi
    if [[ -n "$SS_HIDDEN" ]]; then
      printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":$(printf '%s' "$SS_HIDDEN" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"
    fi
  fi
fi

# On user-prompt-submit: emit a compact per-turn workflow state via the
# Claude Code hookSpecificOutput JSON format so the operator sees the
# system pulse on every prompt (active task, complexity gate, board WIP,
# session-id tail). Mirrors the caveman-mode-tracker.js pattern so the UI
# renders this as a compact labeled "additionalContext" block.
if [[ "$SOURCE" == "user-prompt-submit" ]]; then
  # Body lives in _session_pulse.sh — see that file's header for why.
  # shellcheck source=_session_pulse.sh
  source "${_COS_HOOKS_PHYS}/_session_pulse.sh" 2>/dev/null || exit 0
  cos_emit_session_pulse
fi

exit 0
