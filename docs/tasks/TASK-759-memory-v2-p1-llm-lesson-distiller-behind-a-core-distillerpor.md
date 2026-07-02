---
id: TASK-759
title: "memory-v2 P1: LLM lesson distiller behind a core DistillerPort with claude adapter implementation"
swimlane: core
kind: feature
epic: memory-v2
labels: [memory, ready]
status: icebox
priority: P1
appetite: 3d
created: 2026-07-02
started: null
completed: null
agent_session: null
depends_on: [TASK-758]
blocked_by: []
references: []
---

# TASK-759: memory-v2 P1: LLM lesson distiller behind a core DistillerPort with claude adapter implementation

**Outcome (one sentence):** Nightly learn_extract distills friction clusters into situation/action/why lessons via an adapter-provided LLM port (budget-capped, idempotent by cluster fingerprint) with heuristic fallback; distilled lessons are born volatile (conf=0.5) with provenance=llm_distilled and evidence refs.

## Read First
- docs/engineering/learning-extraction.md
- docs/adapters/claude-sdk.md
- docs/engineering/mcp-error-envelope.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a DB with >=1 friction cluster and the claude adapter available, **When** the learning loop runs, **Then** a lesson with cluster-specific action and evidence_refs exists (provenance=llm_distilled, confidence=0.5, tier != Trusted)
- **Given** no LLM auth/adapter, **When** the loop runs, **Then** the template fallback produces lessons and the nightly exits 0
- **Given** an unchanged cluster fingerprint, **When** the loop re-runs, **Then** no duplicate distillation call is made
- **Given** hook-log lines containing secrets, **When** distillation input is built, **Then** sanitization strips them before any LLM call

## Work Log
