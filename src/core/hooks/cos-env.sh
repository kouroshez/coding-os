#!/usr/bin/env bash
# Coding OS — Shared environment for hooks.
# Source this file at the top of every hook: source "$(dirname "$0")/cos-env.sh"
#
# Provides:
#   COS_STATE_DIR    — shared state directory root (default: .coding-os)
#                      Holds agent-agnostic artifacts: coding-os.db, .hooks.log,
#                      .agent marker, .capture-errors.log, .dogfood-reminded,
#                      installed-manifest.json, domain-config.json.
#   COS_AGENT        — which agent runtime invoked this hook (claude|codex|unknown)
#   COS_AGENT_DIR    — agent-private state directory = $COS_STATE_DIR/$COS_AGENT
#                      Holds per-agent state: session-id, .task-current,
#                      .thinking_os-gate, .zoom-checkpoint, .doc-anchor,
#                      .memory-check, .active-skill.
#                      Two agents running against the same project write to
#                      different dirs and never collide.
#   COS_SESSION_FILE — path to session-id file (inside COS_AGENT_DIR)
#   COS_DB_PATH      — path to the project's coding-os SQLite DB (shared, in COS_STATE_DIR)
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
# Claude often runs hook subprocesses with cwd != repo root. Default
# relative ".coding-os" would then create the wrong tree (and an empty log at
# the real project). Anchor to workspace when the IDE exports it.
case "${COS_STATE_DIR}" in
  .coding-os | ./.coding-os)
    if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
      COS_STATE_DIR="${CLAUDE_PROJECT_DIR}/.coding-os"
    fi
    ;;
esac
# Default DB filename is `coding-os.db`. Legacy `thinking_os.db` is auto-renamed
# by src/core/thinking_os/database.py::migrate_legacy_db_filename() on first init_db()
# call after the upgrade — no shell-side migration needed.
COS_DB_PATH="${COS_DB_PATH:-${COS_STATE_DIR}/coding-os.db}"
COS_HOOK_LOG="${COS_HOOK_LOG:-${COS_STATE_DIR}/.hooks.log}"
# Block-only durable log. The main log above is flooded by high-volume 'fire'
# lines and capped, so rare 'block' events are evicted within hours — long
# before learn_extract mines them (the hook-block lesson signal was being lost).
# This log only ever receives 'block' lines, so it retains them across the
# extraction window. Mined by learning._mine_hook_block_lessons.
COS_HOOK_BLOCK_LOG="${COS_HOOK_BLOCK_LOG:-${COS_STATE_DIR}/.hook-blocks.log}"

# ---------------------------------------------------------------------------
# Per-project hook override (TASK-256) — a disabled NON-safety hook self-skips
# for THIS project. `$COS_STATE_DIR/disabled-hook-scripts` (one script basename
# per line) is the derived allowlist written by cli.project_overrides, which
# NEVER lists a safety-category hook — so a safety hook can never be disabled.
# Guarded + fail-open: when the file is absent (the common case) this costs a
# single stat; any error continues normally. Skip == `exit 0` (this file is
# SOURCED, so the exit ends the calling hook before its body runs). Set
# COS_SKIP_OVERRIDE_CHECK=1 to bypass (used by non-hook sourcers / tests).
# ---------------------------------------------------------------------------
if [[ -z "${COS_SKIP_OVERRIDE_CHECK:-}" && -f "${COS_STATE_DIR}/disabled-hook-scripts" ]]; then
  _cos_self="$(basename "${BASH_SOURCE[1]:-${0:-}}" 2>/dev/null || echo "")"
  if [[ -n "$_cos_self" ]] \
       && grep -qxF -- "$_cos_self" "${COS_STATE_DIR}/disabled-hook-scripts" 2>/dev/null; then
    unset _cos_self
    exit 0
  fi
  unset _cos_self
fi

# Cap the log at 500 lines so `cos hooks-log` stays snappy and the file
# never blooms into a multi-MB artifact that would be tempting to open.
# Truncation runs when the file passes 2× the cap (=1000 lines) and keeps
# only the most recent $COS_HOOK_LOG_MAX_LINES.
COS_HOOK_LOG_MAX_LINES="${COS_HOOK_LOG_MAX_LINES:-500}"

