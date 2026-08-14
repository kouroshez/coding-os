#!/usr/bin/env bash
# Coding OS - Project-root, worktree and panel-id resolution.
# Sourced by cos-env.sh from its own resolved directory; never run
# directly and never sourced by a hook.

# Pure-Bash project-root finder (no python3 spawn — this runs on every hook).
# DRIFT WARNING: mirrors src/core/thinking_os/database.py::_find_project_root_from_cwd
# (its _ROOT_MARKERS + .coding-os/-co-location requirement); tests/test_hooks.py
# asserts the two stay identical. The extra $HOME hard-stop here prevents binding
# the global hub at $HOME/.coding-os. Echoes the resolved root, or empty when none
# is found at/below the $HOME boundary.
_cos_find_project_root() {
  local dir home_real first_state="" marker found_marker parent
  # Rule 5: resolve symlinks (macOS /tmp -> /private/tmp) before the $HOME compare.
  dir="$(cd -P "${PWD}" 2>/dev/null && pwd -P)" || dir=""
  # Only an absolute, resolvable cwd is walkable. A relative/stale $PWD (cos-env.sh
  # is SOURCED, so it inherits the parent's $PWD) would otherwise make dirname
  # collapse to '.' — a fixpoint that spins forever. Bail to the relative default.
  if [[ "$dir" != /* ]]; then
    printf ''
    return 0
  fi
  home_real="$(cd -P "${HOME:-/dev/null}" 2>/dev/null && pwd -P)" || home_real="${HOME:-}"
  while [[ -n "$dir" && "$dir" != "/" ]]; do
    # Never inspect/accept $HOME or above — $HOME/.coding-os is the global hub.
    if [[ -n "$home_real" && "$dir" == "$home_real" ]]; then
      break
    fi
    if [[ -d "$dir/.coding-os" ]]; then
      if [[ -z "$first_state" ]]; then
        first_state="$dir"
      fi
      # Prefer a .coding-os/ co-located with a root marker (skips a stray nested
      # .coding-os/). Marker set mirrors database.py::_ROOT_MARKERS.
      found_marker=""
      for marker in .git .coding-os.yaml pyproject.toml package.json go.mod AGENTS.md; do
        if [[ -e "$dir/$marker" ]]; then
          found_marker=1
          break
        fi
      done
      if [[ -n "$found_marker" ]]; then
        printf '%s' "$dir"
        return 0
      fi
    fi
    parent="$(dirname "$dir")"
    # dirname fixpoint ('/' or any path that cannot ascend) → stop, never spin.
    if [[ "$parent" == "$dir" ]]; then
      break
    fi
    dir="$parent"
  done
  # No marked root below the boundary → innermost bare .coding-os/ (never
  # lazy-create at cwd), else empty (caller keeps the relative default).
  printf '%s' "$first_state"
}

# Resolve the MAIN repo root for a command running inside a git worktree, or
# empty. A linked worktree's --git-common-dir points at <main>/.git, so its
# parent is the main checkout. Used only when a worktree command lacks the
# COS_PROJECT_ROOT fast-path ( / pr-mode). Always returns 0 — this file
# is SOURCED under the caller's `set -euo pipefail`, so a non-zero return from a
# command-substitution assignment would kill the hook (mirrors
# _cos_find_project_root's echo-empty-and-return-0 contract).
# SPEC: docs/playbooks/pr-workflow.md § 3.
_cos_main_repo_from_worktree() {
  command -v git >/dev/null 2>&1 || { printf ''; return 0; }
  local common
  common="$(git rev-parse --git-common-dir 2>/dev/null)" || { printf ''; return 0; }
  [[ -z "$common" ]] && { printf ''; return 0; }
  common="$(cd -P "$common" 2>/dev/null && pwd -P)" || { printf ''; return 0; }
  case "$common" in
    */.git) printf '%s' "${common%/.git}" ;;
    *)      printf '' ;;
  esac
  return 0
}

# Cheap worktree pre-check (NO git fork): a linked worktree's root carries `.git`
# as a FILE (a gitdir pointer), whereas a normal checkout has it as a directory.
# Walk up at most 40 levels from PWD looking for a `.git` file — returns 0 (found)
# so the git-fork probe below runs only for a plausible worktree, keeping normal
# trunk hooks fork-free. Bounded + dirname-fixpoint guarded against infinite walk.
_cos_has_dotgit_file() {
  local dir="${PWD}" i=0
  [[ "$dir" == /* ]] || return 1
  while [[ -n "$dir" && "$dir" != "/" && $i -lt 40 ]]; do
    [[ -f "$dir/.git" ]] && return 0
    [[ -d "$dir/.git" ]] && return 1   # a real repo root — not a worktree
    local parent; parent="$(dirname "$dir")"
    [[ "$parent" == "$dir" ]] && break
    dir="$parent"; i=$((i + 1))
  done
  return 1
}

# _cos_helpers_dir — physical path to _helpers/, resolved through this file's
# own symlink chain. Consumers (and the meta-repo's own .claude/hooks/) symlink
# cos-env.sh but NOT _helpers/, so a $(dirname)-relative path lands in a dir with
# no helpers and the python fallbacks silently no-op — a fail-OPEN gap. readlink
# to the real file's dir finds _helpers/. Defined here (before the worktree-
# routing + pr-mode-enablement blocks below call it) so it is already in scope.
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
# pr-mode enablement — when this project's Hub sets
# git_settings.enabled=true in hub-settings.json, export COS_GIT_WORKFLOW=pr
# (+ branch policy) into EVERY hook's process env. That env is the only place
# branch-guard / block-shared-tree-edit / the cos pr executor can read the mode
# (the inline per-command override is broken). Default OFF = byte-identical to
# trunk. A cheap grep-gate keeps trunk projects (no git_settings key) at one
# grep per hook; an explicitly-exported COS_GIT_WORKFLOW always wins.
# SPEC: docs/playbooks/pr-workflow.md § 1.
# ---------------------------------------------------------------------------
_cos_git_warn_once() {
  # Debounced stderr warning (≤1/hour per condition per state dir) so a persistent
  # corrupt/divergent git_settings surfaces without spamming every hook. Fail-open.
  local key="$1" msg="$2" marker now last
  marker="${COS_STATE_DIR}/.git-settings-warn-${key}"
  now="$(date +%s 2>/dev/null || echo 0)"
  if [[ -f "$marker" ]]; then
    last="$(cat "$marker" 2>/dev/null || echo 0)"
    if [[ $((now - last)) -lt 3600 ]]; then
      return 0
    fi
  fi
  printf '%s\n' "$msg" >&2 2>/dev/null || true
  printf '%s' "$now" >"$marker" 2>/dev/null || true
}

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
