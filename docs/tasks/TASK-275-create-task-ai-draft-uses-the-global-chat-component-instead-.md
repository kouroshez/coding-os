---
id: TASK-275
title: "Create-task AI-draft uses the global chat component instead of a bespoke composer"
swimlane: core
kind: feature
epic: hub-redesign
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-618-2ab7
depends_on: []
blocked_by: []
references: []
---
# TASK-275: Create-task AI-draft uses the global chat component instead of a bespoke composer

**Outcome (one sentence):** The board's "Draft with AI" path now mounts the one global chat component (NewChatForm) pointed at /api/cognition/author-task, so the AI-draft surface has the same composer, model picker, live streaming and styling as the main chat — one chat component, edited in one place.

## Read First
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx — AgentTaskModal (~2449), CreateTaskModal manual form (~2825)
- src/core/web/ui/src/features/cognition/NewChatForm.tsx — the global chat composer (props: endpoint, onComplete)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the board, **When** the user picks "Let an AI draft it", **Then** the modal renders NewChatForm (the global chat composer + live stream) targeting /api/cognition/author-task — not a one-off textarea/`<pre>`.
- **Given** the AI-draft modal, **When** it closes (esc / overlay / completion), **Then** the board list is invalidated so the freshly drafted task appears.
- **Given** the manual mode, **When** chosen, **Then** the existing template-driven form (title/swimlane/kind/priority/effort/labels/outcome) still works.

## Work Log
- 2026-06-08 [claude]: AgentTaskModal gutted from a bespoke textarea+model-select+`<pre>` composer to a thin shell that mounts NewChatForm (the
