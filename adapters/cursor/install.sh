#!/usr/bin/env bash
# Cursor adapter installer for coding-os — native `.cursor/hooks.json` + project MCP.
set -euo pipefail

CODING_OS_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_ROOT="${PWD}"

echo "Installing coding-os Cursor adapter..."
echo "  Project: $PROJECT_ROOT"
echo "  coding-os: $CODING_OS_ROOT"

mkdir -p "${PROJECT_ROOT}/.cursor/hooks"
mkdir -p "${PROJECT_ROOT}/.cursor/rules"
mkdir -p "${PROJECT_ROOT}/.cursor/skills"
mkdir -p "${PROJECT_ROOT}/.cursor/commands"
mkdir -p "${PROJECT_ROOT}/.coding-os"

echo "cursor" > "${PROJECT_ROOT}/.coding-os/.agent" 2>/dev/null || true

# 1) Core hooks
for hook in "${CODING_OS_ROOT}/core/hooks/"*.sh; do
  [ -e "$hook" ] || continue
  name=$(basename "$hook")
  ln -sf "$hook" "${PROJECT_ROOT}/.cursor/hooks/${name}"
done

# 2) Cursor adapter dispatchers
if [ -d "${CODING_OS_ROOT}/adapters/cursor/hooks" ]; then
  for hook in "${CODING_OS_ROOT}/adapters/cursor/hooks/"*.sh; do
    [ -e "$hook" ] || continue
    name=$(basename "$hook")
    ln -sf "$hook" "${PROJECT_ROOT}/.cursor/hooks/${name}"
  done
fi

# 3) Rules
for rule in "${CODING_OS_ROOT}/core/rules/"*.md; do
  [ -e "$rule" ] || continue
  name=$(basename "$rule")
  ln -sf "$rule" "${PROJECT_ROOT}/.cursor/rules/${name}"
done

# 4) Skills
for skill_dir in "${CODING_OS_ROOT}/core/skills/"*/; do
  [ -e "$skill_dir" ] || continue
  name=$(basename "$skill_dir")
  mkdir -p "${PROJECT_ROOT}/.cursor/skills/${name}"
  if [ -f "${skill_dir}SKILL.md" ]; then
    ln -sf "${skill_dir}SKILL.md" "${PROJECT_ROOT}/.cursor/skills/${name}/SKILL.md"
  fi
done

MANIFEST="${PROJECT_ROOT}/.coding-os/installed-manifest.json"
LINKER="${CODING_OS_ROOT}/core/scripts/link-stack-skills.sh"
if [ -f "$MANIFEST" ] && [ -x "$LINKER" ]; then
  STACKS=$(python3 -c "import json,sys; m=json.load(open('$MANIFEST')); print(' '.join(m.get('templates',[])))" 2>/dev/null || true)
  if [ -n "$STACKS" ]; then
    bash "$LINKER" "${PROJECT_ROOT}/.cursor/skills" "${CODING_OS_ROOT}" $STACKS 2>/dev/null || true
    echo "  Re-linked stack skills: $STACKS"
  fi
fi

# 5) Commands
if [ -d "${CODING_OS_ROOT}/core/commands" ]; then
  for cmd in "${CODING_OS_ROOT}/core/commands/"*.md; do
    [ -e "$cmd" ] || continue
    name=$(basename "$cmd")
    ln -sf "$cmd" "${PROJECT_ROOT}/.cursor/commands/${name}"
  done
fi

# 5b) Formula commands
AGENTS_DIR="${CODING_OS_ROOT}/core/thinking_os/agents"
if [ -d "$AGENTS_DIR" ]; then
  for agent in "$AGENTS_DIR"/F*.md; do
    [ -e "$agent" ] || continue
    fname=$(basename "$agent")
    num=$(echo "$fname" | sed 's/F\([0-9]*\)_.*/\1/')
    ln -sf "$agent" "${PROJECT_ROOT}/.cursor/commands/formula-f${num}.md"
  done
fi

# 6) hooks.json from template
TEMPLATE="${CODING_OS_ROOT}/adapters/cursor/hooks.cursor.template.json"
HOOKS_ABS="${PROJECT_ROOT}/.cursor/hooks"
HOOKS_ESCAPED=$(printf '%s' "$HOOKS_ABS" | sed 's/[&|]/\\&/g')
sed "s|{{HOOKS_DIR}}|${HOOKS_ESCAPED}|g" "$TEMPLATE" > "${PROJECT_ROOT}/.cursor/hooks.json"

# 7) mcp.json
MCP_FILE="${PROJECT_ROOT}/.cursor/mcp.json"
if [ ! -f "$MCP_FILE" ]; then
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
echo "Cursor adapter installed successfully!"
echo "  Hooks:    .cursor/hooks/ (symlinked)"
echo "  Rules:    .cursor/rules/ (symlinked)"
echo "  Skills:   .cursor/skills/ (symlinked)"
echo "  Commands: .cursor/commands/ (symlinked)"
echo "  Hooks:    .cursor/hooks.json (generated)"
echo "  MCP:      .cursor/mcp.json (updated)"
