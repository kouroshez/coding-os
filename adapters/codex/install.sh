#!/usr/bin/env bash
# Codex adapter installer for coding-os
#
# Codex CLI reads AGENTS.md at project root for persistent instructions
# (32 KiB cap per developers.openai.com/codex/guides/agents-md) and merges
# global AGENTS.md from ~/.codex/AGENTS.md. Rules content therefore lives
# in AGENTS.md — we do NOT generate a separate instructions.md (that file
# is not part of any Codex loading convention).
#
# Codex hooks are behind the `codex_hooks = true` feature flag in
# config.toml (per developers.openai.com/codex/hooks). Codex supports
# project-scoped `.codex/config.toml` overrides, so this adapter enables
# the flag in the project-local config instead of mutating the user's
# global ~/.codex/config.toml.
#
# MCP servers for Codex also support project-scoped `.codex/config.toml`,
# so this adapter keeps the coding-os MCP entry local to the installed
# project. We do NOT touch .mcp.json here (that is Claude's convention).
#
# What this adapter actually installs:
#   .codex/hooks/         — symlinks to core/hooks/*.sh
#   .codex/hooks.json     — generated from hooks.template.json
#   .codex/rules/         — symlinks to core/rules/*.md   (for parity with
#                           .claude/rules/; Codex agents read these on-
#                           demand via path references in AGENTS.md)
#   .codex/skills/<name>/ — symlinks to core/skills/<name>/SKILL.md
#   .codex/commands/      — symlinks to core/commands/*.md
#
# Rationale for rules/skills/commands symlinks: consumer projects do not
# have core/ in their tree (coding-os is installed as a library). Without
# these symlinks, AGENTS.md path references like `core/skills/X/SKILL.md`
# would not resolve inside a consumer project. With them, both adapters
# offer the same content surface — only the loading mechanism differs
# (Claude auto-loads `.claude/*`, Codex reads on-demand via AGENTS.md).
set -euo pipefail

CODING_OS_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_ROOT="${PWD}"

echo "Installing coding-os Codex adapter..."

# 1. Create .codex directory structure (symmetric with .claude/)
mkdir -p "${PROJECT_ROOT}/.codex/hooks"
mkdir -p "${PROJECT_ROOT}/.codex/rules"
mkdir -p "${PROJECT_ROOT}/.codex/skills"
mkdir -p "${PROJECT_ROOT}/.codex/commands"
mkdir -p "${PROJECT_ROOT}/.coding-os"

# Persist agent identity so cos-env.sh can attribute hook log lines correctly
# even when the runtime does not expose a well-known env marker. Read-only
# fallback: explicit > env heuristics > this file.
echo "codex" > "${PROJECT_ROOT}/.coding-os/.agent" 2>/dev/null || true

# 2. Symlink hooks from core/ (SSOT)
for hook in "${CODING_OS_ROOT}/core/hooks/"*.sh; do
  name=$(basename "$hook")
  ln -sf "$hook" "${PROJECT_ROOT}/.codex/hooks/${name}"
done

# 2b. Symlink adapter-specific Codex dispatcher hooks.
if [ -d "${CODING_OS_ROOT}/adapters/codex/hooks" ]; then
  for hook in "${CODING_OS_ROOT}/adapters/codex/hooks/"*.sh; do
    [ -e "$hook" ] || continue
    name=$(basename "$hook")
    ln -sf "$hook" "${PROJECT_ROOT}/.codex/hooks/${name}"
  done
fi

# 3. Symlink rules from core/rules/*.md — parity with Claude's
# .claude/rules/. Codex CLI's Starlark sandbox scanner expects `.rules`
# files; `.md` files in this dir are ignored by that scanner and serve
# only as agent-readable content.
for rule in "${CODING_OS_ROOT}/core/rules/"*.md; do
  [ -e "$rule" ] || continue
  name=$(basename "$rule")
  ln -sf "$rule" "${PROJECT_ROOT}/.codex/rules/${name}"
done

# 4. Symlink skills (folder structure mirrors core/skills/<name>/SKILL.md)
for skill_dir in "${CODING_OS_ROOT}/core/skills/"*/; do
  [ -e "$skill_dir" ] || continue
  name=$(basename "$skill_dir")
  mkdir -p "${PROJECT_ROOT}/.codex/skills/${name}"
  if [ -f "${skill_dir}SKILL.md" ]; then
    ln -sf "${skill_dir}SKILL.md" "${PROJECT_ROOT}/.codex/skills/${name}/SKILL.md"
  fi
done

# 4b. Link stack-specific skills if installed-manifest declares templates.
# Idempotent: link-stack-skills.sh uses `ln -sf` and skips missing dirs.
# Defensive: only run when manifest + linker both exist.
MANIFEST="${PROJECT_ROOT}/.coding-os/installed-manifest.json"
LINKER="${CODING_OS_ROOT}/core/scripts/link-stack-skills.sh"
if [ -f "$MANIFEST" ] && [ -x "$LINKER" ]; then
  STACKS=$(python3 -c "import json,sys; m=json.load(open('$MANIFEST')); print(' '.join(m.get('templates',[])))" 2>/dev/null || true)
  if [ -n "$STACKS" ]; then
    bash "$LINKER" "${PROJECT_ROOT}/.codex/skills" "${CODING_OS_ROOT}" $STACKS 2>/dev/null || true
    echo "  Re-linked stack skills: $STACKS"
  fi
