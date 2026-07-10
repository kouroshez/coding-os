#!/usr/bin/env bash
# Codex adapter installer for coding-os.
#
# Thin wrapper: delegates the common install work (dirs, hooks, rules,
# skills, commands, role prompts, agent identity) to
# src/core/scripts/install-adapter.sh, then performs Codex-specific
# finalization (.codex/hooks.json render, project-local config.toml
# with hooks feature flag + MCP server entry).
#
# Why Codex-specific finalization stays here:
#   • hooks.json is generated from registry.yaml-rendered template via
#     `make regen-adapter-templates`; install.sh just substitutes the
#     absolute hooks path so commands resolve from any cwd.
#   • Codex enables hooks via the `hooks = true` flag in
#     `.codex/config.toml` (see developers.openai.com/codex/hooks).
#   • MCP servers for Codex are project-scoped via the same TOML.
set -euo pipefail
shopt -s nullglob

CODING_OS_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_ROOT="${PWD}"

echo "⚙️  Installing coding-os Codex adapter..."

# 1-8. Common install steps (shared with claude).
bash "${CODING_OS_ROOT}/core/scripts/install-adapter.sh" \
  --adapter codex --agent-dir .codex \
  --coding-os-root "$CODING_OS_ROOT" --project-root "$PROJECT_ROOT"

# 9. .codex/hooks.json from registry-rendered template.
# Use absolute hook paths so a Codex session launched in a nested cwd
# still resolves the script. (Codex runs `sh -c <command>` with the
# session cwd, not the project root.)
TEMPLATE="${CODING_OS_ROOT}/adapters/codex/hooks.template.json"
HOOKS_ABS="${PROJECT_ROOT}/.codex/hooks"
HOOKS_ESCAPED=$(printf '%s' "$HOOKS_ABS" | sed 's/[&|]/\\&/g')
sed "s|{{HOOKS_DIR}}|${HOOKS_ESCAPED}|g" "$TEMPLATE" > "${PROJECT_ROOT}/.codex/hooks.json"

# 10. Drop legacy .codex/instructions.md from older adapter versions.
# It was never a real Codex convention and Codex CLI doesn't load it.
# AGENTS.md at the project root replaces it.
if [[ -f "${PROJECT_ROOT}/.codex/instructions.md" ]]; then
  rm -f "${PROJECT_ROOT}/.codex/instructions.md"
fi

# 11. Project-local .codex/config.toml — feature flag + MCP server entry.
CODEX_CONFIG="${PROJECT_ROOT}/.codex/config.toml"
mkdir -p "${PROJECT_ROOT}/.codex"

ENABLE_HELPER="${CODING_OS_ROOT}/adapters/codex/enable_codex_hooks.py"
if [[ -x "$ENABLE_HELPER" || -f "$ENABLE_HELPER" ]]; then
  HOOKS_STATUS="$(python3 "$ENABLE_HELPER" "$CODEX_CONFIG" 2>&1 || echo 'failed to enable hooks (see stderr)')"
else
  HOOKS_STATUS="helper missing at $ENABLE_HELPER"
fi

MCP_HELPER="${CODING_OS_ROOT}/adapters/codex/ensure_codex_mcp.py"
if command -v cos >/dev/null 2>&1; then
  MCP_CMD="cos"
  MCP_ARGS=("server-start")
else
  # Pre-`uv tool install` fallback. Use the current Python interpreter so
  # MCP startup does not depend on uv cache access inside Codex's sandbox.
  PYTHON_BIN="$(python3 -c 'import sys; print(sys.executable)')"
  MCP_CMD="$PYTHON_BIN"
  MCP_ARGS=("${CODING_OS_ROOT}/core/thinking_os/server.py")
fi

if [[ -x "$MCP_HELPER" || -f "$MCP_HELPER" ]]; then
  MCP_STATUS="$(python3 "$MCP_HELPER" "$CODEX_CONFIG" "$MCP_CMD" "${MCP_ARGS[@]}" 2>&1 || echo 'failed to configure coding-os MCP (see stderr)')"
else
  MCP_STATUS="helper missing at $MCP_HELPER"
fi

echo ""
echo "✅ Codex adapter installed."
echo "  Hooks config: .codex/hooks.json (generated)"
echo "  SSOT:         AGENTS.md at project root (read by Codex)"
echo "  Hooks flag:   ${HOOKS_STATUS}"
echo "  MCP:          ${MCP_STATUS}"
echo ""
echo "ACTION: Start Codex and run /hooks to review and trust the installed project hooks."
echo "        Repeat that review whenever a hook file changes; Codex keys trust to its hash."
