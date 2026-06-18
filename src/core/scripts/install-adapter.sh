#!/usr/bin/env bash
# Coding OS — common adapter installer.
#
# PURPOSE
#   Single source of truth for the steps every adapter (claude / codex)
#   shares: directory creation, symlinks for hooks / rules /
#   skills / commands, role-prompt linking, agent-identity stamping,
#   stack-skill re-linking. Each adapter's install.sh now boils down to
#   "configure + dispatch to this script + do adapter-specific finalization".
#
# USAGE
#   bash src/core/scripts/install-adapter.sh \
#     --adapter <claude|codex> \
#     --agent-dir <.claude|.codex> \
#     [--coding-os-root <path>] [--project-root <path>]
#
# CONTRACT
#   Idempotent. Safe to re-run. Uses `ln -sf` so existing links rehome.
#   Never deletes or overwrites adapter-specific finalization (settings.json,
#   hooks.json, mcp.json) — those are owned by the adapter's install.sh
#   AFTER this script returns.
set -euo pipefail
shopt -s nullglob

ADAPTER=""
AGENT_DIR=""
CODING_OS_ROOT=""
PROJECT_ROOT="${PWD}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --adapter) ADAPTER="$2"; shift 2 ;;
    --agent-dir) AGENT_DIR="$2"; shift 2 ;;
    --coding-os-root) CODING_OS_ROOT="$2"; shift 2 ;;
    --project-root) PROJECT_ROOT="$2"; shift 2 ;;
    *) echo "Unknown flag: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$ADAPTER" || -z "$AGENT_DIR" ]]; then
  echo "usage: $0 --adapter <id> --agent-dir <.id> [--coding-os-root P] [--project-root P]" >&2
  exit 2
fi

# Resolve coding-os root from caller's BASH_SOURCE if not supplied.
if [[ -z "$CODING_OS_ROOT" ]]; then
  CODING_OS_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
fi

# Avoid leading dot in user-visible label (.claude → claude).
ADAPTER_LABEL="${AGENT_DIR#.}"

# ---------------------------------------------------------------------------
# 1. Directory layout
# ---------------------------------------------------------------------------
mkdir -p \
  "${PROJECT_ROOT}/${AGENT_DIR}/hooks" \
  "${PROJECT_ROOT}/${AGENT_DIR}/rules" \
  "${PROJECT_ROOT}/${AGENT_DIR}/skills" \
  "${PROJECT_ROOT}/${AGENT_DIR}/commands" \
  "${PROJECT_ROOT}/.coding-os"

# ---------------------------------------------------------------------------
# 1b. Sweep stale symlinks BEFORE re-linking. Without this, renames in
#     core/ leave dangling symlinks in consumer projects (the user has to
#     `rm` them by hand). `find -L … -type l` matches symlinks whose
#     target no longer exists. We only sweep dirs we own, never user data.
# ---------------------------------------------------------------------------
for sub in hooks rules commands; do
  target="${PROJECT_ROOT}/${AGENT_DIR}/${sub}"
  if [[ -d "$target" ]]; then
    # macOS BSD find quirk: `-L … -type l` for broken-symlink test must use
    # `! -e`. POSIX-portable form:
    while IFS= read -r -d '' link; do
      rm -f -- "$link"
    done < <(find "$target" -maxdepth 1 -type l ! -exec test -e {} \; -print0 2>/dev/null)
  fi
done
# Skills are nested one level deep (skills/<name>/SKILL.md), sweep both
# the SKILL.md links and any abandoned skill dirs whose source vanished.
SKILLS_TARGET="${PROJECT_ROOT}/${AGENT_DIR}/skills"
if [[ -d "$SKILLS_TARGET" ]]; then
  while IFS= read -r -d '' link; do
    rm -f -- "$link"
  done < <(find "$SKILLS_TARGET" -mindepth 2 -maxdepth 2 -type l ! -exec test -e {} \; -print0 2>/dev/null)
  # Empty skill dirs (source removed entirely) — only delete if dir
  # contains nothing but stale symlinks (find above already pruned).
  find "$SKILLS_TARGET" -mindepth 1 -maxdepth 1 -type d -empty -delete 2>/dev/null || true
