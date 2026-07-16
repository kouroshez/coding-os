---
id: TASK-176
title: "Harden compress.py to preserve symbols verbatim and stamp provenance on generated memory"
swimlane: core
kind: bug
epic: agent-economy
labels: [ready]
status: archive
priority: P2
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-176: Harden compress.py to preserve symbols verbatim and stamp provenance on generated memory

**Outcome (one sentence):** compress.py preserves identifiers/symbols/paths verbatim and forbids invention in the Haiku prompt, and stamps a _generated_by provenance marker on generated facts so cos_search consumers know the narrative is machine-derived.

## Read First

- docs/engineering/agent-economy-and-identity-roadmap.md (B2)
- src/core/thinking_os/compress.py
- src/core/thinking_os/tools/memory.py (cos_search reads narrative/concepts)

## Repro Steps

1. Inspect _call_claude_api in compress.py: the prompt says "infer from file paths" and sets narrative/facts/concepts with no instruction to preserve the Title's symbols and no provenance.
2. A Haiku summary can drop or rename an identifier from the Title or invent a fact; cos_search matches on narrative/concepts, so the hallucination surfaces to future sessions as ground truth with no signal it was machine-generated.

## Acceptance

- **Given** the compress prompt builder and response handler,
- **When** a summary is generated,
- **Then** the prompt instructs verbatim preservation of all Title symbols and forbids invention (faithful fallback to the Title), and the stored facts carry a _generated_by marker; a unit test asserts both without an API call.

## Work Log
- 2026-06-05 [claude]: Status transitioned to complete via cos task-done.
