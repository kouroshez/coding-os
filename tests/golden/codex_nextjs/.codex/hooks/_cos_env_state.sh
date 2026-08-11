#!/usr/bin/env bash
# Coding OS - Session, task and per-panel state file access.
# Sourced by cos-env.sh from its own resolved directory; never run
# directly and never sourced by a hook.

# ---------------------------------------------------------------------------
# Identity helpers — pure reads, cheap enough to call per hook invocation.
# ---------------------------------------------------------------------------
cos_current_session() {
  # Echo current session id or 'none' if not available. Fail-open.
  # Read STRICTLY from panel-private session-id (no AGENT_DIR fallback —
  # cross-panel leak protection: a different panel's session-id parked
  # at $COS_AGENT_DIR/session-id must not become "ours"). When no panel
  # session-id file exists yet, fall back to $COS_PANEL_ID so write-
  # state.sh can still stamp ownership.
  local raw
  if [[ -f "$COS_SESSION_FILE" ]]; then
    raw="$(head -c 64 "$COS_SESSION_FILE" 2>/dev/null | tr -d '[:space:]' || true)"
    if [[ -n "$raw" ]]; then
      echo "$raw"
      return
    fi
  fi
  if [[ -n "${COS_PANEL_ID:-}" ]]; then
    echo "$COS_PANEL_ID"
    return
  fi
  echo "none"
}

cos_current_task() {
  # Echo current task marker in agent-friendly form:
  #   1. If the marker contains a TASK-### token, return just that (e.g.,
  #      "TASK-NNN") so the agent can jump straight to docs/tasks/TASK-NNN-*.md.
  #   2. Else if the marker is a governance/docs-update/exploratory slug,
  #      return it truncated to 40 chars (keeps log lines readable).
  #   3. Else return 'none'.
  # File format: "<session_id> <task_name>" (single whitespace).
  # STRICTLY panel-scoped — never read AGENT_DIR fossil (cross-panel leak).
  local f="${COS_PANEL_DIR}/.task-current"
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
  match="$(echo "$raw" | grep -oE 'TASK-([A-Z][A-Z0-9]*-)?[0-9]+' | head -1 || true)"
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
# cos_sanity_check — verify project state before a hook does real work
#
# WHY
#   Hooks assume the coding-os layout: $COS_STATE_DIR exists, the project
#   has docs/ and core/, etc. When a hook fires in an unconfigured project
#   (fresh clone, mid-cos-init, accidentally-running-elsewhere) the bare
#   jq/python invocations emit cryptic errors. This helper centralises the
#   "is the world sane?" probe so individual hooks can fail-open cleanly.
#
# USAGE
#   cos_sanity_check <hook_id> [check1 check2 ...]
#     - returns 0 if all named checks pass.
#     - on failure: logs "skip reason=sanity_<check>" and exits 0 (fail-open).
#
# CHECKS
#   state_dir   — $COS_STATE_DIR exists and is writable.
#   agent_dir   — $COS_AGENT_DIR exists.
#   db          — $COS_DB_PATH exists.
#   tasks_dir   — docs/tasks/ exists relative to project root.
#   board_os    — src/core/board_os/ exists.
#   git         — .git/ exists somewhere up the tree.
#
# Default check set when no args: state_dir.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# cos_one_shot_override — unified one-shot bypass for blocking hooks
#
# WHY
#   Several hooks (block-hardcoded-literals, block-uv-heredoc,
#   enforce-doc-anchor, enforce-memory-check, enforce-template) historically
#   consumed their own bypass dotfile in different directories with
#   different name prefixes. That made overrides:
#     - hard to discover (no central list of what bypasses are active)
#     - impossible to audit (no trail of who/when/why)
#     - error-prone (touching the wrong path silently fails)
#
# UNIFIED MODEL
#   Single JSON registry: $COS_STATE_DIR/.overrides.json
#     {
#       "doc-anchor": {"reason": "spike", "ts": 1714234567, "agent": "claude"},
#       "memory-check": {...}
#     }
#   Audit trail (append-only): $COS_STATE_DIR/.overrides.audit.log
#
# CONTRACT
#   cos_one_shot_override <key>  → returns 0 if override found and consumed,
#                                  1 otherwise. On hit, appends to audit log
#                                  and removes the entry from the registry
#                                  (or deletes the legacy dotfile).
#
# BACK-COMPAT
#   Legacy paths remain consulted so existing tooling and docs keep working:
#     $COS_AGENT_DIR/.<key>-override
#     $COS_STATE_DIR/.<key>-override   (literals only, historic)
#   When a legacy file is found, it is consumed identically. New writes
#   should prefer the unified registry, but legacy is permanently supported.
#
# SETTING AN OVERRIDE
#   echo '{"doc-anchor": {"reason": "spike-XYZ"}}' > $COS_STATE_DIR/.overrides.json
#   (or simply: touch $COS_AGENT_DIR/.doc-anchor-override)
# ---------------------------------------------------------------------------
cos_one_shot_override() {
  local key="${1:-}"
  [[ -z "$key" ]] && return 1
  local reg="$COS_STATE_DIR/.overrides.json"
  local audit="$COS_STATE_DIR/.overrides.audit.log"
  local legacy_agent="$COS_AGENT_DIR/.${key}-override"
  local legacy_shared="$COS_STATE_DIR/.${key}-override"
  local ts
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

  _audit() {
    {
      mkdir -p "$(dirname "$audit")" 2>/dev/null
      echo "[${ts}] consumed key=${key} agent=${COS_AGENT:-unknown} source=$1" >> "$audit"
    } 2>/dev/null || true
  }

  local consume_helper
  consume_helper="$(_cos_helpers_dir)/consume_override.py"
  if [[ -f "$reg" ]] && command -v python3 >/dev/null 2>&1 && [[ -f "$consume_helper" ]]; then
    if python3 "$consume_helper" "$reg" "$key" >/dev/null 2>&1; then
      _audit "registry"
      return 0
    fi
  fi

  # 2. Legacy per-agent dotfile.
  if [[ -f "$legacy_agent" ]]; then
    rm -f "$legacy_agent" 2>/dev/null || true
    _audit "legacy_agent"
    return 0
  fi

  # 3. Legacy shared dotfile (historic literals path).
  if [[ -f "$legacy_shared" ]]; then
    rm -f "$legacy_shared" 2>/dev/null || true
    _audit "legacy_shared"
    return 0
  fi

  return 1
}

cos_sanity_check() {
  local hook_id="${1:-unknown-hook}"
  shift 2>/dev/null || true
  local checks=("$@")
  if [[ ${#checks[@]} -eq 0 ]]; then
    checks=(state_dir)
  fi

  local check fail
  for check in "${checks[@]}"; do
    fail=""
    case "$check" in
      state_dir)
        [[ -d "$COS_STATE_DIR" ]] || fail="state_dir_missing"
        ;;
      agent_dir)
        [[ -d "$COS_AGENT_DIR" ]] || fail="agent_dir_missing"
        ;;
      db)
        [[ -f "$COS_DB_PATH" ]] || fail="db_missing"
        ;;
      tasks_dir)
        [[ -d "${CLAUDE_PROJECT_DIR:-.}/docs/tasks" ]] \
          || [[ -d "./docs/tasks" ]] \
          || fail="tasks_dir_missing"
        ;;
      board_os)
        [[ -d "${CLAUDE_PROJECT_DIR:-.}/src/core/board_os" ]] \
          || [[ -d "${CLAUDE_PROJECT_DIR:-.}/core/board_os" ]] \
          || [[ -d "./src/core/board_os" ]] \
          || [[ -d "./core/board_os" ]] \
          || fail="board_os_missing"
        ;;
      git)
        local d
        d="$(pwd)"
        local found=0
        while [[ "$d" != "/" ]]; do
          [[ -d "$d/.git" ]] && { found=1; break; }
          d="$(dirname "$d")"
        done
        [[ "$found" -eq 1 ]] || fail="git_missing"
        ;;
      *)
        fail="unknown_check_${check}"
        ;;
    esac
    if [[ -n "$fail" ]]; then
      cos_log_hook "$hook_id" "skip" "reason=sanity_${fail}" 2>/dev/null || true
      exit 0
    fi
  done
  return 0
}

