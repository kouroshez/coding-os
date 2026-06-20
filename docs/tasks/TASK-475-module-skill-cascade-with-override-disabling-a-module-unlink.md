---
id: TASK-475
title: "Module\u2192skill cascade-with-override \u2014 disabling a module unlinks its skills (owner decision, pass-4 \u00a78.5)"
swimlane: infra
kind: feature
epic: null
labels: [modularity, skills, audit-pass4, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-20
started: 2026-06-20
completed: 2026-06-20
agent_session: ses-claude-20260620-015545-0bbe
depends_on: []
blocked_by: []
references: []
---
# TASK-475: Module→skill cascade-with-override — disabling a module unlinks its skills (owner decision, pass-4 §8.5)

**Outcome (one sentence):** Disabling a module unlinks its declared skills by default (no more graph-explorer skill stranded when graph is off — the P4-14 trap), while each skill stays independently re-enableable (preserves Q1-HYBRID). subsystems.yaml gains an optional per-module `skills:` field (data-driven, like hooks:/tools:); toggle reuses remove-stack's skill-unlink + AGENTS.md-mention strip with ref-counting so a skill shared by two enabled modules is never unlinked; re-enabling a module relinks its skills unless the user explicitly disabled one; interactive confirm in TTY/panel + a `--keep-skills` headless escape hatch.

## Read First
- docs/engineering/modularity-audit-2026-06.md
- src/core/subsystems.yaml
- src/cli/subsystems.py
- src/cli/remove_stack.py
- src/cli/skill_commands.py
- src/cli/module_commands.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a module with declared skills (e.g. graph→[graph-explorer]) enabled on a real consumer **When** `cos module disable graph` runs **Then** graph-explorer's SKILL.md symlink is unlinked, recorded in disabled_skills, and its AGENTS.md mention is stripped — AND a skill shared by another ENABLED module is NOT unlinked (ref-counted) — AND `cos skill enable graph-explorer` re-adds it independently — AND re-enabling graph relinks its skills except any the user explicitly disabled — AND kernel/always-on skills (clean-code, thinking_os, search) are never module-owned — AND TTY prompts to confirm while `--keep-skills` / non-TTY skips the prompt; AND module/cli matrix + test_modularity_toggle suites pass; AND doctor flags a module-disabled-but-skill-present drift.

## Work Log
- 2026-06-20 [claude]: Edit modularity-audit-2026-06.md
- 2026-06-20 [claude]: Edit modularity-audit-2026-06.md
- 2026-06-20 [claude]: Edit subsystems.py
- 2026-06-20 [claude]: Edit subsystems.py
- 2026-06-20 [claude]: Edit subsystems.yaml
- 2026-06-20 [claude]: Edit subsystems.yaml
- 2026-06-20 [claude]: Edit subsystems.yaml
- 2026-06-20 [claude]: Edit subsystems.yaml
- 2026-06-20 [claude]: Edit skill_commands.py
- 2026-06-20 [claude]: Edit module_commands.py
- 2026-06-20 [claude]: Edit module_commands.py
- 2026-06-20 [claude]: Edit module_commands.py
- 2026-06-20 [claude]: Edit module_commands.py
- 2026-06-20 [claude]: Edit module_commands.py
- 2026-06-20 [claude]: Edit doctor.py
- 2026-06-20 [claude]: Edit doctor.py
- 2026-06-20 [claude]: Edit test_modularity_toggle.py
- 2026-06-20 [claude]: Edit test_modularity_toggle.py
- 2026-06-20 [claude]: Edit test_modularity_toggle.py
- 2026-06-20 [claude]: committed 89913434 · 7 files
- 2026-06-20 [claude]: Landed module→skill cascade. subsystems.yaml gains data-driven skills: (graph→[graph-explorer,graph-os-authoring],…
