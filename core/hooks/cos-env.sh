#!/usr/bin/env bash
# Coding OS — Shared environment for hooks.
# Source this file at the top of every hook: source "$(dirname "$0")/cos-env.sh"
#
# Provides:
#   COS_STATE_DIR    — shared state directory root (default: .coding-os)
#                      Holds agent-agnostic artifacts: thinking-os.db, .hooks.log,
#                      .agent marker, .capture-errors.log, .dogfood-reminded,
#                      installed-manifest.json, domain-config.json.
#   COS_AGENT        — which agent runtime invoked this hook (claude|codex|cursor|unknown)
#   COS_AGENT_DIR    — agent-private state directory = $COS_STATE_DIR/$COS_AGENT
#                      Holds per-agent state: session-id, .task-current,
#                      .thinking-os-gate, .zoom-checkpoint, .doc-anchor,
#                      .memory-check, .active-skill.
#                      Two agents running against the same project write to
#                      different dirs and never collide.
#   COS_SESSION_FILE — path to session-id file (inside COS_AGENT_DIR)
#   COS_DB_PATH      — path to thinking-os SQLite DB (shared, in COS_STATE_DIR)
#   COS_HOOK_LOG     — path to the append-only hook activity log (shared,
#                      every line carries agent=X session=Y task=Z so downstream
#                      tools can filter by agent without a separate file)
#
# And the helper:
#   cos_log_hook HOOK_NAME [ACTION] [DETAIL]
#     Appends a line to $COS_HOOK_LOG so the user (or `cos hooks-log`) can
#     see live hook activity. Fail-open: never errors a hook even if the
#     write fails.

