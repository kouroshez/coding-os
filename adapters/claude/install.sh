#!/usr/bin/env bash
# Claude adapter installer for coding-os
# Usage: bash adapters/claude/install.sh
set -euo pipefail
shopt -s nullglob

CODING_OS_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_ROOT="${PWD}"

echo "Installing coding-os Claude adapter..."
echo "  Project: $PROJECT_ROOT"
echo "  coding-os: $CODING_OS_ROOT"

# 1. Create .claude directory structure
mkdir -p "${PROJECT_ROOT}/.claude/rules"
mkdir -p "${PROJECT_ROOT}/.claude/skills"
mkdir -p "${PROJECT_ROOT}/.claude/hooks"
mkdir -p "${PROJECT_ROOT}/.coding-os"

# Persist agent identity so cos-env.sh can attribute hook log lines correctly
# even when the runtime does not expose a well-known env marker. Read-only
# fallback: explicit > env heuristics > this file.
echo "claude" > "${PROJECT_ROOT}/.coding-os/.agent" 2>/dev/null || true

# 2. Symlink hooks
for hook in "${CODING_OS_ROOT}/core/hooks/"*.sh; do
  name=$(basename "$hook")
  ln -sf "$hook" "${PROJECT_ROOT}/.claude/hooks/${name}"
done

# 3. Symlink core rules
for rule in "${CODING_OS_ROOT}/core/rules/"*.md; do
  name=$(basename "$rule")
  ln -sf "$rule" "${PROJECT_ROOT}/.claude/rules/${name}"
done

# 4. Symlink core skills
for skill_dir in "${CODING_OS_ROOT}/core/skills/"*/; do
  name=$(basename "$skill_dir")
  mkdir -p "${PROJECT_ROOT}/.claude/skills/${name}"
  ln -sf "${skill_dir}SKILL.md" "${PROJECT_ROOT}/.claude/skills/${name}/SKILL.md"
done

# 4b. Link stack-specific skills if installed-manifest declares templates.
# Idempotent: link-stack-skills.sh uses `ln -sf` and skips missing dirs.
# Defensive: only run when manifest + linker both exist (fresh installs
# that run install.sh before `cos init` has written a manifest skip cleanly).
MANIFEST="${PROJECT_ROOT}/.coding-os/installed-manifest.json"
LINKER="${CODING_OS_ROOT}/core/scripts/link-stack-skills.sh"
if [ -f "$MANIFEST" ] && [ -x "$LINKER" ]; then
  # bash 5.3.9 sporadically deadlocks `python3 - <<HEREDOC` AND nested
  # `$(python3 -c "$(cat <<'PY' ... PY)")` patterns inside command
  # substitutions. The only deadlock-immune form is a separate .py file
  # invoked as `python3 path/to/file.py args`. Helpers live next to this
  # script in `_install_helpers/`.
  STACKS_HELPER="${CODING_OS_ROOT}/adapters/claude/_install_helpers/extract_stacks.py"
  if [ -f "$STACKS_HELPER" ]; then
    STACKS=$(python3 "$STACKS_HELPER" "$MANIFEST" 2>/dev/null || true)
  else
    STACKS=""
  fi
  if [ -n "$STACKS" ]; then
    bash "$LINKER" "${PROJECT_ROOT}/.claude/skills" "${CODING_OS_ROOT}" $STACKS 2>/dev/null || true
    echo "  Re-linked stack skills: $STACKS"
  fi
fi

# 5. Generate settings.json from template
TEMPLATE="${CODING_OS_ROOT}/adapters/claude/settings.template.json"
HOOKS_REL=".claude/hooks"
sed "s|{{HOOKS_DIR}}|${HOOKS_REL}|g" "$TEMPLATE" > "${PROJECT_ROOT}/.claude/settings.json"

# 6. Add MCP server to .mcp.json
MCP_FILE="${PROJECT_ROOT}/.mcp.json"
if [ ! -f "$MCP_FILE" ]; then
  cat > "$MCP_FILE" << 'MCPEOF'
{
  "mcpServers": {}
}
MCPEOF
fi

