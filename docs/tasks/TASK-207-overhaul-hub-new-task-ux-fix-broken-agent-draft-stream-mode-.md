---
id: TASK-207
title: "Overhaul Hub new-task UX: fix broken agent-draft stream, mode-chooser, responsive modals, a11y"
swimlane: core
kind: feature
epic: agent-hub
labels: [ready]
status: in_progress
priority: P1
appetite: "1d"
created: 2026-06-06
started: 2026-06-05
completed: null
agent_session: ses-claude-20260605-183120-db30
depends_on: []
blocked_by: []
references: []
---
# TASK-207: Overhaul Hub new-task UX: fix broken agent-draft stream, mode-chooser, responsive modals, a11y

**Outcome (one sentence):** The Hub new-task flow becomes customer-grade — clicking create first offers a clear agent-vs-manual choice (each with a one-line description); the agent-draft stream actually renders (fix the `content`-vs-`blocks` + missing-`type` SSE contract drift); modals are fluid (clamp/rem) so they fill a 4K screen and scale with Ctrl+zoom; the manual form is de-jargoned, grouped, and validated; and modals get dialog a11y (role/ESC/focus/aria-live) + human empty/loading copy.

## Read First
- docs/engineering/agent-hub-orchestration.md
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx (CreateTaskModal, AgentTaskModal, TaskDetailDrawer)
- src/core/web/routes/cognition.py (`_safe_serialize`, `chat_new`, `author_task`)
- src/core/rules/api-contract-discipline.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a non-developer opens the board and clicks "new"
- **When** they pick "let an agent draft it", type a prompt, and submit
- **Then** the modal streams visible draft text + the created TASK-id (SSE `content`/`type` fixed); the entry first shows a clear agent-vs-manual chooser (each with a one-line description), not a hidden ghost button; the manual form shows 2 required fields with the rest under an optional "Details" group and disabled-until-valid submit; all modals are fluid (fill a 4K screen, scale with Ctrl+zoom); modals carry role="dialog"/ESC/focus-return/aria-live; `tsc` + `make ui-build` + the cognition web tests are green.

## Source
Findings + plan from the read-only review workflow (wf_5e36d619-026): API-contract drift in `_safe_serialize` (asdict pre-flattens nested blocks → no `type`; modal reads `blocks` not `content`); fixed-px modal widths outside the zoom layer; ghost agent button; jargon copy; no dialog a11y.

## Work Log
- 2026-06-06 [claude]: G1 agent-draft stream fixed: _safe_serialize now recurses field-by-field (getattr over dataclasses.fields) so nested Ass
- 2026-06-06 [claude]: committed c240206b: src/core/web/routes/cognition.py, src/core/web/ui/src/features/cognition/NewChatForm.tsx, src/core/w
- 2026-06-06 [claude]: G3 modals fluid: AgentTaskModal width clamp(34rem,50vw,60rem), CreateTaskModal clamp(40rem,62vw,80rem) + grid minmax(0,1
- 2026-06-06 [claude]: committed 5edf1efc: src/core/web/ui/src/features/cos-board/CosBoardPage.tsx
- 2026-06-06 [claude]: G2 customer-grade create flow: clicking new now shows a plain-language chooser first (✨ Let an AI draft it · recommended
- 2026-06-06 [claude]: committed eaa071b7: src/core/web/ui/src/features/cos-board/CosBoardPage.tsx
- 2026-06-06 [claude]: G4 a11y/robustness: all three create/agent modals get role=dialog + aria-modal + aria-label; ESC now closes CreateTaskMo
