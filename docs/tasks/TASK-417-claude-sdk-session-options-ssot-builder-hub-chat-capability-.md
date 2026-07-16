---
id: TASK-417
title: "Claude SDK session-options SSOT builder + Hub-chat capability/security parity (P1/P2/P3)"
swimlane: infra
kind: refactor
epic: null
labels: [ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-15
started: 2026-06-15
completed: 2026-06-15
agent_session: ses-claude-20260614-214422-d991
depends_on: []
blocked_by: []
references: []
---
# TASK-417: Claude SDK session-options SSOT builder + Hub-chat capability/security parity (P1/P2/P3)

ature
# TASK-417: Claude SDK session-options SSOT builder + Hub-chat capability/security parity (P1/P2/P3)

**Outcome (one sentence):** All Claude SDK sessions construct ClaudeAgentOptions via ONE claude_session_options() builder in src/adapters/claude/, loaded by core via the existing dynamic adapter-load seam (also fixing P4 layering); Hub chat registers cos_* via programmatic mcp_servers (read from .mcp.json) and applies the destructive-Bash deny floor — closing the capability gap (P2) and the security blocker (P3). Works in peace with concurrent TASK-416: only clean files are touched (cognition.py, sdk_dispatcher.py, new builder); its dirty set (adapter.yaml, update_mcp_json.py, presence_write.py, claude-sdk.md, presence.py) is left untouched.

## Acceptance

**Given** the Hub chat profile,
**When** chat_new and chat_send build options via claude_session_options,
**Then** the options carry mcp_servers(coding-os) + allowed_tools including mcp__coding-os__* + disallowed_tools including the destructive-bash floor; a new tests/test_session_options_parity.py asserts these per profile; `uv run pytest tests/test_chat_new_route.py tests/test_claude_dispatcher_options.py -q` passes.

## Read First
- src/core/web/routes/cognition.py
- src/adapters/claude/sdk_dispatcher.py
- src/core/thinking_os/dispatcher.py
- .mcp.json

## Work Log
- 2026-06-15 [claude]: Builder designed + spec doc written (docs/adapters/session-options-builder.md, untracked); gate+doc-anchor+skills set. P
- 2026-06-15 [claude]: Edit sdk_probe.py
- 2026-06-15 [claude]: Edit sdk_probe2.py
- 2026-06-15 [claude]: Edit sdk_probe3.py
- 2026-06-15 [claude]: Edit web-sdk-chat-parity-rootcause.md
- 2026-06-15 [claude]: Edit sdk_dispatcher.py
- 2026-06-15 [claude]: Edit cognition.py
- 2026-06-15 [claude]: Edit cognition.py
- 2026-06-15 [claude]: Edit cognition.py
- 2026-06-15 [claude]: Edit test_session_options_parity.py
- 2026-06-15 [claude]: Edit test_chat_new_route.py
- 2026-06-15 [claude]: Edit test_chat_new_route.py
- 2026-06-15 [claude]: Edit test_chat_new_route.py
- 2026-06-15 [claude]: Chunk 1 (P1/P2/P3) LANDED in commit 780536e8. claude_session_options() builder added to sdk_dispatcher.py (chat/chat_res