# Add thinking_os MCP server entry. Same deadlock concern as STACKS above —
# any heredoc inside $(...) on bash 5.3.9 may hang. Use a separate helper.
MCP_HELPER="${CODING_OS_ROOT}/adapters/claude/_install_helpers/update_mcp_json.py"
if [ -f "$MCP_HELPER" ]; then
  python3 "$MCP_HELPER" "$MCP_FILE" "$CODING_OS_ROOT" \
    || echo "  WARN: Could not update .mcp.json automatically (see error above)"
else
  echo "  WARN: helper missing at $MCP_HELPER — .mcp.json not updated"
fi

# 7. Symlink commands
COMMANDS_DIR="${CODING_OS_ROOT}/core/commands"
if [ -d "$COMMANDS_DIR" ]; then
  mkdir -p "${PROJECT_ROOT}/.claude/commands"
  for cmd in "${COMMANDS_DIR}/"*.md; do
    name=$(basename "$cmd")
    ln -sf "$cmd" "${PROJECT_ROOT}/.claude/commands/${name}"
  done
fi

# 7b. Symlink Phase M formula-agent slash commands (F1..F11) — parity
# with .codex/commands/formula-f<N>.md and .cursor/commands/formula-f<N>.md.
# Each formula-f<N>.md resolves to the agent prompt in
# core/thinking_os/agents/. Claude Code surfaces them as /formula-f<N>.
AGENTS_DIR="${CODING_OS_ROOT}/core/thinking_os/agents"
if [ -d "$AGENTS_DIR" ]; then
  for agent in "$AGENTS_DIR"/F*.md; do
    [ -e "$agent" ] || continue
    fname=$(basename "$agent")
    # Convert F1_research.md → formula-f1.md
    num=$(echo "$fname" | sed 's/F\([0-9]*\)_.*/\1/')
    ln -sf "$agent" "${PROJECT_ROOT}/.claude/commands/formula-f${num}.md"
  done
fi

# 7c. Expose the same formula prompts as Claude SDK sub-agents under
# .claude/agents/F<N>_<slug>.md so the SDK can spawn them via
# AgentDefinition (claude_agent_sdk v0.2.x). One canonical source —
# core/thinking_os/agents/ — feeds both the slash-command path (7b) and
# the sub-agent path (7c).
mkdir -p "${PROJECT_ROOT}/.claude/agents"
if [ -d "$AGENTS_DIR" ]; then
  for agent in "$AGENTS_DIR"/F*.md; do
    [ -e "$agent" ] || continue
    name=$(basename "$agent")
    ln -sf "$agent" "${PROJECT_ROOT}/.claude/agents/${name}"
  done
fi

# 8. Copy settings.local.json if not exists
LOCAL_TEMPLATE="${CODING_OS_ROOT}/adapters/claude/settings.local.template.json"
LOCAL_TARGET="${PROJECT_ROOT}/.claude/settings.local.json"
if [ ! -f "$LOCAL_TARGET" ] && [ -f "$LOCAL_TEMPLATE" ]; then
  cp "$LOCAL_TEMPLATE" "$LOCAL_TARGET"
fi

echo ""
echo "Claude adapter installed successfully!"
echo "  Hooks:    .claude/hooks/ (symlinked)"
echo "  Rules:    .claude/rules/ (symlinked)"
echo "  Skills:   .claude/skills/ (symlinked)"
echo "  Commands: .claude/commands/ (symlinked)"
echo "  Settings: .claude/settings.json (generated)"
echo "  Perms:    .claude/settings.local.json (copied)"
echo "  MCP:      .mcp.json (updated)"
echo ""
echo "Optional: real formula-agent dispatch via claude-agent-sdk"
echo "  uv sync --extra claude-sdk"
echo "  # → cos_dispatch_formula_run spawns real Claude Code sub-sessions"
echo "  # → see docs/adapters/claude-sdk.md"