# ---------------------------------------------------------------------------
# cos_state_path <basename-or-path>
#
# Single-source-of-truth path resolver for state files. Centralises the
# per-panel / per-agent routing decision so write-state.sh and check-state.sh
# (and any future state-touching hook) never re-implement the allowlist
# inline. Behavior:
#
#   - bare basename ".thinking_os-gate" and basename is in
#     $COS_PER_PANEL_FILES → returns "$COS_PANEL_DIR/.thinking_os-gate"
#   - bare basename ".task-mode" (not in allowlist) → returns
#     "$COS_AGENT_DIR/.task-mode"
#   - path already containing a slash (absolute or relative): if its
#     basename is in the per-panel allowlist AND the parent dir resolves
#     to $COS_AGENT_DIR, redirect to $COS_PANEL_DIR. Otherwise return as
#     given (back-compat for callers that pass shared-dir paths like
#     "$COS_STATE_DIR/.capture-errors.log").
# ---------------------------------------------------------------------------
cos_state_path() {
  local arg="${1:?Usage: cos_state_path <basename-or-path>}"
  local base parent
  base="$(basename "$arg")"
  case " $COS_PER_PANEL_FILES " in
    *" $base "*)
      if [[ "$arg" == */* ]]; then
        parent="$(cd "$(dirname "$arg")" 2>/dev/null && pwd || dirname "$arg")"
        local agent_real
        agent_real="$(cd "$COS_AGENT_DIR" 2>/dev/null && pwd || echo "$COS_AGENT_DIR")"
        if [[ "$parent" == "$agent_real" ]]; then
          printf '%s/%s' "$COS_PANEL_DIR" "$base"
          return
        fi
        printf '%s' "$arg"
        return
      fi
      printf '%s/%s' "$COS_PANEL_DIR" "$base"
      ;;
    *)
      if [[ "$arg" == /* ]] || [[ "$arg" == */* ]]; then
        printf '%s' "$arg"
      else
        printf '%s/%s' "$COS_AGENT_DIR" "$arg"
      fi
      ;;
  esac
}

