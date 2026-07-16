---
id: TASK-253
title: "Command palette (Cmd/Ctrl+K) jump-to"
swimlane: core
kind: feature
epic: hub-redesign
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-08
started: 2026-06-08
completed: 2026-06-08
agent_session: ses-claude-20260608-024900-f2b0
depends_on: []
blocked_by: []
references: []
---
# TASK-253: Command palette (Cmd/Ctrl+K) jump-to

**Outcome (one sentence):** Add a Cmd/Ctrl+K command palette to jump to project/chat/task/trace.

## Read First
- src/core/web/ui/src/layout/AppShell.tsx — where the palette + global keybinding mount.
- src/core/web/ui/src/lib/use-scoped-link.ts — building project-scoped navigation targets.
- src/core/web/ui/src/components/Modal.tsx — reuse for the palette overlay.

## Context / Approach
Reserve Cmd/Ctrl+K. Open a palette (built on the shared Modal primitive) that searches projects + chat sessions + tasks + traces and navigates on select. The signature Linear/Vercel/Claude-desktop affordance. Ship project+session+task search first; full palette can fast-follow.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** Cmd/Ctrl+K is pressed, **When** received, **Then** the palette opens with focus in the input.
- **Given** the palette open, **When** a project/session/task is chosen, **Then** the app navigates there.

## Work Log
- 2026-06-08 [claude]: Added CommandPalette (Cmd/Ctrl+K) on shared Modal: fetches projects/tasks/chats on open, pure filterCommandItems, arrow+
