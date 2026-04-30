#!/usr/bin/env bash
# Claude adapter installer for coding-os.
#
# Thin wrapper: delegates the common install work (dirs, hooks, rules,
# skills, commands, role prompts, agent identity) to
# core/scripts/install-adapter.sh, then performs Claude-specific
# finalization (settings.json render, .mcp.json, .claude/agents/ for
# Claude SDK sub-agent spawning).
set -euo pipefail
shopt -s nullglob

CODING_OS_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_ROOT="${PWD}"

echo "Installing coding-os Claude adapter..."
echo "  Project: $PROJECT_ROOT"
echo "  coding-os: $CODING_OS_ROOT"

# 1-8. Common install steps (shared with codex / cursor).
bash "${CODING_OS_ROOT}/core/scripts/install-adapter.sh" \
  --adapter claude --agent-dir .claude \
  --coding-os-root "$CODING_OS_ROOT" --project-root "$PROJECT_ROOT"

# 9. settings.json from registry-rendered template.
TEMPLATE="${CODING_OS_ROOT}/adapters/claude/settings.template.json"
HOOKS_REL=".claude/hooks"
sed "s|{{HOOKS_DIR}}|${HOOKS_REL}|g" "$TEMPLATE" > "${PROJECT_ROOT}/.claude/settings.json"

# 10. .mcp.json — register thinking_os MCP server entry.
MCP_FILE="${PROJECT_ROOT}/.mcp.json"
if [[ ! -f "$MCP_FILE" ]]; then
  cat > "$MCP_FILE" << 'MCPEOF'
{
  "mcpServers": {}
}
MCPEOF
fi
MCP_HELPER="${CODING_OS_ROOT}/adapters/claude/_install_helpers/update_mcp_json.py"
if [[ -f "$MCP_HELPER" ]]; then
  python3 "$MCP_HELPER" "$MCP_FILE" "$CODING_OS_ROOT" \
    || echo "  WARN: Could not update .mcp.json automatically (see error above)"
else
  echo "  WARN: helper missing at $MCP_HELPER — .mcp.json not updated"
fi

# 11. .claude/agents/ — expose role prompts as Claude SDK sub-agents.
# AgentDefinition (claude_agent_sdk v0.2.x) reads files from this dir;
# one canonical source (core/thinking_os/agents/) feeds both the
# slash-command path (handled by the shared installer) and the
# sub-agent path here.
mkdir -p "${PROJECT_ROOT}/.claude/agents"
AGENTS_DIR="${CODING_OS_ROOT}/core/thinking_os/agents"
if [[ -d "$AGENTS_DIR" ]]; then
  for agent in "${AGENTS_DIR}/"*.md; do
    name=$(basename "$agent")
    [[ "$name" == "README.md" ]] && continue
    ln -sf "$agent" "${PROJECT_ROOT}/.claude/agents/${name}"
  done
fi

# 12. Local permission overrides — copy template once if not present.
LOCAL_TEMPLATE="${CODING_OS_ROOT}/adapters/claude/settings.local.template.json"
LOCAL_TARGET="${PROJECT_ROOT}/.claude/settings.local.json"
if [[ ! -f "$LOCAL_TARGET" && -f "$LOCAL_TEMPLATE" ]]; then
  cp "$LOCAL_TEMPLATE" "$LOCAL_TARGET"
fi

echo ""
echo "Claude adapter installed successfully."
echo "  Settings: .claude/settings.json (generated)"
echo "  Perms:    .claude/settings.local.json (copied)"
echo "  MCP:      .mcp.json (updated)"
echo "  Sub-agents: .claude/agents/ (role prompts symlinked for SDK)"
echo ""
echo "Optional: real role-agent dispatch via claude-agent-sdk"
echo "  uv sync --extra claude-sdk"
echo "  # → cos_dispatch_formula_run spawns real Claude Code sub-sessions"
echo "  # → see docs/adapters/claude-sdk.md"
