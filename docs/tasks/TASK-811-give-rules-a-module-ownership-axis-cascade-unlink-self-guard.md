---
id: TASK-811
title: "Give rules a module-ownership axis \u2014 cascade unlink + self-guard + total variability (F-A / rank 1)"
swimlane: core
kind: feature
epic: modularity-completion
labels: [ready]
status: archive
priority: P1
appetite: 1d
created: 2026-07-16
started: 2026-07-16
completed: 2026-07-16
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-811: Give rules a module-ownership axis — cascade unlink + self-guard + total variability (F-A / rank 1)

**Outcome (one sentence):** A disabled module's owned rule files leave the consumer's .claude/rules/ (physical unlink, ref-counted like skills/commands) AND self-guard as inert while present (defense-in-depth), so a lean profile neither ships nor is commanded by dead-tool instructions.

## Read First
- src/cli/subsystems.py
- src/cli/module_commands.py
- src/cli/skill_commands.py
- src/core/scripts/install-adapter.sh
- src/core/rules/memory.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** memory disabled (lite/core profile), **When** a consumer inits or toggles, **Then** memory.md is NOT symlinked into .claude/rules/ and the module gate + rules agree; on re-enable it relinks; meta-repo (is_coding_os_source_tree) is guarded.

Checklist:
- [ ] Re-add `rules: tuple[str,...]` to Module dataclass (src/cli/subsystems.py) + loader.
- [ ] Assign in subsystems.yaml: memory->[memory.md], cognition->[model-routing.md], graph->[graph-first.md] (meta path). Keep cross-cutting rules (git-workflow, anti-overengineering, transparency-banner, api-contract-discipline, thinking_os, test-discipline) unowned/kernel.
- [ ] Add cascade_module_rules() mirroring cascade_module_skills (ref-counted unlink/relink, override-aware) + wire into toggle_and_regen (meta-repo guarded).
- [ ] Gate the install-adapter.sh core-rule symlink loop by module state (reuse module_disabled reader; keep _NON_ACTIVE_RULES behavior).
- [ ] Defense-in-depth: add the model-routing.md-style self-guard sentence to memory.md and any module rule lacking it.
- [ ] Update dimension/skill-enforcement regen if rules count feeds them (verify no derived-artifact drift; run make regen-rules if needed).
- [ ] Tests: disable->rule unlinked+gate agrees; enable->relinked; ref-count (rule co-owned survives); meta-repo preserved.
- [ ] Verify: uv run pytest tests/test_cli.py -q + make verify-hooks (install-adapter.sh) + make docs-lint.

## Work Log
- 2026-07-16 [claude]: Edit subsystems.py
- 2026-07-16 [claude]: Edit subsystems.py
- 2026-07-16 [claude]: Edit subsystems.yaml
- 2026-07-16 [claude]: Edit subsystems.yaml
- 2026-07-16 [claude]: Edit subsystems.yaml
- 2026-07-16 [claude]: Edit subsystems.yaml
- 2026-07-16 [claude]: Edit module_commands.py
- 2026-07-16 [claude]: Edit module_commands.py
- 2026-07-16 [claude]: Edit module_commands.py
- 2026-07-16 [claude]: Edit extract_disabled_module_rules.py
- 2026-07-16 [claude]: Edit install-adapter.sh
- 2026-07-16 [claude]: Edit memory.md
- 2026-07-16 [claude]: Edit memory.md
- 2026-07-16 [claude]: Edit test_cli.py
- 2026-07-16 [claude]: Implemented rules module-ownership: Module.rules field + loader (subsystems.py); memory->[memory.md],…
- 2026-07-16 [claude]: commit af56209fc1 — feat(core): module-owned rules — cascade-unlink a disabled module's rules (F-A)