fi
# Claude SDK sub-agents dir mirrors src/core/thinking_os/agents/ verbatim;
# sweep that one too when it exists.
AGENTS_LINK_DIR="${PROJECT_ROOT}/${AGENT_DIR}/agents"
if [[ -d "$AGENTS_LINK_DIR" ]]; then
  while IFS= read -r -d '' link; do
    rm -f -- "$link"
  done < <(find "$AGENTS_LINK_DIR" -maxdepth 1 -type l ! -exec test -e {} \; -print0 2>/dev/null)
fi

# ---------------------------------------------------------------------------
# 2. Agent identity (read-only fallback for cos-env.sh)
# ---------------------------------------------------------------------------
echo "$ADAPTER" > "${PROJECT_ROOT}/.coding-os/.agent" 2>/dev/null || true

# ---------------------------------------------------------------------------
# 3. Core hooks
# ---------------------------------------------------------------------------
for hook in "${CODING_OS_ROOT}/core/hooks/"*.sh; do
  name=$(basename "$hook")
  # Fail-open (R14): never link a syntax-broken hook. A hook that aborts on a
  # parse error exits non-zero, which the runtime reads as a BLOCK — one broken
  # hook would then reject every matching tool call. Skip + warn instead.
  if ! bash -n "$hook" 2>/dev/null; then
    echo "  ⚠️  ${name}: bash -n failed — NOT linked (fix the hook source)" >&2
    continue
  fi
  ln -sf "$hook" "${PROJECT_ROOT}/${AGENT_DIR}/hooks/${name}"
done

# ---------------------------------------------------------------------------
# 4. Adapter-specific dispatcher hooks (optional)
# ---------------------------------------------------------------------------
if [[ -d "${CODING_OS_ROOT}/adapters/${ADAPTER}/hooks" ]]; then
  for hook in "${CODING_OS_ROOT}/adapters/${ADAPTER}/hooks/"*.sh; do
    name=$(basename "$hook")
    if ! bash -n "$hook" 2>/dev/null; then  # fail-open (R14) — see core-hooks loop
      echo "  ⚠️  ${name}: bash -n failed — NOT linked (fix the hook source)" >&2
      continue
    fi
    ln -sf "$hook" "${PROJECT_ROOT}/${AGENT_DIR}/hooks/${name}"
  done
fi

# ---------------------------------------------------------------------------
# 5. Core rules
# ---------------------------------------------------------------------------
for rule in "${CODING_OS_ROOT}/core/rules/"*.md; do
  name=$(basename "$rule")
  ln -sf "$rule" "${PROJECT_ROOT}/${AGENT_DIR}/rules/${name}"
done

# ---------------------------------------------------------------------------
# 6. Core skills (one dir per skill; SKILL.md is the entry point).
# Per-project opt-out: .coding-os.yaml::disabled_skills (single store, written
# by `cos skill disable`). A disabled skill is skipped AND unlinked so the agent
# runtime stops loading its description into every session's system prompt.
# The live toggle is done inline by cli.skill_commands; this re-applies it on
# a fresh install / `cos update`.
# ---------------------------------------------------------------------------
PROJECT_CONFIG="${PROJECT_ROOT}/.coding-os.yaml"
DISABLED_HELPER="${CODING_OS_ROOT}/core/scripts/extract_disabled_skills.py"
DISABLED_SKILLS=""
if [[ -f "$PROJECT_CONFIG" && -f "$DISABLED_HELPER" ]]; then
  DISABLED_SKILLS=$(python3 "$DISABLED_HELPER" "$PROJECT_CONFIG" 2>/dev/null || true)
fi
_skill_disabled() {
  [[ " ${DISABLED_SKILLS} " == *" $1 "* ]]
}
DISABLED_COUNT=0
for skill_dir in "${CODING_OS_ROOT}/core/skills/"*/; do
  name=$(basename "$skill_dir")
  if _skill_disabled "$name"; then
    rm -f "${PROJECT_ROOT}/${AGENT_DIR}/skills/${name}/SKILL.md" 2>/dev/null || true
    rmdir "${PROJECT_ROOT}/${AGENT_DIR}/skills/${name}" 2>/dev/null || true
    DISABLED_COUNT=$((DISABLED_COUNT + 1))
    continue
  fi
  mkdir -p "${PROJECT_ROOT}/${AGENT_DIR}/skills/${name}"
  if [[ -f "${skill_dir}SKILL.md" ]]; then
    ln -sf "${skill_dir}SKILL.md" "${PROJECT_ROOT}/${AGENT_DIR}/skills/${name}/SKILL.md"
  fi
