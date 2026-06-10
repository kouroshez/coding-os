---
id: TASK-116
title: "B0: agent-memory + thinking_os tool-name drift fix + skill↔code drift-guard test"
swimlane: core
kind: bug
epic: skills-enterprise-hardening
labels: [skills, drift-guard, meta-authoring, audit, epic:skills-enterprise-hardening, ready]
status: complete
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
# TASK-116: B0: agent-memory + thinking_os tool-name drift fix + skill↔code drift-guard test

**Outcome (one sentence):** agent-memory + thinking_os document the REAL cos_* signatures (no invented kwargs/tool names); a CI drift-guard test imports the live server and asserts every skill-documented kwarg/category/import/tool-name exists, so meta-authoring skills cannot silently re-rot.

## Read First
- src/core/skills/agent-memory/SKILL.md
- src/core/skills/agent-memory/references/memory-recipes.md
- src/core/skills/agent-memory/scripts/check_observation.py
- src/core/thinking_os/server.py
- src/core/skills/thinking_os/SKILL.md
- docs/governance/mcp-tool-inventory.md

## Repro Steps
1. Open src/core/skills/agent-memory/SKILL.md → the "Record an observation" recipe shows `cos_observation_record(title=, body=, memory_type=, confidence=, impact_score=, tags_csv=, task_id=)`.
2. The real signature (src/core/thinking_os/server.py:539) is `cos_observation_record(file_path, tool_name="Edit")` — edit-derived, no freeform fields.
3. Calling the documented form raises InputValidationError on the first call. Same for cos_learn_extract/suggest/validate/feedback, cos_details, cos_timeline; thinking_os SKILL.md calls non-existent `thinking_os_search`/`thinking_os_details`.

Expected: every documented signature/tool-name matches the live server.
Actual: all memory/learning recipes use invented kwargs; agent following them fails on the first call.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the agent-memory and thinking_os skills document cos_* memory/learning tool usage
- **When** an agent follows any Write/Read/Learn recipe verbatim or invokes a named tool
- **Then** every documented kwarg, tool name, error category and import resolves against the live server (no InputValidationError / ModuleNotFoundError), the skills describe the real automatic-capture + learn-loop model (confidence is system-computed, not agent-set), and a CI drift-guard test fails if any future skill↔code drift is introduced.

## Work Log
- 2026-06-05 [claude]: B0a done (commit c021649): agent-memory rewritten to real cos_* signatures (edit-derived capture, system-computed confid
- 2026-06-05 [claude]: B0 complete. B0a c021649 (agent-memory real signatures), B0b 00cf2fe (thinking_os cos_search/cos_details + .claude/ lite
