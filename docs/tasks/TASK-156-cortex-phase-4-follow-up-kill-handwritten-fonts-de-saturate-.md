---
id: TASK-156
title: "Cortex Phase 4 follow-up — kill handwritten fonts + de-saturate domain tint; capture review roadmap"
swimlane: core
kind: refactor
epic: ui-design-system
labels: [ui, design-system, board, review, ready]
status: archive
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-156: Cortex Phase 4 follow-up — kill handwritten fonts + de-saturate domain tint; capture review roadmap

**Outcome (one sentence):** Remove the 11 remaining handwritten display fonts (Permanent Marker / Caveat / Kalam) in CosBoardPage → inherited Inter, and de-saturate the swimlane(domain) card body from alpha 0.55/0.32 to a subtle 0.16/0.07 tint — domain identity is carried by the 5px left rail + kind chip (color-namespace-separation rule), fixing the over-colored board (external review images 9-14). Extend docs/engineering/design-system.md with the validated cross-cutting rules from the external product/design review (separate color namespaces for status/domain/priority/agent; domain = rail/tint not full-fill; task + memory lifecycle vocabulary; IA sketch; canonical object contract) and log the larger multi-phase redesign as backlog tasks. make ui-build green.

## Read First
- src/core/web/ui/src/features/cos-board/CosBoardPage.tsx
- docs/engineering/design-system.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the board renders in dark mode (default)
- **When** lane headers, card titles and task cards paint
- **Then** no handwritten/cursive font remains anywhere in the app UI (all → inherited Inter), the swimlane(domain) card body is a subtle ≤0.16 tint with domain carried by the left rail + chip (not a saturated full fill), design-system.md documents the color-namespace-separation + domain-as-rail rules and the review roadmap is logged as backlog tasks, and `make ui-build` is green

Spec SSOT: [docs/engineering/design-system.md](../engineering/design-system.md)

## Work Log
- 2026-06-05 [claude]: Shipped (commit 94d3821): removed the last 11 handwritten fonts (Permanent Marker/Caveat/Kalam) in CosBoardPage → inheri