done

# 6b. Re-link stack-specific skills declared in installed-manifest.json.
# Idempotent: link-stack-skills.sh uses `ln -sf` and skips missing dirs.
MANIFEST="${PROJECT_ROOT}/.coding-os/installed-manifest.json"
LINKER="${CODING_OS_ROOT}/core/scripts/link-stack-skills.sh"
if [[ -f "$MANIFEST" && -x "$LINKER" ]]; then
  STACKS_HELPER="${CODING_OS_ROOT}/adapters/${ADAPTER}/_install_helpers/extract_stacks.py"
  if [[ ! -f "$STACKS_HELPER" ]]; then
    # Fallback: inline parse via python3 — bash 5.3.9 heredoc-deadlock-safe
    # because we don't use a heredoc here, just a -c arg.
    STACKS=$(python3 -c "import json,sys; m=json.load(open('${MANIFEST}')); print(' '.join(m.get('templates',[])))" 2>/dev/null || true)
  else
    STACKS=$(python3 "$STACKS_HELPER" "$MANIFEST" 2>/dev/null || true)
  fi
  if [[ -n "$STACKS" ]]; then
    bash "$LINKER" "${PROJECT_ROOT}/${AGENT_DIR}/skills" "${CODING_OS_ROOT}" $STACKS 2>/dev/null || true
    echo "  ✅ Re-linked stack skills: $STACKS"
    # Re-apply disabled opt-outs to stack skills too (the linker is unconditional).
    for name in $DISABLED_SKILLS; do
      if [[ -e "${PROJECT_ROOT}/${AGENT_DIR}/skills/${name}/SKILL.md" ]]; then
        rm -f "${PROJECT_ROOT}/${AGENT_DIR}/skills/${name}/SKILL.md" 2>/dev/null || true
        rmdir "${PROJECT_ROOT}/${AGENT_DIR}/skills/${name}" 2>/dev/null || true
        DISABLED_COUNT=$((DISABLED_COUNT + 1))
      fi
    done
  fi
fi
[[ "$DISABLED_COUNT" -gt 0 ]] && echo "  ✅ Skipped ${DISABLED_COUNT} disabled skill(s) (.coding-os.yaml::disabled_skills)"

# ---------------------------------------------------------------------------
# 7. Core commands (slash commands)
# ---------------------------------------------------------------------------
COMMANDS_DIR="${CODING_OS_ROOT}/core/commands"
if [[ -d "$COMMANDS_DIR" ]]; then
  for cmd in "${COMMANDS_DIR}/"*.md; do
    name=$(basename "$cmd")
    ln -sf "$cmd" "${PROJECT_ROOT}/${AGENT_DIR}/commands/${name}"
  done
fi

# ---------------------------------------------------------------------------
# 8. Role prompt slash commands (researcher.md, analyst.md, …) exposed as
#    /role-<name> across all three adapters. README.md is excluded (it
#    documents the catalog, not a role).
# ---------------------------------------------------------------------------
AGENTS_DIR="${CODING_OS_ROOT}/core/thinking_os/agents"
if [[ -d "$AGENTS_DIR" ]]; then
  for agent in "${AGENTS_DIR}/"*.md; do
    base=$(basename "$agent")
    if [[ "$base" == "README.md" ]]; then
      continue
    fi
    role="${base%.md}"
    ln -sf "$agent" "${PROJECT_ROOT}/${AGENT_DIR}/commands/role-${role}.md"
  done
fi

# ---------------------------------------------------------------------------
# Done — adapter-specific finalization (settings.json / hooks.json /
# mcp config / agent-spawn registries) is the caller's responsibility.
# ---------------------------------------------------------------------------
echo "  ✅ ${ADAPTER_LABEL}: hooks/rules/skills/commands linked under ${AGENT_DIR}/"