# Resolve from env, .coding-os.yaml, or defaults
COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"
# Cursor / Claude often run hook subprocesses with cwd != repo root. Default
# relative ".coding-os" would then create the wrong tree (and an empty log at
# the real project). Anchor to workspace when the IDE exports it.
case "${COS_STATE_DIR}" in
  .coding-os | ./.coding-os)
    if [[ -n "${CURSOR_PROJECT_DIR:-}" ]]; then
      COS_STATE_DIR="${CURSOR_PROJECT_DIR}/.coding-os"
    elif [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
      COS_STATE_DIR="${CLAUDE_PROJECT_DIR}/.coding-os"
    fi
    ;;
esac
COS_DB_PATH="${COS_DB_PATH:-${COS_STATE_DIR}/thinking-os.db}"
COS_HOOK_LOG="${COS_HOOK_LOG:-${COS_STATE_DIR}/.hooks.log}"

# Cap the log at 500 lines so `cos hooks-log` stays snappy and the file
# never blooms into a multi-MB artifact that would be tempting to open.
# Truncation runs when the file passes 2× the cap (=1000 lines) and keeps
# only the most recent $COS_HOOK_LOG_MAX_LINES.
COS_HOOK_LOG_MAX_LINES="${COS_HOOK_LOG_MAX_LINES:-500}"

# ---------------------------------------------------------------------------
# Agent runtime detection — which runtime invoked this hook?
# Priority: explicit COS_AGENT env > .coding-os/.agent (install marker) >
# Cursor (CURSOR_*) > Claude Code > Codex > unknown.
#
# Cursor sets CLAUDE_PROJECT_DIR as a workspace alias, so we MUST NOT treat
# CLAUDE_PROJECT_DIR alone as "Claude Code" — that mis-tags Cursor hooks.
# Must run BEFORE COS_AGENT_DIR / COS_SESSION_FILE are computed.
# ---------------------------------------------------------------------------
if [[ -z "${COS_AGENT:-}" ]]; then
  COS_AGENT=""
  # Prefer runtime-specific env markers over persisted .agent.
  # .agent is a fallback when the host runtime doesn't expose identity.
  if [[ -n "${CURSOR_PROJECT_DIR:-}" ]] || [[ -n "${CURSOR_VERSION:-}" ]]; then
    COS_AGENT="cursor"
  elif [[ -n "${CODEX_SESSION_ID:-}" ]] || [[ -n "${CODEX_AGENT_DIR:-}" ]] || [[ -n "${CODEX_HOME:-}" ]]; then
    COS_AGENT="codex"
  elif [[ -n "${CLAUDECODE:-}" ]] || [[ -n "${CLAUDE_CODE_SSE_PORT:-}" ]]; then
    COS_AGENT="claude"
  fi

  if [[ -z "${COS_AGENT:-}" ]] && [[ -f "${COS_STATE_DIR}/.agent" ]]; then
    COS_AGENT="$(head -c 32 "${COS_STATE_DIR}/.agent" 2>/dev/null | tr -d '[:space:]' || true)"
  fi

  # Last-resort Claude compatibility marker; Cursor also sets CLAUDE_PROJECT_DIR,
  # so only use this when no stronger signal existed.
  if [[ -z "${COS_AGENT:-}" ]] && [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
    COS_AGENT="claude"
  fi

  COS_AGENT="${COS_AGENT:-unknown}"
fi

# Agent-private state dir. Every per-session state file lives here so two
# agents attached to the same project never trample each other's state.
COS_AGENT_DIR="${COS_AGENT_DIR:-${COS_STATE_DIR}/${COS_AGENT}}"
COS_SESSION_FILE="${COS_AGENT_DIR}/session-id"

export COS_STATE_DIR COS_AGENT_DIR COS_SESSION_FILE COS_DB_PATH COS_HOOK_LOG COS_HOOK_LOG_MAX_LINES COS_AGENT

# ---------------------------------------------------------------------------
# Identity helpers — pure reads, cheap enough to call per hook invocation.
# ---------------------------------------------------------------------------
cos_current_session() {
  # Echo current session id or 'none' if not available. Fail-open.
  # Session-id format (agent-prefixed): ses-<agent>-YYYYMMDD-HHMMSS-xxxx
  if [[ -f "$COS_SESSION_FILE" ]]; then
    local raw
    raw="$(head -c 64 "$COS_SESSION_FILE" 2>/dev/null | tr -d '[:space:]' || true)"
    if [[ -n "$raw" ]]; then
      echo "$raw"
      return
    fi
  fi
  echo "none"
}

cos_current_task() {
  # Echo current task marker in agent-friendly form:
  #   1. If the marker contains a TASK-### token, return just that (e.g.,
  #      "TASK-043") so the agent can jump straight to docs/tasks/TASK-043-*.md.
  #   2. Else if the marker is a governance/docs-update/exploratory slug,
  #      return it truncated to 40 chars (keeps log lines readable).
  #   3. Else return 'none'.
  # File format: "<session_id> <task_name>" (single whitespace).
  local f="${COS_AGENT_DIR}/.task-current"
  if [[ ! -f "$f" ]]; then
    echo "none"
    return
  fi

  local line raw
  line="$(head -1 "$f" 2>/dev/null || true)"
  # Second whitespace-separated token onward is the task name.
  raw="$(echo "$line" | awk '{$1=""; sub(/^ /, ""); print}' 2>/dev/null || true)"
  if [[ -z "$raw" ]]; then
    echo "none"
    return
  fi

  # Prefer explicit TASK-### anywhere in the marker — shortest agent-useful form.
  local match
  match="$(echo "$raw" | grep -oE 'TASK-[0-9]+' | head -1 || true)"
  if [[ -n "$match" ]]; then
    echo "$match"
    return
  fi

  # Fallback: truncate long governance slugs so log lines stay readable.
  if [[ ${#raw} -gt 40 ]]; then
    echo "${raw:0:37}..."
  else
    echo "$raw"
  fi
}

# ---------------------------------------------------------------------------
# Hook activity logging — makes hook execution visible to the user.
# Format: [ISO-8601] [hook_name] [action] agent=X session=Y task=Z detail...
# Keeps human-readable shape so `grep`/`awk`/`tail -f` all still work; new
# identity fields are appended in front of the free-form detail so downstream
# filters (cos hooks-log --agent X) never need a JSON parser.
# ---------------------------------------------------------------------------
cos_log_hook() {
  local hook_name="${1:-unknown}"
  local action="${2:-fire}"
  shift 2 2>/dev/null || true
  local detail="$*"

  local ts agent session task model_bit
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  agent="${COS_AGENT:-unknown}"
  session="$(cos_current_session)"
  task="$(cos_current_task)"
  model_bit=""
  if [[ -n "${COS_HOOK_RUNTIME_MODEL:-}" ]]; then
    model_bit=" model=${COS_HOOK_RUNTIME_MODEL}"
  fi

  # Fail-open: never let a logging error abort the hook.
  {
    mkdir -p "$(dirname "$COS_HOOK_LOG")" 2>/dev/null
    if [[ -n "$detail" ]]; then
      echo "[${ts}] [${hook_name}] [${action}] agent=${agent} session=${session} task=${task}${model_bit} ${detail}" >> "$COS_HOOK_LOG"
    else
      echo "[${ts}] [${hook_name}] [${action}] agent=${agent} session=${session} task=${task}${model_bit}" >> "$COS_HOOK_LOG"
    fi

    # Opportunistic truncation — keep only last N lines when file grows past 2x cap.
    if [[ -f "$COS_HOOK_LOG" ]]; then
      local lines
      lines=$(wc -l < "$COS_HOOK_LOG" 2>/dev/null || echo 0)
      if [[ "$lines" -gt $((COS_HOOK_LOG_MAX_LINES * 2)) ]]; then
        tail -n "$COS_HOOK_LOG_MAX_LINES" "$COS_HOOK_LOG" > "${COS_HOOK_LOG}.tmp" \
          && mv "${COS_HOOK_LOG}.tmp" "$COS_HOOK_LOG"
      fi
    fi
  } 2>/dev/null || true
}
