---
id: TASK-283
title: "Hub chat panel: fix resume tool-permission errors, light-mode code blocks, duplicate message, empty live bubbles"
swimlane: core
kind: bug
epic: hub-redesign
labels: [hub, chat, ui, ready]
status: archive
priority: P1
appetite: 1d
created: 2026-06-09
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260609-151118-a8c3
depends_on: []
blocked_by: []
references: []
---
# TASK-283: Hub chat panel: fix resume tool-permission errors, light-mode code blocks, duplicate message, empty live bubbles

**Outcome (one sentence):** Resuming a chat in the Hub runs tools without permission errors, code/diff blocks are readable in light theme, the user message is not duplicated during streaming, and no empty assistant·live bubbles render.

## Read First
- src/core/web/routes/cognition.py
- src/core/web/ui/src/features/cognition/ChatView.tsx
- src/core/web/ui/src/components/MarkdownBlock.tsx
- docs/engineering/hub-architecture.md

## Repro Steps
1. Open the Hub (`http://127.0.0.1:9188`), open an existing chat session and send a follow-up that asks the agent to edit a file.
2. Observe: every Write/Edit tool returns "Claude requested permissions to write … but you haven't granted it yet" (A).
3. Switch the Hub to light theme; observe fenced code/diff blocks render light text on a near-white background, unreadable (B).
4. While the reply streams, observe the just-sent user message appears twice — once as a persisted turn, once as the live echo (C).
5. Observe an empty "assistant · live" bubble with no content while streaming (D).
Expected: tools run, code blocks are readable in both themes, the message shows once, no empty bubbles.
Actual: tool permission errors, unreadable light-mode code, duplicate message, empty bubbles.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a resumed Hub chat session, **When** the agent calls Write/Edit/Bash, **Then** it runs without a permission error (chat_send sets `permission_mode="dontAsk"` like chat_new/onboard).
- **Given** the Hub in light theme, **When** the assistant reply contains a fenced code or diff block, **Then** the block is readable (dark-pinned surface so the github-dark token palette has correct contrast).
- **Given** a streaming reply, **When** the 2s transcript poll surfaces the new user turn, **Then** the user message renders exactly once (polling paused while streaming).
- **Given** a content-less SDK message (system/result), **When** the live or persisted turn list renders, **Then** no empty assistant bubble appears.

## Work Log
- 2026-06-09 [claude]: Fixed 5 Hub-chat bugs: (A) chat_send resume now sets permission_mode=dontAsk so Write/Edit/Bash run; (B) pinned code-blo
