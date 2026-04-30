#!/usr/bin/env bash
# Cursor adapter installer for coding-os.
#
# Thin wrapper: delegates the common install work to
# core/scripts/install-adapter.sh, then performs Cursor-specific
# finalization (hooks.json render, project-local mcp.json).
set -euo pipefail
shopt -s nullglob

CODING_OS_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_ROOT="${PWD}"

echo "Installing coding-os Cursor adapter..."
echo "  Project: $PROJECT_ROOT"
echo "  coding-os: $CODING_OS_ROOT"

# 1-8. Common install steps (shared with claude / codex).
bash "${CODING_OS_ROOT}/core/scripts/install-adapter.sh" \
  --adapter cursor --agent-dir .cursor \
  --coding-os-root "$CODING_OS_ROOT" --project-root "$PROJECT_ROOT"

# 9. .cursor/hooks.json from registry-rendered template.
TEMPLATE="${CODING_OS_ROOT}/adapters/cursor/hooks.cursor.template.json"
HOOKS_ABS="${PROJECT_ROOT}/.cursor/hooks"
HOOKS_ESCAPED=$(printf '%s' "$HOOKS_ABS" | sed 's/[&|]/\\&/g')
sed "s|{{HOOKS_DIR}}|${HOOKS_ESCAPED}|g" "$TEMPLATE" > "${PROJECT_ROOT}/.cursor/hooks.json"

# 10. .cursor/mcp.json — register coding-os MCP server entry.
MCP_FILE="${PROJECT_ROOT}/.cursor/mcp.json"
if [[ ! -f "$MCP_FILE" ]]; then
  cat > "$MCP_FILE" << 'MCPEOF'
{
  "mcpServers": {}
}
MCPEOF
fi

python3 -c "
import json, shutil
mcp_path = '${MCP_FILE}'
cos_root = '${CODING_OS_ROOT}'
cos_bin = shutil.which('cos')
with open(mcp_path) as f:
    data = json.load(f)
data.setdefault('mcpServers', {})
if cos_bin:
    data['mcpServers']['coding-os'] = {
        'command': cos_bin,
        'args': ['server-start'],
    }
else:
    data['mcpServers']['coding-os'] = {
        'command': 'uv',
        'args': ['run', '--directory', f'{cos_root}/core/thinking_os', 'python', 'server.py'],
        'cwd': '\${workspaceFolder}'
    }
with open(mcp_path, 'w') as f:
    json.dump(data, f, indent=2)
" 2>/dev/null || echo "  WARN: Could not update .cursor/mcp.json automatically"

echo ""
echo "Cursor adapter installed successfully."
echo "  Hooks:    .cursor/hooks.json (generated)"
echo "  MCP:      .cursor/mcp.json (updated)"
