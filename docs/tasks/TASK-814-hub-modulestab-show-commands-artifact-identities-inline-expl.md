---
id: TASK-814
title: "Hub ModulesTab \u2014 show commands + artifact identities, inline explain-refusal, confirm before disable (F-E / ranks 6+7)"
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
# TASK-814: Hub ModulesTab — show commands + artifact identities, inline explain-refusal, confirm before disable (F-E / ranks 6+7)

**Outcome (one sentence):** The Hub Config→Modules tab (the least-expert persona's surface) shows the full blast radius before a toggle (commands + named hooks/tools/skills/commands, not opaque counts), renders the dependency-refusal reason inline and accessibly (not tooltip-only) sourced from the registry, and confirms a destructive disable — matching or beating the CLI's guardrail.

## Read First
- src/cli/module_commands.py
- src/core/web/routes/settings.py
- src/core/web/ui/src/pages/ConfigPage.tsx
- src/core/subsystems.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a module with owned commands and a dependency carrying a documented reason (tasks->docs enforcement-locality), **When** the Modules tab renders and a user focuses a blocked toggle, **Then** the Owns column shows a commands count + expandable artifact identities, the refusal reason renders as inline text (aria-disabled, keyboard/SR reachable — not title-only), and a disable that will unlink skills/commands prompts a confirm.
Checklist:
- [ ] module_state_payload: add commands count + optional name lists (hooks/tools/skills/commands identities). api-contract: extend ModuleRow to match.
- [ ] Add depends_on_reason to Module dataclass + subsystems.yaml (populate tasks->docs from the existing YAML comment); thread through payload.
- [ ] ConfigPage ModulesTab: render '· N commands' in Owns + an expandable identity view; render blockedReason as inline aria-disabled text (not just title=); optional confirm dialog reusing planned_skill_unlinks.
- [ ] a11y: aria-disabled + visible reason (WCAG — no hover-only critical info).
- [ ] Tests: ConfigPage.test.tsx asserts commands shown + reason inline; payload test asserts commands + reason fields.
- [ ] Verify: uv run pytest tests/test_cli.py -q (payload) + npm test (ui) if wired + make docs-lint.

## Work Log
- 2026-07-16 [claude]: Edit subsystems.py
- 2026-07-16 [claude]: Edit subsystems.py
- 2026-07-16 [claude]: Edit subsystems.yaml
- 2026-07-16 [claude]: Edit module_commands.py
- 2026-07-16 [claude]: Edit ConfigPage.tsx
- 2026-07-16 [claude]: Edit ConfigPage.tsx
- 2026-07-16 [claude]: Edit ConfigPage.tsx
- 2026-07-16 [claude]: Edit ConfigPage.test.tsx
- 2026-07-16 [claude]: Edit ConfigPage.test.tsx
- 2026-07-16 [claude]: Edit test_cli.py
- 2026-07-16 [claude]: Hub ModulesTab disclosure: module_state_payload now emits commands count, depends_on_reason, and owned artifact…
- 2026-07-16 [claude]: commit 8bd5757b93 — feat(hub): ModulesTab discloses commands/rules + inline refusal reason + dependency why (F-E)