# ---------------------------------------------------------------------------
# Agent runtime detection — which runtime invoked this hook?
# Priority: explicit COS_AGENT env > .coding-os/.agent (install marker) >
# Codex > Claude Code > unknown.
#
# Must run BEFORE COS_AGENT_DIR / COS_SESSION_FILE are computed.
#
# DRIFT WARNING: src/cli/board_commands.py::_detect_agent_runtime mirrors this
# same priority in Python for CLI-originated task transitions.  If you add
# a new marker here, add it there (and the matching test in
# tests/test_board_commands_agent_detect.py).
# ---------------------------------------------------------------------------
if [[ -z "${COS_AGENT:-}" ]]; then
  COS_AGENT=""
  # Prefer runtime-specific env markers over persisted .agent.
  # .agent is a fallback when the host runtime doesn't expose identity.
  #
  # Claude Code (VSCode/Antigravity variants) does NOT export CLAUDECODE=1
  # to hook processes — only CLAUDE_CODE_ENTRYPOINT and CLAUDE_AGENT_SDK_VERSION
  # make it through.  Treat those as authoritative claude signals, otherwise
  # hooks fired by Claude Code mis-tag themselves via the .agent fallback.
  if [[ -n "${CODEX_SESSION_ID:-}" ]] || [[ -n "${CODEX_AGENT_DIR:-}" ]] || [[ -n "${CODEX_HOME:-}" ]]; then
    COS_AGENT="codex"
  elif [[ -n "${CLAUDECODE:-}" ]] || [[ -n "${CLAUDE_CODE_SSE_PORT:-}" ]] \
       || [[ -n "${CLAUDE_CODE_ENTRYPOINT:-}" ]] \
       || [[ -n "${CLAUDE_AGENT_SDK_VERSION:-}" ]]; then
    COS_AGENT="claude"
  fi

  if [[ -z "${COS_AGENT:-}" ]] && [[ -f "${COS_STATE_DIR}/.agent" ]]; then
    COS_AGENT="$(head -c 32 "${COS_STATE_DIR}/.agent" 2>/dev/null | tr -d '[:space:]' || true)"
  fi

  # Last-resort Claude compatibility marker; only use this when no
  # stronger signal existed.
  if [[ -z "${COS_AGENT:-}" ]] && [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
    COS_AGENT="claude"
  fi

  COS_AGENT="${COS_AGENT:-unknown}"
fi

# Agent-private state dir. Every per-agent state file lives here so two
# DIFFERENT agents (e.g. Claude + Codex) attached to the same project never
# trample each other's state.
COS_AGENT_DIR="${COS_AGENT_DIR:-${COS_STATE_DIR}/${COS_AGENT}}"

# ---------------------------------------------------------------------------
# Panel identity — keys cognitive state per-PANEL of the SAME agent.
#
# Two panels of the same Claude/Codex instance on the same project
# share $COS_AGENT_DIR but get distinct $COS_PANEL_DIR subdirs so cognitive
# state files (.thinking_os-gate, .task-current, .active-skill, .doc-anchor,
# .memory-check, .zoom-checkpoint, .active-formula, .learn-suggestions and
# the dedupe markers) never collide.
#
# Resolution priority (highest first):
#   1. $COS_PANEL_ID env — explicit caller override (test harness, manual).
#   2. Adapter runtime stdin `session_id` — set later by
#      cos_panel_upgrade_from_payload(). cos-env.sh CANNOT consume stdin
#      itself (would steal it from the hook), so this slot is filled by
#      the hook after it reads stdin.
#   3. Adapter-runtime env vars — declared per adapter in
#      src/adapters/<id>/adapter.yaml::runtime_session_marker. Listed
#      below in fall-through order so any adapter that exports its
#      session id natively (Claude `CLAUDE_SESSION_ID`, Codex
#      `CODEX_SESSION_ID`) is picked up. A new
#      adapter adds its var here + to its adapter.yaml when it ships.
#   4. PPID-derived stable token — last resort. The hook's parent process
#      is the agent runtime process for THIS panel; PIDs differ across
#      panels of the same agent, so a hash over (PPID, agent) is a
#      panel-stable identifier in the absence of a richer signal.
# ---------------------------------------------------------------------------
_cos_resolve_panel_id() {
  local id="" v val ppid_val
  if [[ -n "${COS_PANEL_ID:-}" ]]; then
    printf '%s' "$COS_PANEL_ID"
    return
  fi
  # CLAUDE_CODE_SESSION_ID is the real var Claude Code exports to every hook
  # subprocess (stable per session, distinct per tab). It MUST lead — without
  # it the resolver fell through to the ppid fallback (#4), which is ephemeral
  # per tool call on Claude (fresh subprocess each fire) and scattered one
  # session's state across dozens of panels. Keep the bare CLAUDE_SESSION_ID
  # after it as a forward-compat alias. Stays in sync with each adapter.yaml
  # ::runtime_session_marker.env_vars (per-agent SSOT for the var name).
  # Real adapter session vars only (claude/codex) — matches the two
  # src/adapters/*/adapter.yaml::runtime_session_marker.env_vars. Speculative
  # GEMINI_*/ANTHROPIC_* removed: a future
  # adapter adds its var here + to its adapter.yaml when it actually ships.
  for v in CLAUDE_CODE_SESSION_ID CLAUDE_SESSION_ID CODEX_SESSION_ID; do
    val="$(printenv "$v" 2>/dev/null || true)"
    if [[ -n "$val" ]]; then
      id="$val"
      break
    fi
  done
  if [[ -z "$id" ]]; then
    ppid_val="${PPID:-$$}"
    if command -v shasum >/dev/null 2>&1; then
      id="ppid-$(printf 'p%s-%s' "$ppid_val" "${COS_AGENT:-unknown}" | shasum -a 1 | cut -c1-8)"
    else
      id="ppid-${ppid_val}"
    fi
  fi
  # FS-safe: keep [A-Za-z0-9._-] only, cap at 64 chars
  printf '%s' "$id" | tr -c 'A-Za-z0-9_.-' '-' | cut -c1-64
}
COS_PANEL_ID="${COS_PANEL_ID:-$(_cos_resolve_panel_id)}"
COS_PANEL_DIR="${COS_PANEL_DIR:-${COS_AGENT_DIR}/panels/${COS_PANEL_ID}}"
COS_SESSION_FILE="${COS_PANEL_DIR}/session-id"

# Classify how the panel id was derived so SessionStart can surface a collision
# risk (cheap, no side effects — the loud warning lives in session-context.sh).
# A ppid-* prefix means NO runtime session-id var was exported and we fell back
# to a PPID hash; two panels sharing a PPID would then collide on one panel dir.
case "$COS_PANEL_ID" in
  ppid-*) export COS_PANEL_ID_SOURCE="ppid" ;;
  *)      export COS_PANEL_ID_SOURCE="session" ;;
