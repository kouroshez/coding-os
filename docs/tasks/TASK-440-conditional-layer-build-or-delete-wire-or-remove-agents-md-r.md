---
id: TASK-440
title: "Conditional layer build-or-delete: wire (or remove) AGENTS.md requires: + skill/hook overrides, render per-consumer rules, hide no-op design module + orphan goldens"
swimlane: infra
kind: refactor
epic: null
labels: [modularity, build-or-delete, conditional-assembly, audit-2026-06, ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-06-16
started: 2026-06-17
completed: null
agent_session: ses-claude-20260617-183518-6ce2
depends_on: [TASK-438]
blocked_by: []
references: []
---
# TASK-440: Conditional layer build-or-delete: wire (or remove) AGENTS.md requires: + skill/hook overrides, render per-consumer rules, hide no-op design module + orphan goldens

**Outcome (one sentence):** Toggling a module/skill actually changes what the consumer is told to do — its rule files are scoped to its own stacks, its disabled module's prose drops from AGENTS.md, a core/stack skill can be disabled, and every declared-but-dead modularity axis is deleted (doc-first) so no half-wired surface survives. Closes audit R6+R7+R8+R13 and new findings F2+F3+F4+F9 (+F10/F11 hygiene).

## Decisions locked (user, 2026-06-17) — execute to these, do not re-litigate
- **Granularity = HYBRID (Q1=C):** module is the primary toggle unit (VSCode-extension model); SKILL is the one first-class per-item toggle (real token-cost ROI, zero safety risk); HOOKS stay module-bound (per-hook toggle is a footgun + maintenance sink). => deliver core/stack skill-disable; do NOT build a per-hook writer — instead assign the 32 orphan non-safety hooks to modules (F9).
- **Per-consumer rules = RUNTIME-FILTER (Q2):** keep dimension-registry.md / skill-enforcement.md as-is on disk but filter to the consumer's installed stacks at Classify time (reuse skill_primer.py installed-manifest scoping). Do NOT render-and-copy per-consumer files / break the live symlink. Exclude the `meta` stack from non-meta consumers.
- **Dead machinery = DELETE all 5, DOC-FIRST (Q3):** write the audit SSOT doc (see NEW audit-doc task / R12) capturing why each axis is dead BEFORE deleting, then delete in the same pass.

## Read First
- src/cli/renderer.py
- src/templates/_base/base.yaml  (agents_md_sections — flat, ungated)
- src/cli/project_overrides.py  (dead load_skill_overrides)
- src/cli/skill_commands.py  (set_project_skill — extras-only today)
- src/core/subsystems.yaml

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** a disabled module (graph/memory/docs) **When** AGENTS.md is rendered **Then** that module's tool-routing prose drops — add inline `{% if modules.<id> %}` gates to the graph/memory/docs fragments and split task-authoring/task-logging behind `modules.tasks` (F2). PR-gated test: `render_agents_md(world,{'memory':False})` MUST NOT contain `cos_search`.

**Given** a python-only consumer **When** Classify builds the Read List / reads skill-enforcement **Then** only its installed stacks appear, via the RUNTIME filter (F3/R8), and `meta` is excluded for non-meta consumers — remove-stack no longer leaves the stack in the Read List.

**Given** `cos skill disable <core-or-stack-skill>` (e.g. redis) **When** invoked from CLI or Hub **Then** ONE `.coding-os.yaml` skills block `{extra, disabled}` is updated AND the apply fn re-links/unlinks the adapter skills dir inline AND re-renders the consumer-scoped skill-enforcement (F4). Delete skill-overrides.json + load_skill_overrides (no second store).

**Given** the 32 non-safety orphan hooks (F9) **When** subsystems.yaml is regenerated **Then** each belongs to a toggleable module (or is pinned to kernel as core discipline); no per-hook override layer is built.

**Given** the 5 dead axes (requires: section-skip, skill-overrides reader, Module.rules/doc_tags, routing_weights loop, DispatchRequest.adapter+adapter_budget_usd) **When** the DELETE pass runs **Then** each is removed AFTER the audit SSOT doc records it, the `design` no-op module is hidden from the Hub toggle (F10), and the 4 orphan goldens are deleted (F11).

**Given** all of the above **When** the matrix tests + golden parity + a new render-with-module-disabled assertion run **Then** they pass.

## Work Log
- 2026-06-18 [claude]: Edit renderer.py
- 2026-06-18 [claude]: Edit task-authoring.md.tmpl
- 2026-06-18 [claude]: Edit task-authoring.md.tmpl
- 2026-06-18 [claude]: Edit task-logging.md.tmpl
- 2026-06-18 [claude]: Edit task-logging.md.tmpl
- 2026-06-18 [claude]: Edit test_all_stacks_render_smoke.py
- 2026-06-18 [claude]: commit ccf6986a5a — feat(modularity): gate task-authoring/task-logging AGENTS.md fragments on modules.tasks
- 2026-06-18 [claude]: F2 slice LANDED: task-authoring + task-logging fragments now gated on {% if modules.tasks %}; renderer skips…
