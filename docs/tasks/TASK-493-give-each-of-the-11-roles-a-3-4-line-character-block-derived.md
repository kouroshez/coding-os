---
id: TASK-493
title: "Give each of the 11 roles a 3-4 line Character block derived from the Constitution"
swimlane: "thinking_os"
kind: feature
epic: teach-why-alignment
labels: [teach-why, roles, persona, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-21
started: 2026-06-20
completed: 2026-06-20
agent_session: ses-claude-20260620-185936-c751
depends_on: [TASK-491]
blocked_by: []
references: []
---
# TASK-493: Give each of the 11 roles a 3-4 line Character block derived from the Constitution

**Outcome (one sentence):** The 11 role personas (src/core/thinking_os/agents/*.md) are pure job-descriptions + a few MUST-NOTs — no character. Per persona-selection, alignment lives at the character layer and behaviors are downstream; a persona defined only by tasks+prohibitions generalizes like a rule list, so a composed sub-session hitting an uncovered situation has no values to reason from. Add a short '## Character' block (<=4 lines) to each agent.md stating the value the role embodies and why it serves the user (implementer: "smallest correct change, because every line is a liability future maintainers carry"; reviewer: "independent verification, because authors cannot see their own blind spots"; security_auditor: "assume breach, value the user's trust over shipping speed"). Each line derives from constitution.md (one source -> P1). Prose-only via the existing load_agent_prompt path — no schema/yaml-key change, hard 4-line cap to protect the token budget.

## Read First
- docs/governance/constitution.md
- src/core/thinking_os/agents/implementer.md
- src/core/thinking_os/agents/reviewer.md
- src/core/thinking_os/presets/registry.yaml
- docs/adapters/claude-sdk.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** each of the 11 src/core/thinking_os/agents/*.md, **When** reviewed, **Then** it has a '## Character' block <=4 lines, each line traceable to a constitution value.
- **Given** a composed role chain, **When** prompts load via load_agent_prompt, **Then** no new YAML key is introduced and the Character prose loads via the existing path.
- **Given** the change set, **When** verifying, **Then** `uv run --extra rag pytest src/core/thinking_os/tests/ -q -m 'not slow'` + `python src/core/thinking_os/server.py --test` are GREEN.

## Work Log
- 2026-06-21 [claude]: commit 954693300d — feat(thinking_os): give each role a Character block (values derived from the Constitution)
- 2026-06-21 [claude]: Added a <=4-line '## Character' block to all 12 cognitive role files (analyst..security_auditor) via an idempotent…
