#!/usr/bin/env bash
# SessionStart hook: probe the coding-os MCP server, warn if down.
#
# Rationale: without a live MCP, the entire thinking-os layer is dead —
# memory search, task-sync, learning, breakthrough capture, doc-search
# all silently fail. The agent and the human have no visible signal
# unless they happen to call an MCP tool and see the error.
#
# This hook runs once per session, reads the launch command from the
# active agent config (.mcp.json for Claude, .codex/config.toml for
# Codex, then user-level Codex config as a fallback), attempts an
# initialize handshake (5s timeout), and on failure prints a loud
# banner so both sides know memory is unavailable.
#
# Fast-path: if .mcp.json has no coding-os entry, the session simply
# doesn't use MCP — silent exit.
set -euo pipefail

# Find the project root by walking up from this hook. The hook lives at
# $PROJECT/.claude/hooks/ or $PROJECT/.codex/hooks/, so two levels up is
# the project root.
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$HOOK_DIR/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then
  cos_log_hook() { :; }
fi
PROJECT_ROOT="$(cd "$HOOK_DIR/../.." && pwd)"
cos_log_hook warn-mcp-down fire

MCP_FILE="$PROJECT_ROOT/.mcp.json"
CODEX_PROJECT_CONFIG="$PROJECT_ROOT/.codex/config.toml"
resolve_launch_from_mcp_json() {
  local mcp_file="${1:-}"
  [[ -f "$mcp_file" ]] || return 0
  grep -q '"coding-os"' "$mcp_file" 2>/dev/null || return 0
  python3 -c '
import json, shlex, sys
from pathlib import Path
try:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    entry = (data.get("mcpServers") or {}).get("coding-os") or {}
    cmd = entry.get("command")
    args = entry.get("args") or []
    if not cmd:
        raise SystemExit(0)
    parts = [cmd, *args]
    print(" ".join(shlex.quote(p) for p in parts))
except Exception:
    raise SystemExit(0)
' "$mcp_file"
}

resolve_launch_from_codex_config() {
  local config_file="${1:-}"
  [[ -f "$config_file" ]] || return 0
  python3 -c '
import re, shlex, sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r"(?ms)^\[mcp_servers\.coding-os\]\s*\n(?P<body>.*?)(?=^\[|\Z)", text)
if not match:
    raise SystemExit(0)
body = match.group("body")
cmd_match = re.search(r"(?m)^\s*command\s*=\s*\"([^\"]+)\"\s*$", body)
if not cmd_match:
    raise SystemExit(0)
args_match = re.search(r"(?ms)^\s*args\s*=\s*\[(.*?)\]\s*$", body)
args = []
if args_match:
    args = re.findall(r"\"((?:[^\"\\\\]|\\\\.)*)\"", args_match.group(1))
    args = [bytes(item, "utf-8").decode("unicode_escape") for item in args]
parts = [cmd_match.group(1), *args]
print(" ".join(shlex.quote(p) for p in parts))
' "$config_file"
}

LAUNCH="$(resolve_launch_from_mcp_json "$MCP_FILE")"
if [[ -z "$LAUNCH" ]]; then
  LAUNCH="$(resolve_launch_from_codex_config "$CODEX_PROJECT_CONFIG")"
fi
if [[ -z "$LAUNCH" ]]; then
  LAUNCH="$(resolve_launch_from_codex_config "${HOME}/.codex/config.toml")"
fi
if [[ -z "$LAUNCH" ]]; then
  cos_log_hook warn-mcp-down skip "reason=no_mcp_config"
  exit 0
fi

# Probe with a real initialize handshake. Any response containing
# `"jsonrpc"` + `"result"` within 5 seconds means the server is live.
HANDSHAKE='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"warn-mcp-down","version":"1"}}}'

RESULT=$(
  cd "$PROJECT_ROOT" || exit 0
  # perl has a portable timeout alarm on macOS where `timeout` is absent.
  (echo "$HANDSHAKE" | perl -e 'alarm 5; exec @ARGV' sh -c "$LAUNCH" 2>/dev/null) | head -c 4096
) || true

if echo "$RESULT" | grep -q '"jsonrpc"' && echo "$RESULT" | grep -q '"result"'; then
  # Server is live — silent success.
  cos_log_hook warn-mcp-down ok
  exit 0
fi

# Server is down → print a loud banner to stderr (visible to human in
# Claude Code) AND stdout (which SessionStart hooks inject into agent
# context so the agent knows memory is unavailable).
{
  echo ""
  echo "⚠️  ================================================================"
  echo "⚠️  MCP coding-os is DOWN this session"
  echo "⚠️  ================================================================"
  echo "⚠️  Memory, learning, task-sync, doc-search are ALL unavailable."
  echo "⚠️  The agent's cos_search / cos_task_* / cos_doc_search tools"
  echo "⚠️  will error or return empty. Observations won't be persisted."
  echo "⚠️"
  echo "⚠️  Diagnose:  cos doctor         (check C15 mcp_actually_launches)"
  echo "⚠️  Repair:    bash adapters/claude/install.sh     (Claude projects)"
  echo "⚠️             bash adapters/codex/install.sh      (Codex projects)"
  echo "⚠️             OR: uv tool install --force --editable <coding-os>"
  echo "⚠️  ================================================================"
  echo ""
} >&2

cat <<'STDOUT'
[coding-os status] MCP server is unreachable this session.
  The thinking-os layer (memory / learning / task-sync / doc-search) is
  disabled. Proceed with caution — patterns won't be retrieved and
  observations won't be recorded. Run `cos doctor` for diagnosis.
STDOUT
cos_log_hook warn-mcp-down warn "launch=${LAUNCH}"

# Exit 0 — SessionStart hooks should never block session creation.
exit 0