# ---------------------------------------------------------------------------
# cos_panel_upgrade_from_payload <json-payload>
#
# Hook helper. After a hook reads stdin via cos_read_stdin_bounded, call
# this with the payload to upgrade $COS_PANEL_ID from the agent runtime's
# stdin session_id field — strongest panel signal available. Idempotent;
# no-op when the payload lacks session_id, jq is missing, or the id is
# already current.
#
# Why a separate helper instead of consuming stdin in cos-env.sh: stdin is
# one-shot. cos-env.sh runs at hook source-time, before the hook itself
# reads stdin. Stealing stdin from cos-env would break every hook.
# ---------------------------------------------------------------------------
cos_panel_upgrade_from_payload() {
  local payload="${1:-}"
  [[ -z "$payload" ]] && return 0
  command -v jq >/dev/null 2>&1 || return 0
  local sid
  sid="$(printf '%s' "$payload" | jq -r '.session_id // .sessionId // empty' 2>/dev/null || true)"
  [[ -z "$sid" ]] && return 0
  sid="$(printf '%s' "$sid" | tr -c 'A-Za-z0-9_.-' '-' | cut -c1-64)"
  [[ -z "$sid" ]] && return 0
  if [[ "$COS_PANEL_ID" != "$sid" ]]; then
    COS_PANEL_ID="$sid"
    COS_PANEL_DIR="${COS_AGENT_DIR}/panels/${COS_PANEL_ID}"
    COS_SESSION_FILE="${COS_PANEL_DIR}/session-id"
    export COS_PANEL_ID COS_PANEL_DIR COS_SESSION_FILE
    mkdir -p "$COS_PANEL_DIR" 2>/dev/null || true
  fi
  # Initialize the panel session-id file when missing. Without this, every
  # reader that goes through $COS_SESSION_FILE (the SSOT for "who am I")
  # sees an empty value, and the per-session ownership check rejects every
  # state file as un-owned — the cascade that surfaces as banner ses=? ·
  # task=none · gate=unset on hooks that only have agent-level legacy
  # state. SessionStart:startup writes a `ses-<agent>-<ts>-<rand>` id; for
  # resume/compact/user-prompt-submit (where startup never fires for this
  # panel), we mirror the agent-level session-id when present, else seed
  # with the panel id (stable across the conversation).
  if [[ ! -s "$COS_SESSION_FILE" ]]; then
    local seed=""
    if [[ -s "${COS_AGENT_DIR}/session-id" ]]; then
      seed="$(tr -d '\n\r' < "${COS_AGENT_DIR}/session-id" 2>/dev/null || true)"
    fi
    [[ -z "$seed" ]] && seed="ses-${COS_AGENT}-${COS_PANEL_ID}"
    local _tmp="${COS_SESSION_FILE}.tmp.$$"
    printf '%s\n' "$seed" > "$_tmp" 2>/dev/null \
      && mv -f "$_tmp" "$COS_SESSION_FILE" 2>/dev/null \
      || rm -f "$_tmp" 2>/dev/null
  fi
}

# ---------------------------------------------------------------------------
# cos_task_bound_in_live_sibling <task-id>
#
# rc 0 when ANOTHER panel of this agent binds <task-id> via its .task-current
# (last whitespace field — write-state.sh prefixes a session id) AND that
# panel's heartbeat is fresh. A task actively driven in a sibling panel is
# not stranded: nudging an idle panel about it invites a "rescue" park of
# live work (the phantom NULL-reason in_progress→icebox reverts).
# ---------------------------------------------------------------------------
cos_task_bound_in_live_sibling() {
  local task="${1:-}" pd ptask hb now
  [[ -n "$task" && -d "${COS_AGENT_DIR:-}/panels" ]] || return 1
  now=$(date +%s)
  for pd in "${COS_AGENT_DIR}/panels"/*/; do
    [[ -d "$pd" ]] || continue
    [[ "${pd%/}" == "${COS_PANEL_DIR:-}" ]] && continue
    ptask="$(awk '{print $NF}' "${pd}.task-current" 2>/dev/null | head -1 || true)"
    [[ "$ptask" == "$task" ]] || continue
    hb=$(stat -c %Y "${pd}heartbeat" 2>/dev/null || stat -f %m "${pd}heartbeat" 2>/dev/null || echo 0)
    if [[ "$hb" -gt 0 && $((now - hb)) -lt "${COS_SIBLING_BIND_TTL:-3600}" ]]; then
      return 0
    fi
  done
  return 1
}
