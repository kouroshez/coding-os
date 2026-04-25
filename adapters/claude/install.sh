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
  STACKS=$(MANIFEST="$MANIFEST" python3 - <<'PY' 2>/dev/null || true
import json, os, sys
try:
    with open(os.environ["MANIFEST"]) as f:
        data = json.load(f)
    print(" ".join(data.get("templates", [])))
except Exception as exc:
    sys.stderr.write(f"manifest parse error: {exc}\n")
    sys.exit(1)
PY
)
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

# Add thinking-os MCP server entry using Python (safe JSON manipulation).
# Portable entry: `cos server-start` resolves the coding-os location at
# runtime via whichever `cos` binary is on PATH. If `cos` is not on PATH
# yet, fall back to the absolute `uv run` form so the project still works
# before the user installs the CLI.
#
# Inputs are passed via env vars (not interpolated into the Python literal)
# so paths containing single quotes do not break parsing or risk injection.
MCP_FILE="$MCP_FILE" CODING_OS_ROOT="$CODING_OS_ROOT" python3 - <<'PY' || echo "  WARN: Could not update .mcp.json automatically (see error above)"
import json, os, shutil, sys
mcp_path = os.environ["MCP_FILE"]
cos_root = os.environ["CODING_OS_ROOT"]
has_cos = shutil.which("cos") is not None
try:
    with open(mcp_path) as f:
        data = json.load(f)
except json.JSONDecodeError as exc:
    sys.stderr.write(f"  ERROR: {mcp_path} is not valid JSON: {exc}\n")
    sys.exit(1)
data.setdefault("mcpServers", {})
if has_cos:
    data["mcpServers"]["coding-os"] = {
        "command": "cos",
        "args": ["server-start"],
    }
else:
    data["mcpServers"]["coding-os"] = {
        "command": "uv",
        "args": ["run", "--directory", f"{cos_root}/core/thinking_os", "python", "server.py"],
        "cwd": "${workspaceFolder}",
    }
with open(mcp_path, "w") as f:
    json.dump(data, f, indent=2)
PY

# 7. Symlink commands
COMMANDS_DIR="${CODING_OS_ROOT}/core/commands"
if [ -d "$COMMANDS_DIR" ]; then
  mkdir -p "${PROJECT_ROOT}/.claude/commands"
  for cmd in "${COMMANDS_DIR}/"*.md; do
    name=$(basename "$cmd")
    ln -sf "$cmd" "${PROJECT_ROOT}/.claude/commands/${name}"
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
