#!/usr/bin/env python3
"""Probe server.py's _detect_agent_session_default() in isolation.

PURPOSE:      Resolve and print the agent session-id the MCP server would
              derive under the current process env, WITHOUT booting the server
              (which has import side effects). Used to debug agent-session
              attribution. SSOT: docs/adapters/claude-deepening-checklist.md.
INPUT:        none — reads the live process environment.
OUTPUT:       resolved session-id + the relevant env vars, to stdout.
DEPENDENCIES: src/core/thinking_os/server.py (the helper is regex-extracted).
NOTES:        Runs from any cwd (paths anchored on __file__). The helper is
              exec'd in an isolated namespace with os aliased as `_os` (the
              name server.py uses), so no server-module import is triggered.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SERVER = ROOT / "src" / "core" / "thinking_os" / "server.py"

if not SERVER.exists():
    sys.exit(f"server.py not found at {SERVER}")

src = SERVER.read_text(encoding="utf-8")
match = re.search(
    r"def _detect_agent_session_default\(\)[\s\S]+?    return f\"ses-\{agent\}-mcp-\{_os.getpid\(\)\}\"",
    src,
)
if not match:
    raise RuntimeError("helper _detect_agent_session_default not found in server.py")

ns: dict = {"_os": os}  # server.py references the stdlib os module as `_os`
exec(match.group(0), ns)
_detect_agent_session_default = ns["_detect_agent_session_default"]

resolved = _detect_agent_session_default()
print(f"resolved session-id: {resolved!r}")
print()
print("relevant env:")
for key in (
    "COS_AGENT_SESSION_ID",
    "COS_AGENT_DIR",
    "COS_AGENT",
    "COS_STATE_DIR",
    "CLAUDECODE",
    "CLAUDE_AGENT_SDK_VERSION",
    "CLAUDE_CODE_SSE_PORT",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_PROJECT_DIR",
    "CURSOR_TRACE_ID",
    "CODEX_PROJECT_DIR",
):
    val = os.environ.get(key)
    if val is not None:
        print(f"  {key}={val!r}")
