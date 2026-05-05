"""Probe `_detect_agent_session_default` to verify the H-bug fix.

PURPOSE: Confirm the new MCP-side helper returns a non-NULL session id
under the same env that runs the live Claude CLI. Source-of-truth doc:
docs/adapters/claude-deepening-checklist.md.
INPUT:   none — reads CLAUDECODE / CLAUDE_AGENT_SDK_VERSION /
         CLAUDE_PROJECT_DIR / COS_AGENT_DIR.
OUTPUT:  Resolved session id or "(unresolved)".
DEPENDENCIES: core/thinking_os imported via PYTHONPATH (uv editable install).
NOTES:   Run after restarting the MCP server / Claude CLI so the running
         server has the new code.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, "core/thinking_os")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "_qdeep_server_probe", "core/thinking_os/server.py"
)
mod = importlib.util.module_from_spec(spec)
# server.py expects CWD/parent paths set; just exec the helper section.
import re
src = open("core/thinking_os/server.py").read()
match = re.search(
    r"def _detect_agent_session_default\(\)[\s\S]+?    return f\"ses-\{agent\}-mcp-\{_os.getpid\(\)\}\"",
    src,
)
if not match:
    raise RuntimeError("helper not found in server.py")
ns: dict = {}
exec(match.group(0), ns)
_detect_agent_session_default = ns["_detect_agent_session_default"]  # noqa: E402

resolved = _detect_agent_session_default()
print(f"resolved session-id: {resolved!r}")
print()
print("relevant env:")
for key in (
    "COS_AGENT_SESSION_ID", "COS_AGENT_DIR", "COS_AGENT", "COS_STATE_DIR",
    "CLAUDECODE", "CLAUDE_AGENT_SDK_VERSION", "CLAUDE_CODE_SSE_PORT",
    "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_PROJECT_DIR",
    "CURSOR_TRACE_ID", "CODEX_PROJECT_DIR",
):
    val = os.environ.get(key)
    if val is not None:
        print(f"  {key}={val!r}")