esac

# Per-panel state file allowlist (basenames). Single source of truth used by
# cos_state_path / write-state.sh / check-state.sh to route a write to the
# panel dir vs the shared per-agent dir. Adding a new per-panel marker:
# append its basename here; the writer/reader auto-route from then on.
#
# Explicitly NOT in this list (intentionally shared across panels of the
# same agent): .agent, .model, .swimlane, .last-verify*, .last-decay,
# .turn-activity.log, .overrides.json, .hooks.log, sessions/, traces/,
# locks/, heartbeat, coding-os.db. Rationale per file in
# docs/engineering/state-files.md.
# .task-mode and the discovery-debounce markers moved to per-panel — two
# panels of the same agent must not share banner verbosity or nudge debounce.
COS_PER_PANEL_FILES="${COS_PER_PANEL_FILES:-.thinking_os-gate .task-current .active-skill .doc-anchor .memory-check .zoom-checkpoint .active-formula .learn-suggestions .zoom-prompt-suggested .docs-first-nudged .roles-composed .roles .role .graph-call-seen .abandoned-task-warned .graph-empty-warning-shown .doc-anchor-override .memory-check-override .uv-heredoc-override .task-mode .last-discovery-reminder session-id}"

# Model signal for the routing / learning pipeline. Priority:
#   1. Caller already exported COS_AGENT_MODEL (test harness / explicit).
#   2. Agent runtime env — adapters expose their preferred model env so
#      consumer projects with different adapters share one resolver.
#   3. $COS_AGENT_DIR/.model — latest hook-stdin model snapshot (written
#      by session-context.sh when the agent sends `model` in the hook
#      payload).  This is the dynamic source of truth — Claude Code
#      rotates models mid-session and the hook payload carries the
#      current choice.
#   Everything falls back to empty (NULL) — routing_weights tolerates it.
if [[ -z "${COS_AGENT_MODEL:-}" ]]; then
  # printenv keeps this portable across bash / zsh (zsh lacks ${!var}).
  for _cand in CLAUDE_CODE_MODEL CODEX_MODEL ANTHROPIC_MODEL \
               OPENAI_MODEL; do
    _val="$(printenv "$_cand" 2>/dev/null || true)"
    if [[ -n "$_val" ]]; then
      COS_AGENT_MODEL="$_val"
      break
    fi
  done
  unset _cand _val
