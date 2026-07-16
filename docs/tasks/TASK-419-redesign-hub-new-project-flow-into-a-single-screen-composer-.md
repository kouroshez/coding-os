---
id: TASK-419
title: "Redesign Hub new-project flow into a single-screen Composer + fix live-cwd, multi-agent, skills depth"
swimlane: core
kind: feature
epic: null
labels: [hub, onboarding, ux, frontend, backend, ready]
status: archive
priority: P1
appetite: 2d
created: 2026-06-15
started: 2026-06-15
completed: 2026-06-15
agent_session: ses-claude-20260615-014142-5969
depends_on: []
blocked_by: []
references: []
---
# TASK-419: Redesign Hub new-project flow into a single-screen Composer + fix live-cwd, multi-agent, skills depth

**Outcome (one sentence):** Replace the 8-step OnboardingWizard with a single-screen "Composer" (choices on the left, a live "what you'll get" preview on the right, an Advanced section collapsed by default) so the dominant "preset + name + Create" path finishes in about 3 interactions instead of 8 screens, reusing existing primitives (Modal full-screen, ActionPill/Banner, --cos-* tokens) rather than reinventing them, and bundling the audited backend fixes (live-cwd, multi-agent init, module toggles, skills depth). Audit evidence: workflow wf_337e7824-63a (7 agents) plus this session's analysis.

## Read First
- src/core/web/ui/src/pages/OnboardingWizard.tsx — the wizard to replace
- src/core/web/ui/src/pages/HubHome.tsx — polished reference + the live-cwd card
- src/core/web/routes/hub.py — projects list + init/validate-init + adapters/stacks/skills/presets endpoints
- src/core/web/ui/src/components/Modal.tsx — reuse for the full-screen shell
- src/core/web/ui/src/layout/HubPrimitives.tsx — ActionPill/Banner to reuse
- src/core/web/ui/src/pages/ConfigPage.tsx — module/skill toggles to mirror; stale read-only comment
- src/cli/skills_list.py — required/recommended/optional grouping + tier/domain/description
- docs/engineering/hub-architecture.md — address-space + onboarding doc to update

## Acceptance (G/W/T) — *this IS the Definition of Done*

### 1 Live-cwd fix
- **Given** the Hub started with cwd = $HOME (the GUI-first path)
- **When** GET /api/hub/projects is called
- **Then** $HOME is NOT listed as a runtime-cwd project — `_derive_runtime_entry` (hub.py) returns None when cwd==Path.home() or lacks a real project marker (not just `.coding-os/` presence); covered by a test in tests/test_hub_projects.py

### 2 Multi-agent
- **Given** a user in the Composer Advanced section
- **When** they pick both claude and codex
- **Then** POST /api/hub/registry/{init,validate-init} accept `agents: list[str]` (with `agent: str` back-compat) and the scaffold installs both .claude/ and .codex/; the agent chips are multi-select

### 3 Single screen + live preview
- **Given** the Composer open with a preset/stack chosen
- **When** it renders
- **Then** one screen shows choices (left) plus a live preview (right) of resolved stacks, the 9 always-installed core skills, required+recommended skills WITH tier/domain/description, a VISUAL board/swimlane preview (no raw JSON merge-notes), agents, and the target path derived from validate-init; the old standalone skills and swimlanes steps are gone

### 4 Skills depth
- **Given** the skills picker
- **When** it renders
- **Then** stack-recommended skills are pre-selected (toggleable), unshipped (validated=false) skills are excluded from the selectable set, and copy explains they seed .coding-os.yaml::extra_skills (adjustable later in Config)

### 5 Module toggles at create
- **Given** the Advanced section expanded
- **When** the user toggles modules (docs/tasks/graph/memory/design; kernel locked)
- **Then** the tasks→docs dependency is respected and the choices are passed to init (wired into the request + scaffold, mirroring preset.modules)

### 6 Design consistency
- **Given** the Composer rendered
- **When** reviewed visually
- **Then** it uses Modal.tsx (focus-trap/Esc/backdrop-blur/scroll-lock), ActionPill for the primary CTA, --cos-err tokens (no hardcoded red-500), a text-sm+ hierarchy (no blanket text-[10px]), rounded-xl/2xl elevation consistent with HubHome, and the description is a prominent first-class field

### 7 Docs + verify
- **Given** the change complete
- **When** closing
- **Then** hub-architecture.md gains a "new-project Composer + runtime-cwd" section, an ADR records the wizard-to-composer decision, the ConfigPage stale "read-only this phase" comment is corrected, and verification passes: `uv run pytest tests/test_hub_projects.py tests/test_cli.py -q` plus `cd src/core/web/ui && npm test && npm run build`

## Work Log
- 2026-06-15 [claude]: Created from a 7-agent onboarding audit (workflow wf_337e7824-63a). Confirmed root causes — live-cwd surfaces ~/.coding-os (hub.py:124-140); multi-agent already supported by the CLI but not the Hub API (hub.py:490); the wizard ignores Modal/ActionPill/tokens; skills steps shallow and unshipped skills selectable. User approved direction: single-screen Composer (Option A), full redesign in one slice. Implement in a fresh session due to context budget.
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit test_hub_projects.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit hub.py
- 2026-06-15 [claude]: Edit test_hub_init_route.py
- 2026-06-15 [claude]: commit 6050279b7e — fix(hub): drop $HOME/global-state from project list + accept multi-agent init (TASK-419)
- 2026-06-15 [claude]: Slice 1/2 landed (commit 6050279b): backend bug fixes verified green. (1) live-cwd — _derive_runtime_entry now skips cwd
- 2026-06-15 [claude]: Edit OnboardingWizard.tsx
- 2026-06-15 [claude]: Edit OnboardingWizard.test.tsx
- 2026-06-15 [claude]: Edit OnboardingWizard.tsx
- 2026-06-15 [claude]: Edit OnboardingWizard.tsx
- 2026-06-15 [claude]: Edit OnboardingWizard.tsx
- 2026-06-15 [claude]: Edit ConfigPage.tsx
- 2026-06-15 [claude]: Edit hub-architecture.md
- 2026-06-15 [claude]: Edit hub-architecture.md
- 2026-06-15 [claude]: Edit 0009-new-project-composer.md
- 2026-06-15 [claude]: committed 8c9cec44: docs/architecture/adr/00-index.md, docs/architecture/adr/0009-new-project-composer.md, docs/engineer
- 2026-06-15 [claude]: Slice 2/2 landed (commit 8c9cec44): single-screen Composer shipped. OnboardingWizard.tsx rewritten as a 2-column Modal c
- 2026-06-15 [claude]: Status transitioned to complete via cos task-done.
