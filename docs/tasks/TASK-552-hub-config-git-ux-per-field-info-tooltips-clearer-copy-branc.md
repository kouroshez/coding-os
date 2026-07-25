---
id: TASK-552
title: "Hub Config\u2192Git UX: per-field info tooltips + clearer copy + branch presets/none/custom + quick-start presets"
swimlane: core
kind: feature
epic: multi-agent-pr-mode
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-552: Hub Config→Git UX: per-field info tooltips + clearer copy + branch presets/none/custom + quick-start presets

**Outcome (one sentence):** The Config→Git tab becomes unambiguous for a non-expert consumer — every field carries an accessible info control (hover AND click → popover) explaining what it is and how it works; copy is rewritten for clarity; branch fields offer common presets + a None/clear control + custom entry; and a row of one-click quick-start presets (incl. a clearly-marked "Recommended — multi-agent") fills the form. Global default stays OFF (ADR-0013; coding-os stays trunk) — the Recommended preset is the easy path, not a forced default. Read-only (meta-repo) renders a clear explanation, not a dead form. PATCH payload shape unchanged.

## Read First
- src/core/web/ui/src/pages/ConfigPage.tsx (the `GitTab` ~line 407+ and the `AUTONOMY_OPTIONS` array)
- src/core/web/ui/src/lib/hooks.ts (useApiGet signature — query params)
- docs/playbooks/pr-workflow.md (the canonical semantics each tooltip paraphrases)

## Design Spec (SSOT for the implementation)

### A. Quick-start presets (new — top of the form, above Enable)
A labelled row "Quick start" of preset buttons; clicking one calls `setForm(...)` (does NOT auto-save — user reviews then Saves):
- **Solo / local** → `{enabled:true, integration_branch:'main', protected_branches:[], autonomy_level:'local'}` — "One agent, or no GitHub. Agents isolate in worktrees; you review & merge. Works with no remote."
- **Team + GitHub CI** ⭐ *Recommended* → `{enabled:true, integration_branch:'main', protected_branches:['production'], autonomy_level:'auto_merge'}` — "Agents open PRs into main and auto-merge once CI is green."
- **main → dev → prod** → `{enabled:true, integration_branch:'develop', protected_branches:['main','production'], autonomy_level:'auto_merge'}` — "Agents integrate to develop; main + production are human-only."
Mark the Recommended one visually (accent border/badge). Keep it honest: a preset only fills the form — the global default stays OFF.

### B. Per-field info control (ⓘ)
Reusable accessible `InfoTip` (button, `aria-label`, opens on hover AND click/focus, Esc closes, keyboard-reachable — a11y). One next to each field label. Copy (what + how):
- **Enable pr-mode:** "Multi-agent safety mode. Each agent works in its own isolated git worktree (under ~/.coding-os/worktrees) and lands changes via a Pull Request — so 5+ agents never overwrite or block each other. Off = trunk: agents commit straight to the branch (fine for one agent, risky for many). coding-os itself always stays trunk."
- **Integration branch:** "The branch agents merge their work into, via PR — they branch off it and target it. Usually `main` or `develop`. It stays always-green: broken code can't reach it because CI gates the merge."
- **Protected branches:** "Branches agents may NEVER write, push, or merge to — human-only (e.g. `production`). The branch-guard hook blocks every agent write to these. Leave empty if you have none."
- **Autonomy level:** "How far an agent acts without you. Local: commits only, you merge. Draft: opens a PR, you click merge. Auto-merge: merges itself when CI is green. Autonomous: also cleans up after itself. Higher rungs need a remote + GitHub. CI always gates the merge — autonomy changes who clicks merge, never whether code is checked."

### C. Autonomy dropdown one-liners (refine existing hints)
- Local — never pushes: "Commits in the worktree; you review & merge. Works with no remote."
- Draft — opens a PR: "Pushes + opens a PR; you merge it. Needs a remote + GitHub."
- Auto-merge — merges on green CI: "Pushes, opens a PR, merges itself once required CI passes. Needs a required status check."
- Autonomous — hands-off: "Auto-merge + cleans up its own worktree & branch after merge."

### D. Branch fields — presets + custom + None (replace bare free-text)
- **Integration branch:** keep the real-branch dropdown when the repo probe returns a branch list; otherwise an input with quick chips `[main] [develop] [master]` + free typing. Never empty (defaults `main`; show a hint).
- **Protected branches:** common toggle chips `[production] [main] [release/*]` + a **None** button that clears the list (field then reads "None — no protected branches") + a custom add input. When a branch list exists, keep the multiselect from it AND the None/custom add.

### E. Copy + layout polish
Section headers + one-line helper under each control; keep existing capability pills (remote/gh/required CI/pr-ready) and the unknown-branch warning. Tighten the TabIntro copy.

### F. Read-only state (meta-repo)
When the tab is read-only, show a clear banner — "coding-os itself stays trunk — pr-mode is for your consumer projects. Pick a project above to configure." — and disable inputs/presets (don't render a dead, confusing form).

### Constraints
- Reuse existing components (`Pill`, `StateRow`, `TabIntro`, the probe/branch-list/unknown-branch logic). Only add a minimal `InfoTip` + chip control if none exist (search first — reuse-first).
- API-contract: the Save PATCH body stays exactly `{enabled, integration_branch, protected_branches, autonomy_level}` — verify against the producer `_GitSettingsIn` in src/core/web/routes/settings.py. No new backend.
- a11y on the InfoTip + chips (keyboard, aria, focus-visible). No magic numbers, terse WHY-only comments.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** pr-mode is OFF, **When** I open Config→Git, **Then** quick-start preset buttons (incl. a Recommended multi-agent one) one-click fill the form, and each field has an info control that on hover OR click explains what it is and how it works.
- **Given** the Protected branches field, **When** I want none, **Then** a None control clears it (reads "None — no protected branches"), with common presets (production/main) + custom add available.
- **Given** the tab is read-only (coding-os meta-repo), **When** I view it, **Then** inputs are disabled with a clear "coding-os stays trunk — configure pr-mode on a consumer project" explanation and the layout still reads cleanly.
- **Given** I apply a preset and Save, **Then** the PATCH payload {enabled, integration_branch, protected_branches, autonomy_level} is sent unchanged and `tsc` typecheck + `vite build` pass.

## Work Log
- 2026-06-24 [claude]: Deliberation: read-only signal = active project slug==='coding-os' (the meta-repo's derived slug, confirmed) rather…
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.tsx
- 2026-06-24 [claude]: Edit ConfigPage.test.tsx
- 2026-06-24 [claude]: Edit ConfigPage.test.tsx
- 2026-06-24 [claude]: Built InfoTip (hover+click+Esc, aria) + Chip + FieldLabel co-located in ConfigPage; quick-start preset row…
- 2026-06-24 [claude]: committed b210bdce · 2 files
- 2026-06-24 [claude]: Status transitioned to complete via cos task-done.
- 2026-06-24 [claude]: Verified diff post-fork: tsc+vite build green, eslint clean, 8/8 ConfigPage tests pass. Read-only is a CLIENT-SIDE…