fi
if [[ -z "${COS_AGENT_MODEL:-}" ]] && [[ -f "${COS_AGENT_DIR}/.model" ]]; then
  COS_AGENT_MODEL="$(head -c 64 "${COS_AGENT_DIR}/.model" 2>/dev/null \
                     | tr -d '[:space:]' || true)"
fi
COS_AGENT_MODEL="${COS_AGENT_MODEL:-}"

# Hook latency SLI — stamp wall-clock entry time when the hook sources
# this file. cos_log_hook subtracts it to emit dt=<ms>, giving the hook layer
# a real per-invocation duration without a wrapper. $EPOCHREALTIME is bash 5+
# (seconds.microseconds, e.g. 1717545600.123456); we keep the raw string and
# do integer-µs math in cos_log_hook so there is no float/locale dependency.
COS_HOOK_T0="${COS_HOOK_T0:-${EPOCHREALTIME:-}}"

export COS_STATE_DIR COS_AGENT_DIR COS_PANEL_ID COS_PANEL_DIR COS_SESSION_FILE COS_DB_PATH COS_HOOK_LOG COS_HOOK_BLOCK_LOG COS_HOOK_LOG_MAX_LINES COS_AGENT COS_AGENT_MODEL COS_PER_PANEL_FILES COS_HOOK_T0

