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

# ---------------------------------------------------------------------------
# Resolve this file's REAL directory and source the function leaves.
#
# ${BASH_SOURCE[0]} is the symlink a consumer project holds in .claude/hooks/;
# walking it back to the meta-repo means the leaves are found next to the real
# file and reach every consumer the moment core changes - no `cos update`
# needed, which is what makes splitting a live-symlinked hook safe. Same walk
# as _cos_helpers_dir(), inlined because that helper now lives in a leaf.
# ---------------------------------------------------------------------------
_cos_env_src="${BASH_SOURCE[0]}"
while [ -L "$_cos_env_src" ]; do
  _cos_env_dir="$(cd -P "$(dirname "$_cos_env_src")" && pwd)"
  _cos_env_src="$(readlink "$_cos_env_src")"
  [[ "$_cos_env_src" != /* ]] && _cos_env_src="${_cos_env_dir}/${_cos_env_src}"
done
_cos_env_dir="$(cd -P "$(dirname "$_cos_env_src")" && pwd)"
for _cos_env_part in _cos_env_paths _cos_env_log _cos_env_io _cos_env_state; do
  # shellcheck source=/dev/null
  source "${_cos_env_dir}/${_cos_env_part}.sh"
done
unset _cos_env_src _cos_env_dir _cos_env_part


# Resolve $COS_STATE_DIR. Precedence (applied ONLY while it is the bare default):
#   1. explicit non-default COS_STATE_DIR → verbatim
#   2. $CLAUDE_PROJECT_DIR                 → $CLAUDE_PROJECT_DIR/.coding-os
#   3. $COS_PROJECT_ROOT                   → $COS_PROJECT_ROOT/.coding-os
#   4. upward marker-walk from $PWD        → <root>/.coding-os
#   5. nothing found                       → relative .coding-os (legacy)
# Why a walk: hooks often run with cwd != repo root (e.g. `cd src/backend &&
# go build`); a bare relative ".coding-os" then lazily creates a STRAY
# .coding-os/ at the subdir (the nested-.coding-os bug). CLAUDE_PROJECT_DIR is
# unset under the VSCode native extension, so steps 3-4 are the runtime-
# independent fix. SPEC: docs/engineering/state-files.md § Project-root resolution.
COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"


case "${COS_STATE_DIR}" in
  .coding-os | ./.coding-os)
    if [[ -n "${CLAUDE_PROJECT_DIR:-}" ]]; then
      COS_STATE_DIR="${CLAUDE_PROJECT_DIR}/.coding-os"
    elif [[ -n "${COS_PROJECT_ROOT:-}" ]]; then
      COS_STATE_DIR="${COS_PROJECT_ROOT}/.coding-os"
    else
      _cos_root="$(_cos_find_project_root)"
      if [[ -n "$_cos_root" ]]; then
        COS_STATE_DIR="${_cos_root}/.coding-os"
      fi
      unset _cos_root
    fi
    ;;
esac

# ---------------------------------------------------------------------------
# Worktree state routing + misroute guard ( / pr-mode). A command
# inside a git worktree under ~/.coding-os/worktrees/ must resolve state to the
# MAIN repo, so every worktree of one repo shares its $COS_STATE_DIR (DB, board,
# presence, the test-governor .test-run.lock). Runs AFTER the case so it also
# corrects an INHERITED hub COS_STATE_DIR (e.g. a command spawned under
# `cos hub`, whose env carries COS_STATE_DIR=$HOME/.coding-os). Cheap raw-string
# gate first — only worktree cwds pay the resolution cost; the happy path
# (COS_PROJECT_ROOT exported by the cos pr dispatch) never spawns git.
# SPEC: docs/playbooks/pr-workflow.md § 3.
# ---------------------------------------------------------------------------
_cos_in_wt=""
case "${PWD}" in
  *"/.coding-os/worktrees/"*) _cos_in_wt=1 ;;
esac
if [[ -z "$_cos_in_wt" && -n "${COS_WORKTREE_ROOT:-}" && "${PWD}" == "${COS_WORKTREE_ROOT}"/* ]]; then
  _cos_in_wt=1
fi
# Catches a custom-location worktree the raw-string gates miss. Short-circuit ONLY
# on COS_PROJECT_ROOT (the authoritative fast-path) — the old CLAUDE_PROJECT_DIR
# arm gated this OFF for every Claude Code hook, exactly when the probe is needed,
# so a custom-location worktree misrouted state into itself (stray .coding-os in
# the agent's PR). Trunk fast-path preserved by a cheap `.git`-FILE pre-check: a
# linked worktree's root has `.git` as a file (gitdir pointer), a normal repo has
# it as a directory — only the former forks git below. (pr-workflow.md § 3.)
if [[ -z "$_cos_in_wt" && -z "${COS_PROJECT_ROOT:-}" ]] && _cos_has_dotgit_file; then
  _cos_wt_main="$(_cos_main_repo_from_worktree)"
  if [[ -n "$_cos_wt_main" ]]; then
    _cos_wt_top="$(git rev-parse --show-toplevel 2>/dev/null)" || _cos_wt_top=""
    if [[ -n "$_cos_wt_top" ]]; then
      _cos_wt_top="$(cd -P "$_cos_wt_top" 2>/dev/null && pwd -P)" || _cos_wt_top=""
    fi
    if [[ -n "$_cos_wt_top" && "$_cos_wt_top" != "$_cos_wt_main" ]]; then
      _cos_in_wt=1
    fi
  fi
  unset _cos_wt_main _cos_wt_top
fi
if [[ -n "$_cos_in_wt" ]]; then
  # In a worktree the project root is unambiguously the MAIN repo. COS_PROJECT_ROOT
  # is authoritative and beats whatever the case produced (CLAUDE_PROJECT_DIR or
  # the walk can point at the worktree itself or the global hub).
  _cos_main=""
  if [[ -n "${COS_PROJECT_ROOT:-}" ]]; then
    _cos_main="${COS_PROJECT_ROOT}"
  else
    _cos_main="$(_cos_main_repo_from_worktree)"
  fi
  if [[ -n "$_cos_main" && -d "${_cos_main}/.coding-os" ]]; then
    COS_STATE_DIR="${_cos_main}/.coding-os"
  else
    # main unresolvable: steer to a per-worktree QUARANTINE, never the global hub
    # ($HOME/.coding-os) — binding there made every misrouted worktree share the
    # hub's own state (DB/board/presence/locks) and collide with it and each other
    # ( regression of 1f8869b5). Also never a worktree-relative.coding-os —
    # that stray gets committed into the agent's PR. The quarantine sits
    # OFF the hub root and outside the checkout, keyed per worktree path; the
    # misroute flag still fires so the operator sees the misconfig.
    export COS_STATE_MISROUTE=1
    printf 'cos-env: worktree state misroute — main repo unresolvable from %s; export COS_PROJECT_ROOT=<main-repo> for worktree commands (docs/playbooks/pr-workflow.md § 3).\n' "$PWD" >&2
    _cos_home_real="$(cd -P "${HOME:-/dev/null}" 2>/dev/null && pwd -P)" || _cos_home_real="${HOME:-}"
    if [[ -n "$_cos_home_real" ]]; then
      _cos_wt_tag="$(printf '%s' "$PWD" | cksum 2>/dev/null | cut -d' ' -f1 2>/dev/null || true)"
      COS_STATE_DIR="${_cos_home_real}/.coding-os-misrouted/${_cos_wt_tag:-orphan}"
      unset _cos_wt_tag
    fi
    unset _cos_home_real
  fi
  unset _cos_main
fi
unset _cos_in_wt

if [[ -f "${COS_STATE_DIR}/hub-settings.json" ]] \
     && grep -q '"git_settings"' "${COS_STATE_DIR}/hub-settings.json" 2>/dev/null; then
  # jq fast-path, python3 fallback — a host WITHOUT jq must still honor an
  # enabled project (the old `command -v jq` precondition silently downgraded
  # it to trunk). Both emit one tab-separated line: enabled\tintegration\t
  # protected(csv)\tautonomy. python3 is a hard dep of coding-os.
  if command -v jq >/dev/null 2>&1; then
    _cos_git_line="$(jq -r '[(.git_settings.enabled // false), (.git_settings.integration_branch // "main"), ((.git_settings.protected_branches // ["production"]) | join(",")), (.git_settings.autonomy_level // "draft")] | @tsv' "${COS_STATE_DIR}/hub-settings.json" 2>/dev/null || true)"
  elif command -v python3 >/dev/null 2>&1; then
    _cos_git_line="$(python3 "$(_cos_helpers_dir)/git_settings_fields.py" "${COS_STATE_DIR}/hub-settings.json" 2>/dev/null || true)"
  else
    _cos_git_line=""
  fi
  _cos_git_enabled="$(printf '%s' "$_cos_git_line" | cut -f1)"
  if [[ -z "${COS_GIT_WORKFLOW:-}" && "$_cos_git_enabled" == "true" ]]; then
    # Split declare/assign so shellcheck SC2155 stays clean (return-value masking).
    COS_GIT_INTEGRATION_BRANCH="$(printf '%s' "$_cos_git_line" | cut -f2)"
    COS_GIT_PROTECTED_BRANCHES="$(printf '%s' "$_cos_git_line" | cut -f3)"
    COS_GIT_AUTONOMY="$(printf '%s' "$_cos_git_line" | cut -f4)"
    export COS_GIT_WORKFLOW="pr" COS_GIT_INTEGRATION_BRANCH COS_GIT_PROTECTED_BRANCHES COS_GIT_AUTONOMY
  elif [[ -z "${COS_GIT_WORKFLOW:-}" && -z "$_cos_git_line" ]]; then
    # grep matched the git_settings key but no parser could read it (corrupt/torn
    # JSON, or neither jq nor python3). The file EXISTS and names git_settings, so
    # the operator opted into pr-mode; a torn write must NOT silently re-enable
    # trunk (where a direct push to main is legal). Fail CLOSED to pr-mode — the
    # stricter posture — with safe-default policy, and warn once.
    COS_GIT_INTEGRATION_BRANCH="${COS_GIT_INTEGRATION_BRANCH:-main}"
    COS_GIT_PROTECTED_BRANCHES="${COS_GIT_PROTECTED_BRANCHES:-production}"
    COS_GIT_AUTONOMY="${COS_GIT_AUTONOMY:-draft}"
    export COS_GIT_WORKFLOW="pr" COS_GIT_INTEGRATION_BRANCH COS_GIT_PROTECTED_BRANCHES COS_GIT_AUTONOMY
    _cos_git_warn_once "unreadable" \
      "cos-env: git_settings present but hub-settings.json could not be parsed — failing CLOSED to pr-mode (stricter). Fix the file or install jq/python3 to restore the chosen mode. (docs/playbooks/pr-workflow.md § 1)"
  elif [[ "${COS_GIT_WORKFLOW:-}" == "trunk" && "$_cos_git_enabled" == "true" ]]; then
    # An inherited explicit COS_GIT_WORKFLOW=trunk wins over the file by design;
    # surface the self-downgrade of the Hub policy instead of applying it silently.
    _cos_git_warn_once "divergence" \
      "cos-env: git_settings enables pr-mode but an inherited COS_GIT_WORKFLOW=trunk overrides it — running TRUNK. Unset COS_GIT_WORKFLOW to honor the Hub setting. (docs/playbooks/pr-workflow.md § 1)"
  fi
  unset _cos_git_line _cos_git_enabled
fi

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
# Per-project hook override — a disabled NON-safety hook self-skips
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
COS_PER_PANEL_FILES="${COS_PER_PANEL_FILES:-.thinking_os-gate .task-current .active-skill .doc-anchor .memory-check .zoom-checkpoint .active-formula .learn-suggestions .zoom-prompt-suggested .docs-first-nudged .roles-composed .roles .role .graph-call-seen .abandoned-task-warned .graph-empty-warning-shown .doc-anchor-override .memory-check-override .uv-heredoc-override .task-mode .last-discovery-reminder .humanizer-audit session-id}"

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


