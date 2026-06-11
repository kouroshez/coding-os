#!/usr/bin/env bash
# SessionStart hook: probe the coding-os MCP server, warn if down.
#
# Rationale: without a live MCP, the entire thinking_os layer is dead —
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

# Debounce the heavy spawn-probe: this hook fires on every
# SessionStart — startup AND compact AND resume. Each probe spawns the full
# MCP server for one initialize handshake; re-spawning it on every compaction
# of a long session is wasteful. The MCP server is agent-shared, so a recent
# successful probe is trusted across panels. Override: COS_MCP_PROBE_TTL (s).
_PROBE_MARKER="${COS_AGENT_DIR:-${COS_STATE_DIR:-.coding-os}/claude}/.mcp-probe-ok"
if [[ -f "$_PROBE_MARKER" ]]; then
  _probe_mtime=$(stat -f %m "$_PROBE_MARKER" 2>/dev/null || stat -c %Y "$_PROBE_MARKER" 2>/dev/null || echo 0)
  if [[ $(( $(date +%s) - _probe_mtime )) -lt "${COS_MCP_PROBE_TTL:-600}" ]]; then
    cos_log_hook warn-mcp-down skip "reason=recent_probe_ok"
    exit 0
  fi
fi

MCP_FILE="$PROJECT_ROOT/.mcp.json"
CODEX_PROJECT_CONFIG="$PROJECT_ROOT/.codex/config.toml"
resolve_launch_from_mcp_json() {
  local mcp_file="${1:-}"
  [[ -f "$mcp_file" ]] || return 0
  command grep -q '"coding-os"' "$mcp_file" 2>/dev/null || return 0
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
# `"jsonrpc"` + `"result"` means the server is live. 6s alarm + one retry:
# the old 2s single-shot raced the SessionStart burst (hub boot + 20 hooks
# + uv resolve) and branded a healthy server DOWN for the whole session,
# pushing the agent off MCP retrieval into raw-read token burn (TASK-344).
HANDSHAKE='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"warn-mcp-down","version":"1"}}}'

for _attempt in 1 2; do
  RESULT=$(
    cd "$PROJECT_ROOT" || exit 0
    # perl has a portable timeout alarm on macOS where `timeout` is absent.
    (echo "$HANDSHAKE" | perl -e 'alarm 6; exec @ARGV' sh -c "$LAUNCH" 2>/dev/null) | head -c 4096
  ) || true
  if echo "$RESULT" | command grep -q '"jsonrpc"' && echo "$RESULT" | command grep -q '"result"'; then
    # Server is live — silent success. Stamp the probe marker so the next
    # compact/resume within COS_MCP_PROBE_TTL skips the heavy re-spawn.
    mkdir -p "$(dirname "$_PROBE_MARKER")" 2>/dev/null || true
    : > "$_PROBE_MARKER" 2>/dev/null || true
    cos_log_hook warn-mcp-down ok
    exit 0
  fi
  [[ "$_attempt" == "1" ]] && sleep 2
done

# Server is down → print a loud banner to stderr (visible to human in
# Claude Code) AND stdout (which SessionStart hooks inject into agent
# context so the agent knows memory is unavailable).
{
  echo ""
  echo "⚠️  ================================================================"
  echo "⚠️  MCP coding-os is DOWN this session"
  echo "⚠️  ================================================================"
  echo "⚠️  Memory, learning, task-sync, doc-search are LIKELY unavailable."
  echo "⚠️  The agent's cos_search / cos_task_* / cos_doc_search tools"
  echo "⚠️  may error or return empty. Observations may not be persisted."
  echo "⚠️"
  echo "⚠️  AGENT: this probe spawns a THROWAWAY server and can false-negative"
  echo "⚠️  under SessionStart load — your session's own MCP connection may be"
  echo "⚠️  fine. VERIFY with one real call (ToolSearch select:cos_health →"
  echo "⚠️  cos_health) before treating MCP as down for the session."
  echo "⚠️"
  echo "⚠️  Diagnose:  cos doctor         (check C15 mcp_actually_launches)"
  echo "⚠️  Repair:"
  # Data-driven: list every adapter that ships an install.sh under
  # src/adapters/<id>/. New adapters added tomorrow appear here automatically;
  # no source edits required. Falls back to a generic line if the meta
  # repo can't be located (consumer projects without the live tree).
  _META_ROOT="${COS_ROOT:-}"
  if [[ -z "$_META_ROOT" ]] || [[ ! -d "$_META_ROOT/adapters" ]]; then
    # Best-effort: walk up from this hook script's physical location.
    _src="${BASH_SOURCE[0]}"
    while [ -L "$_src" ]; do
      _dir="$(cd -P "$(dirname "$_src")" && pwd)"
      _src="$(readlink "$_src")"
      [[ "$_src" != /* ]] && _src="$_dir/$_src"
    done
    _META_ROOT="$(cd -P "$(dirname "$_src")/../.." && pwd 2>/dev/null || true)"
    unset _src _dir
  fi
  if [[ -d "$_META_ROOT/adapters" ]]; then
    for _adapter_yml in "$_META_ROOT"/adapters/*/adapter.yaml; do
      [[ -f "$_adapter_yml" ]] || continue
      _adapter_dir="$(dirname "$_adapter_yml")"
      _adapter="$(basename "$_adapter_dir")"
      [[ -f "$_adapter_dir/install.sh" ]] || continue
      printf "⚠️             bash adapters/%s/install.sh\n" "$_adapter"
    done
    unset _adapter_yml _adapter_dir _adapter
  else
    echo "⚠️             bash <adapter>/install.sh   (one per adapter under adapters/)"
  fi
  unset _META_ROOT
  echo "⚠️             OR: uv tool install --force --editable <coding-os>"
  echo "⚠️  ================================================================"
  echo ""
} >&2

cat <<'STDOUT'
[coding-os status] MCP server is unreachable this session.
  The thinking_os layer (memory / learning / task-sync / doc-search) is
  disabled. Proceed with caution — patterns won't be retrieved and
  observations won't be recorded. Run `cos doctor` for diagnosis.
STDOUT
cos_log_hook warn-mcp-down warn "launch=${LAUNCH}"

# Exit 0 — SessionStart hooks should never block session creation.
exit 0