# Activity heartbeat — written on every hook invocation so GC can measure
# inactivity rather than session age. Per-panel so orphan GC can target
# dead panels' subdirs without disturbing live siblings.
mkdir -p "${COS_PANEL_DIR}" 2>/dev/null || true
date +%s > "${COS_PANEL_DIR}/heartbeat" 2>/dev/null || true

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
# Hook activity logging — makes hook execution visible to the user.
# Format: [ISO-8601] [hook_name] [action] agent=X session=Y task=Z detail...
# Keeps human-readable shape so `grep`/`awk`/`tail -f` all still work; new
# identity fields are appended in front of the free-form detail so downstream
# filters (cos hooks-log --agent X) never need a JSON parser.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# cos_record_activity <category> <detail> — append a per-turn activity entry
# ---------------------------------------------------------------------------
# Logs operator-visible side effects (memory capture, graph reindex, task
# sync, skill invoke, worklog) for the per-turn pulse. session-context.sh
# reads this file on the next UserPromptSubmit, summarizes, then truncates.
# Claude Code does NOT render PostToolUse stdout, so this aggregation is
# the only reliable way to surface PostToolUse activity in the chat UI.
# Fail-open: never aborts the parent hook on logging failure.
# ---------------------------------------------------------------------------
# _cos_helpers_dir — physical path to _helpers/, resolved through this file's
# own symlink chain. Consumers (and the meta-repo's own .claude/hooks/) symlink
# cos-env.sh but NOT _helpers/, so a $(dirname)-relative path lands in a dir
# with no helpers and the python fallbacks silently no-op — a fail-OPEN gap for
# cos_json_field. readlink to the real file's dir finds _helpers/. On demand.
# ---------------------------------------------------------------------------
_cos_helpers_dir() {
  local src dir
  src="${BASH_SOURCE[0]}"
  while [ -L "$src" ]; do
    dir="$(cd -P "$(dirname "$src")" && pwd)"
    src="$(readlink "$src")"
    [[ "$src" != /* ]] && src="${dir}/${src}"
  done
  printf '%s' "$(cd -P "$(dirname "$src")" && pwd)/_helpers"
}

# ---------------------------------------------------------------------------
cos_record_activity() {
  local category="${1:-}"
  local detail="${2:-}"
  [[ -z "$category" ]] && return 0
  [[ -z "${COS_AGENT_DIR:-}" ]] && return 0
  local log ts size
  log="$COS_AGENT_DIR/.turn-activity.log"
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo "")"
  {
    mkdir -p "$COS_AGENT_DIR" 2>/dev/null
    printf '%s\t%s\t%s\n' "$category" "$detail" "$ts" >> "$log"
  } 2>/dev/null || true
  # Opportunistic truncation — keep last 500 lines once the file exceeds 50 KB.
  size=$(stat -f%z "$log" 2>/dev/null || stat -c%s "$log" 2>/dev/null || echo 0)
  if [[ "$size" -gt 50000 ]]; then
    {
      tail -n 500 "$log" > "${log}.tmp" && mv "${log}.tmp" "$log"
    } 2>/dev/null || true
  fi
  return 0
}

# Elapsed wall-time (ms) since this hook sourced cos-env.sh. Pure integer-µs
# math on the two $EPOCHREALTIME strings (sec.usec) — no float, no locale,
# no awk. Echoes a non-negative integer; empty when T0 / now is unavailable
# (older bash without $EPOCHREALTIME) so the dt= field is simply omitted.
cos_hook_elapsed_ms() {
  local t0="${COS_HOOK_T0:-}" now="${EPOCHREALTIME:-}"
  [[ -z "$t0" || -z "$now" ]] && return 0
  # Split sec.usec; pad/truncate the fractional part to exactly 6 digits.
  local t0_s="${t0%%.*}" t0_f="${t0#*.}" now_s="${now%%.*}" now_f="${now#*.}"
  [[ "$t0_f" == "$t0" ]] && t0_f="0"
  [[ "$now_f" == "$now" ]] && now_f="0"
  t0_f="${t0_f}000000"; t0_f="${t0_f:0:6}"
  now_f="${now_f}000000"; now_f="${now_f:0:6}"
  # Strip leading zeros so bash does not read them as octal.
  local t0_us=$((10#$t0_s * 1000000 + 10#$t0_f))
  local now_us=$((10#$now_s * 1000000 + 10#$now_f))
  local dms=$(((now_us - t0_us) / 1000))
  ((dms < 0)) && dms=0
  printf '%s' "$dms"
}

cos_log_hook() {
  local hook_name="${1:-unknown}"
  local action="${2:-fire}"
  shift 2 2>/dev/null || true
  local detail="$*"

  local ts agent session task model_bit dt_bit
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  agent="${COS_AGENT:-unknown}"
  session="$(cos_current_session)"
  task="$(cos_current_task)"
  model_bit=""
  if [[ -n "${COS_HOOK_RUNTIME_MODEL:-}" ]]; then
    model_bit=" model=${COS_HOOK_RUNTIME_MODEL}"
  fi
  dt_bit=""
  local _dms
  _dms="$(cos_hook_elapsed_ms 2>/dev/null || true)"
  if [[ -n "$_dms" ]]; then
    dt_bit=" dt=${_dms}ms"
  fi

  # Fail-open: never let a logging error abort the hook.
  {
    mkdir -p "$(dirname "$COS_HOOK_LOG")" 2>/dev/null
    local log_line
    if [[ -n "$detail" ]]; then
      log_line="[${ts}] [${hook_name}] [${action}] agent=${agent} session=${session} task=${task}${model_bit}${dt_bit} ${detail}"
    else
      log_line="[${ts}] [${hook_name}] [${action}] agent=${agent} session=${session} task=${task}${model_bit}${dt_bit}"
    fi
    echo "$log_line" >> "$COS_HOOK_LOG"

    # Mirror 'block' lines into the block-only durable log so the high-volume
    # main log's cap can't evict them before learn_extract mines them.
    if [[ "$action" == "block" && -n "${COS_HOOK_BLOCK_LOG:-}" ]]; then
      echo "$log_line" >> "$COS_HOOK_BLOCK_LOG"
      local blk_lines
      blk_lines=$(wc -l < "$COS_HOOK_BLOCK_LOG" 2>/dev/null || echo 0)
      if [[ "$blk_lines" -gt $((COS_HOOK_LOG_MAX_LINES * 2)) ]]; then
        tail -n "$COS_HOOK_LOG_MAX_LINES" "$COS_HOOK_BLOCK_LOG" > "${COS_HOOK_BLOCK_LOG}.tmp" \
          && mv "${COS_HOOK_BLOCK_LOG}.tmp" "$COS_HOOK_BLOCK_LOG"
      fi
    fi

    # F8 (TASK-447): make a BLOCK durable in the SQLite log_events store the
    # logging_os sink owns so cos_log_query / error_sweep surface it — not just
    # the text logs above. Reuse the shared shell→DB writer (DB-only here).
    if [[ "$action" == "block" ]] && command -v python3 >/dev/null 2>&1; then
      local _db_helper
      _db_helper="$(_cos_helpers_dir)/cos_say_json.py"
      if [[ -f "$_db_helper" ]]; then
        python3 "$_db_helper" "$ts" "ERROR" "hook.${hook_name}" "${detail:-blocked}" \
          "action=block session=${session} task=${task}" >/dev/null 2>&1 || true
      fi
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


# ---------------------------------------------------------------------------
# cos_read_stdin_bounded — drain stdin with a hard timeout
#
# WHY
#   Hooks read JSON from stdin (PreToolUse / PostToolUse / Stop / etc.).
#   When invoked from a terminal (`bash hook.sh` for testing), stdin is
#   a tty and `cat` would block forever waiting for the user. perl's
#   alarm() gives us a portable stdin read with a hard ceiling — bash's
#   `read -t` doesn't slurp multi-line JSON, and `timeout(1)` is missing
#   on macOS by default. Also: when the agent runtime sends nothing, we
#   want to fall through to defaults rather than hang the hook.
#
# USAGE
#   INPUT="$(cos_read_stdin_bounded 2)"      # 2-second ceiling
#
# CONTRACT
#   - Returns whatever bytes arrived on stdin (possibly empty).
#   - On timeout: prints nothing, returns 0 (fail-open).
#   - When stdin is a tty: returns immediately with empty output.
# ---------------------------------------------------------------------------
cos_read_stdin_bounded() {
  local timeout_s="${1:-2}"
  if [[ -t 0 ]]; then
    return 0
  fi
  perl -e '
    my $timeout = shift // 2;
    eval {
      local $SIG{ALRM} = sub { die "cos_stdin_timeout\n" };
      alarm $timeout;
      local $/;
      my $data = <STDIN>;
      alarm 0;
      print $data if defined $data;
    };
    exit 0;
  ' "$timeout_s" 2>/dev/null || true
}


# ---------------------------------------------------------------------------
# cos_require_or_skip — fail-open when a required CLI binary is absent
#
# WHY
#   Hooks hard-depend on `jq` and `python3`. Fresh-clone or minimal-CI
#   runtimes may lack one. With `set -euo pipefail` a missing binary
#   would kill the hook (exit ≠ 0 → BLOCK from the agent's POV). This
#   helper logs a `skip reason=missing_dep` event and exits 0 so the
#   hook degrades gracefully.
#
# USAGE (top of hook, after sourcing cos-env.sh)
#   cos_require_or_skip jq block-secrets
#
# STRICT MODE
#   COS_STRICT_DEPS=1 makes missing deps exit 2 (block) instead of 0.
#   Opt-in for CI that demands a fully-set-up environment.
# ---------------------------------------------------------------------------
cos_require_or_skip() {
  local bin="$1"
  local hook_id="${2:-unknown-hook}"
  if command -v "$bin" >/dev/null 2>&1; then
    return 0
  fi
  cos_log_hook "$hook_id" "skip" "reason=missing_dep dep=$bin" 2>/dev/null || true
  if [[ "${COS_STRICT_DEPS:-0}" == "1" ]]; then
    echo "BLOCKED: hook $hook_id needs '$bin' on PATH (COS_STRICT_DEPS=1)" >&2
    exit 2
  fi
  exit 0
}


# ---------------------------------------------------------------------------
# cos_require_parser <hook_id> — fail-CLOSED dep guard for harm gates.
#
# WHY
#   An irreversible/integrity-harm gate (block-secrets, block-dangerous-
#   commands, ...) must be able to read its decision input. The old
#   `jq -r '...' || echo ""` returned empty when jq was missing → the gate
#   exited 0 (allow) and silently disabled itself. observability-eye I8:
#   a guard that cannot evaluate must DENY, not allow.
#
# CONTRACT
#   Run at the TOP of a harm gate, OUTSIDE command-substitution (so the
#   exit can actually block). Returns 0 when at least one JSON parser
#   (jq OR python3) is on PATH; otherwise captures + exit 2 (block).
#   python3 is a hard dep of coding-os, so the realistic degraded case
#   (jq absent) still passes — cos_json_field falls back to python3.
#
# ESCAPE
#   COS_ALLOW_MISSING_DEPS=1 lets a human bootstrap (install jq/python3)
#   when both are absent.
# ---------------------------------------------------------------------------
cos_require_parser() {
  local hook_id="${1:-unknown-hook}"
  if command -v jq >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1; then
    return 0
  fi
  if [[ "${COS_ALLOW_MISSING_DEPS:-0}" == "1" ]]; then
    cos_log_hook "$hook_id" "skip" "reason=no_parser_override" 2>/dev/null || true
    return 0
  fi
  cos_say error "hook.${hook_id}" "no JSON parser (jq/python3) on PATH — gate fails closed" 2>/dev/null || true
  cos_log_hook "$hook_id" "block" "rule=no-parser-fail-closed" 2>/dev/null || true
  echo "BLOCKED: $hook_id needs jq or python3 to evaluate safety — neither found. Install one, or set COS_ALLOW_MISSING_DEPS=1 to bootstrap." >&2
  exit 2
}


# ---------------------------------------------------------------------------
# cos_json_field <path...> — extract first non-empty string field from a hook
# JSON envelope read on stdin. jq fast-path, python3 fallback.
#
# Echoes the value (empty if the field is genuinely absent). Does NOT block
# on a missing parser — that is cos_require_parser's job, which must run
# outside command-substitution. Replaces the `jq -r '...' || echo ""` idiom
# whose empty-on-missing-jq result drove the harm-gate fail-open class.
#
# USAGE
#   TOOL=$(printf '%s' "$INPUT" | cos_json_field tool_name)
#   CONTENT=$(printf '%s' "$INPUT" | cos_json_field tool_input.new_string tool_input.content)
# ---------------------------------------------------------------------------
cos_json_field() {
  local input filter="" p
  input="$(cat)"
  if command -v jq >/dev/null 2>&1; then
    for p in "$@"; do
      [[ -n "$filter" ]] && filter+=" // "
      filter+=".${p}"
    done
    filter+=" // empty"
    printf '%s' "$input" | jq -r "$filter" 2>/dev/null || true
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf '%s' "$input" \
      | python3 "$(_cos_helpers_dir)/json_field.py" "$@" 2>/dev/null || true
    return 0
  fi
  return 0
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

# ---------------------------------------------------------------------------
# cos_say <level> <scope> <msg> [k=v ...] — shell parity for logging_os.
#
# Schema mirrors src/core/logging_os/ (docs/engineering/logging_os.md).
# Three renders auto-detected from env + isatty(stderr); fans out to stderr,
# $COS_LOG_FILE (always short text), and ${COS_LOG_FILE}.jsonl (always json).
# Fail-open: never aborts the parent hook on logging failure.
# ---------------------------------------------------------------------------
cos_say() {
  local level scope msg
  level="${1:-info}"
  scope="${2:-shell.unknown}"
  msg="${3:-}"
  shift 3 2>/dev/null || true
  level="$(echo "$level" | tr '[:lower:]' '[:upper:]')"
  local level_value=20
  case "$level" in
    DEBUG) level_value=10 ;;
    INFO)  level_value=20 ;;
    OK)    level_value=21 ;;
    WARN)  level_value=30 ;;
    ERROR) level_value=40 ;;
    FATAL) level_value=50 ;;
    *) level="INFO"; level_value=20 ;;
  esac

  local floor_name floor_value=20
  floor_name="$(echo "${COS_LOG_LEVEL:-info}" | tr '[:lower:]' '[:upper:]')"
  case "$floor_name" in
    DEBUG) floor_value=10 ;;
    INFO)  floor_value=20 ;;
    OK)    floor_value=21 ;;
    WARN)  floor_value=30 ;;
    ERROR) floor_value=40 ;;
    FATAL) floor_value=50 ;;
  esac
  # Per-sink flooring (TASK-473): the console floor (COS_LOG_LEVEL) gates the
  # human sinks (stderr/text/jsonl); the durable floor (COS_LOG_DB_MIN_LEVEL,
  # re-applied inside cos_say_json.py) gates the log_events row independently.
  # Short-circuit only when the event clears NEITHER floor — flooring at the
  # console level alone here dropped a WARN before the durable store saw it.
  local db_floor_name db_floor_value=30
  db_floor_name="$(echo "${COS_LOG_DB_MIN_LEVEL:-WARN}" | tr '[:lower:]' '[:upper:]')"
  case "$db_floor_name" in
    DEBUG) db_floor_value=10 ;;
    INFO)  db_floor_value=20 ;;
    OK)    db_floor_value=21 ;;
    WARN)  db_floor_value=30 ;;
    ERROR) db_floor_value=40 ;;
    FATAL) db_floor_value=50 ;;
  esac
  local min_floor="$floor_value"
  [[ "$db_floor_value" -lt "$min_floor" ]] && min_floor="$db_floor_value"
  if [[ "$level_value" -lt "$min_floor" ]]; then
    return 0
  fi
  local below_console=0
  [[ "$level_value" -lt "$floor_value" ]] && below_console=1

  local kv=""
  if [[ $# -gt 0 ]]; then
    kv="$*"
  fi

  local mode
  if [[ "${COS_LOG_JSON:-}" == "1" ]]; then
    mode="json"
  elif [[ "${COS_LOG_FORCE_PRETTY:-}" == "1" ]]; then
    mode="pretty"
  elif [[ -n "${NO_COLOR:-}" ]]; then
    mode="short"
  elif [[ -t 2 ]]; then
    mode="pretty"
  else
    mode="short"
  fi

  local ts_iso ts_short
  ts_iso="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "")"
  ts_short="$(date -u +%H:%M:%S 2>/dev/null || echo "")"

  local emoji="" color="" reset=""
  case "$level" in
    DEBUG) emoji="🔍 "; color=$'\e[90m' ;;
    INFO)  emoji="ℹ️  "; color=$'\e[36m' ;;
    OK)    emoji="✅"; color=$'\e[32m' ;;
    WARN)  emoji="⚠️  "; color=$'\e[33m' ;;
    ERROR) emoji="❌"; color=$'\e[31m' ;;
    FATAL) emoji="💀"; color=$'\e[1;31m' ;;
  esac
  reset=$'\e[0m'

  local level_padded
  level_padded="$(printf '%-5s' "$level")"
  local short_line="${ts_short} ${level_padded} ${scope} ${msg}"
  [[ -n "$kv" ]] && short_line="${short_line} ${kv}"

  local helper
  helper="$(_cos_helpers_dir)/cos_say_json.py"
  local json_line=""
  if command -v python3 >/dev/null 2>&1 && [[ -f "$helper" ]]; then
    json_line="$(python3 "$helper" "$ts_iso" "$level" "$scope" "$msg" "$kv" 2>/dev/null || true)"
  fi

  local stderr_line
  case "$mode" in
    pretty)
      local pad
      pad="$(printf '%-20s' "$scope")"
      stderr_line="${emoji}  ${ts_short}  ${color}${level_padded}${reset}  ${pad}  ${msg}"
      [[ -n "$kv" ]] && stderr_line="${stderr_line}  ${kv}"
      ;;
    json)
      stderr_line="${json_line:-$short_line}"
      ;;
    *)
      stderr_line="$short_line"
      ;;
  esac

  # Human sinks respect the console floor; the durable log_events row was already
  # written above by cos_say_json.py (gated by COS_LOG_DB_MIN_LEVEL) (TASK-473).
  if [[ "$below_console" -eq 0 ]]; then
    printf '%s\n' "$stderr_line" >&2 2>/dev/null || true
  fi

  local log_file="${COS_LOG_FILE:-${COS_STATE_DIR}/.cos.log}"
  if [[ "$below_console" -eq 0 ]]; then
    {
      mkdir -p "$(dirname "$log_file")" 2>/dev/null
      printf '%s\n' "$short_line" >> "$log_file"
    } 2>/dev/null || true

    if [[ -n "$json_line" ]]; then
      {
        printf '%s\n' "$json_line" >> "${log_file}.jsonl"
      } 2>/dev/null || true
    fi
  fi

  return 0
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
