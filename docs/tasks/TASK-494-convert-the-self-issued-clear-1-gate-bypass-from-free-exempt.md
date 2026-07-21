---
id: TASK-494
title: "Convert the self-issued CLEAR-1 gate-bypass from free exemption to a logged, justified, counted act"
swimlane: core
kind: feature
epic: teach-why-alignment
labels: [teach-why, hooks, gate, ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-21
started: 2026-06-20
completed: 2026-06-20
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-494: Convert the self-issued CLEAR-1 gate-bypass from free exemption to a logged, justified, counted act

**Outcome (one sentence):** A self-issued `CLEAR 1` (write-state.sh .thinking_os-gate "CLEAR 1") today lifts six gates at once on the agent's OWN unverified classification — enforce-doc-anchor, enforce-skill, enforce-task-start, enforce-memory-check, enforce-zoom, enforce-anti-ambiguity — and the BLOCK message literally prints the bypass command. Under goal/budget pressure the lowest-friction path is to self-exempt: this is the agentic-misalignment mechanism (recognize the rule, calculate bypass is efficient, proceed) and the constitution's "values merely imposed crack under pressure". Do NOT make the gate harder (over-blocking breeds worse evasions like mislabeling files). Instead change its character: require a one-line justification when the CLEAR-1 bypass is written, surface a running per-session count in the transparency banner (`bypasses=N`), and feed that count into retro. Make the cost VISIBLE, not the gate stricter.

## Read First
- src/core/hooks/enforce-doc-anchor.sh
- src/core/hooks/enforce-skill.sh
- src/core/hooks/write-state.sh
- src/core/hooks/session-context.sh
- src/core/rules/transparency-banner.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `write-state.sh .thinking_os-gate "CLEAR 1"` issued as a bypass, **When** it is written, **Then** a one-line justification is required and recorded.
- **Given** >=1 self-issued CLEAR-1 bypass in a session, **When** session-context.sh emits the banner, **Then** it shows `bypasses=N` and retro surfaces the count.
- **Given** the change set, **When** verifying, **Then** the gate is NOT made stricter (no new BLOCK introduced) and `make verify-hooks` is GREEN. Live-symlinked hooks edited atomically.

## Work Log
- 2026-06-21 [claude]: Edit write-state.sh
- 2026-06-21 [claude]: Edit session-context.sh
- 2026-06-21 [claude]: Edit enforce-doc-anchor.sh
- 2026-06-21 [claude]: Edit enforce-task-start.sh
- 2026-06-21 [claude]: Edit enforce-memory-check.sh
- 2026-06-21 [claude]: Edit transparency-banner.md
- 2026-06-21 [claude]: Edit retro.md
- 2026-06-21 [claude]: Edit retro.md
- 2026-06-21 [claude]: commit 59c1c0424d — feat(core): make self-issued CLEAR-1 gate bypass logged, counted, and surfaced
- 2026-06-21 [claude]: write-state.sh now appends each self-issued 'CLEAR 1' gate write + its justification to per-session…
