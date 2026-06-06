#!/usr/bin/env bash
# Claude adapter installer for coding-os.
#
# Thin wrapper: delegates the common install work (dirs, hooks, rules,
# skills, commands, role prompts, agent identity) to
# src/core/scripts/install-adapter.sh, then performs Claude-specific
# finalization (settings.json render, .mcp.json).
#
# History: prior versions also symlinked role files into .claude/agents/
# anticipating an AgentDefinition-driven dispatch path. Decision D2 of
# (2026-05-05) keeps `query()`-per-formula because role
# sub-sessions need their own permission_mode + MCP + hooks; the
# AgentDefinition path would force inheritance from the parent.
# .claude/agents/ symlinks were therefore removed — slash-command
# role prompts still ship via .claude/commands/role-*.md.
set -euo pipefail
shopt -s nullglob

CODING_OS_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
PROJECT_ROOT="${PWD}"

echo "⚙️  Installing coding-os Claude adapter..."
echo "  Project: $PROJECT_ROOT"
echo "  coding-os: $CODING_OS_ROOT"

# 1-8. Common install steps (shared with codex / cursor).
bash "${CODING_OS_ROOT}/src/core/scripts/install-adapter.sh" \
  --adapter claude --agent-dir .claude \
  --coding-os-root "$CODING_OS_ROOT" --project-root "$PROJECT_ROOT"

# 9. settings.json from registry-rendered template.
TEMPLATE="${CODING_OS_ROOT}/src/adapters/claude/settings.template.json"
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
MCP_HELPER="${CODING_OS_ROOT}/src/adapters/claude/_install_helpers/update_mcp_json.py"
if [[ -f "$MCP_HELPER" ]]; then
  python3 "$MCP_HELPER" "$MCP_FILE" "$CODING_OS_ROOT" \
    || echo "  WARN: Could not update .mcp.json automatically (see error above)"
else
  echo "  WARN: helper missing at $MCP_HELPER — .mcp.json not updated"
fi

# 11. Strip any pre-Q.deep .claude/agents/ symlinks — D2 retired the
# AgentDefinition path; presence of these symlinks was misleading
# because the dispatcher uses query() not the Agent tool.
if [[ -d "${PROJECT_ROOT}/.claude/agents" ]]; then
  for legacy in "${PROJECT_ROOT}/.claude/agents/"*.md; do
    [[ -L "$legacy" ]] && rm -f "$legacy"
  done
  rmdir "${PROJECT_ROOT}/.claude/agents" 2>/dev/null || true
fi

# 12. Local permission overrides — copy template once if not present.
LOCAL_TEMPLATE="${CODING_OS_ROOT}/src/adapters/claude/settings.local.template.json"
LOCAL_TARGET="${PROJECT_ROOT}/.claude/settings.local.json"
if [[ ! -f "$LOCAL_TARGET" && -f "$LOCAL_TEMPLATE" ]]; then
  cp "$LOCAL_TEMPLATE" "$LOCAL_TARGET"
fi

echo ""
echo "✅ Claude adapter installed."
echo "  Settings: .claude/settings.json (generated)"
echo "  Perms:    .claude/settings.local.json (copied)"
echo "  MCP:      .mcp.json (updated)"
echo "  Roles:    .claude/commands/role-*.md (slash commands)"
echo ""
echo "Optional: real role-agent dispatch via claude-agent-sdk"
echo "  uv sync --extra claude-sdk"
echo "  # → cos_dispatch_formula_run spawns real Claude Code sub-sessions"
echo "  # → see docs/adapters/claude-sdk.md"
echo ""
echo "Branding note:"
echo "  This adapter integrates coding-os with Anthropic's Claude Code."
echo "  coding-os is independent and is NOT branded as, affiliated with,"
echo "  or endorsed by Anthropic. References to 'Claude Code' describe"
echo "  Anthropic's product per their terms — see docs/adapters/claude-sdk.md."