fi

# 5. Symlink commands (Codex supports slash commands; even without a
# dedicated loader directory, agent-readable content at a stable path
# is the minimum requirement).
if [ -d "${CODING_OS_ROOT}/core/commands" ]; then
  for cmd in "${CODING_OS_ROOT}/core/commands/"*.md; do
    [ -e "$cmd" ] || continue
    name=$(basename "$cmd")
    ln -sf "$cmd" "${PROJECT_ROOT}/.codex/commands/${name}"
  done
fi

# 6. Generate hooks.json from template.
# Use absolute hook paths anchored to the installed project root. Relative
# `.codex/hooks/<hook>.sh` only works when Codex is launched from the repo
# root; if the session starts in a nested cwd, `sh -c <command>` resolves the
# path relative to that subdirectory and every hook fails with ENOENT.
#
# We intentionally avoid shell-time `git rev-parse --show-toplevel` here:
# Codex may run outside a git repo, under an ancestor repo, or with `git`
# missing from PATH. The installer already knows the intended project root,
# so bake that path into the generated config deterministically.
TEMPLATE="${CODING_OS_ROOT}/adapters/codex/hooks.template.json"
HOOKS_ABS="${PROJECT_ROOT}/.codex/hooks"
HOOKS_ESCAPED=$(printf '%s' "$HOOKS_ABS" | sed 's/[&|]/\\&/g')
sed "s|{{HOOKS_DIR}}|${HOOKS_ESCAPED}|g" "$TEMPLATE" > "${PROJECT_ROOT}/.codex/hooks.json"

# 7. Clean up legacy .codex/instructions.md from older adapter versions.
# It was never a real Codex convention and Codex CLI doesn't load it.
# AGENTS.md at the project root replaces it.
if [ -f "${PROJECT_ROOT}/.codex/instructions.md" ]; then
  rm -f "${PROJECT_ROOT}/.codex/instructions.md"
fi

# 8. Register coding-os MCP server in project-local .codex/config.toml.
# Codex loads trusted project overrides from `.codex/config.toml`, so the
# adapter keeps both the hook feature flag and MCP server local to this repo.
CODEX_CONFIG="${PROJECT_ROOT}/.codex/config.toml"
mkdir -p "${PROJECT_ROOT}/.codex"

# Enable the `codex_hooks` feature flag in project-local .codex/config.toml.
# We ship the Python logic as a standalone script so install.sh never
# relies on command-substitution-of-a-heredoc ($(python3 - <<'PY' …)),
# which has been observed to hang deterministically when any sandbox in
# the call stack keeps the pipe's read-end alive after python3 exits.
#
# The helper is idempotent: prints "already enabled" when the flag is
# already `= true`, otherwise adds `codex_hooks = true` under `[features]`.
ENABLE_HELPER="${CODING_OS_ROOT}/adapters/codex/enable_codex_hooks.py"
if [ -x "$ENABLE_HELPER" ] || [ -f "$ENABLE_HELPER" ]; then
  HOOKS_STATUS="$(python3 "$ENABLE_HELPER" "$CODEX_CONFIG" 2>&1 || echo 'failed to enable codex_hooks (see stderr)')"
else
  HOOKS_STATUS="helper missing at $ENABLE_HELPER"
fi

MCP_HELPER="${CODING_OS_ROOT}/adapters/codex/ensure_codex_mcp.py"
if command -v cos >/dev/null 2>&1; then
  MCP_CMD="cos"
  MCP_ARGS=("server-start")
else
  # Fallback before `uv tool install` puts `cos` on PATH. Use the current
  # Python interpreter directly instead of `uv run` so MCP startup does not
  # depend on uv cache access inside Codex's sandbox.
  PYTHON_BIN="$(python3 -c 'import sys; print(sys.executable)')"
  MCP_CMD="$PYTHON_BIN"
  MCP_ARGS=("${CODING_OS_ROOT}/core/thinking-os/server.py")
fi

if [ -x "$MCP_HELPER" ] || [ -f "$MCP_HELPER" ]; then
  MCP_STATUS="$(python3 "$MCP_HELPER" "$CODEX_CONFIG" "$MCP_CMD" "${MCP_ARGS[@]}" 2>&1 || echo 'failed to configure coding-os MCP (see stderr)')"
else
  MCP_STATUS="helper missing at $MCP_HELPER"
fi

echo ""
echo "Codex adapter installed successfully!"
echo "  Hooks:        .codex/hooks/ (symlinked to core/)"
echo "  Rules:        .codex/rules/ (symlinked to core/)"
echo "  Skills:       .codex/skills/ (symlinked to core/)"
echo "  Commands:     .codex/commands/ (symlinked to core/)"
echo "  Hooks config: .codex/hooks.json (generated)"
echo "  SSOT:         AGENTS.md at project root (read by Codex)"
echo "  Hooks:        ${HOOKS_STATUS}"
echo "  MCP:          ${MCP_STATUS}"
echo ""
echo "NOTE: Codex PreToolUse/PostToolUse only support the Bash tool."
echo "      Write/Edit-triggered enforcement (doc-anchor, migration-conflict,"
echo "      hardcoded-literals) is Claude-only until Codex adds those events."
echo "      Matching Codex hooks run concurrently, so this adapter coalesces"
echo "      Bash / SessionStart / Stop checks through dispatcher scripts."
