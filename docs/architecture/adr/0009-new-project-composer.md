<!-- domain:ARCH | layer:adr | ssot:true | updated:2026-06-15 -->
# ADR-0009: New-project flow is a single-screen Composer, not a step wizard

> Nav: [ADR index](00-index.md)

## Status

Accepted (TASK-419). The Composer (`src/core/web/ui/src/pages/OnboardingWizard.tsx`)
replaces the 8-step wizard shipped in TASK-358.

## Context

The TASK-358 "New project" flow was an 8-step full-screen wizard
(mode → [stacks] → agent → skills preview → extra skills → swimlanes →
name → description → review). In review it read as low quality for an
enterprise product:

- The choices are mostly **independent**, but a wizard forces them into a
  sequence — the dominant "preset + Create" path still cost 8 screens.
- Two steps (skills preview, swimlanes) demanded **no input** — they padded the
  funnel, and the swimlane step printed raw merge-notes JSON at the user.
- Agent selection was **single-select**, though the CLI/scaffold have always
  supported several adapters per project (`cos init --agent claude,codex`).
- The component was hand-rolled (`fixed inset-0`, blanket `text-[10px]`,
  hardcoded `red-500`), ignoring the shared `Modal` / `ActionPill` primitives
  and `--cos-*` tokens that the rest of the Hub uses.
- The 1–2 paragraph description (which seeds the PRD, TASK-364) was buried at
  step 7 and users did not realise it existed.

## Decision

Collapse the wizard into one **Composer** screen with progressive disclosure:

1. **One screen, two columns.** Left = choices (template preset/custom; name +
   folder + a first-class description; an *Advanced* disclosure for multi-select
   agents and skills). Right = a **live preview** driven by `validate-init`
   (resolved stacks, agents, board lanes rendered as chips — not JSON, target
   path, the stack's skills with tier/domain/description depth).
2. **Multi-select agents.** The Hub `init`/`validate-init` endpoints accept
   `agents: list[str]` (`agent: str` kept for back-compat via `_resolve_agents`).
3. **Skill depth + correct defaults.** Stack-recommended *core* skills are
   pre-selected into `extra_skills` (the scaffold only auto-links a stack's own
   skill dirs, so curated core companions must ride `--skills`); unshipped
   (`validated:false`) skills are filtered out of the selectable set.
4. **Reuse, don't reinvent.** Built on `Modal` (focus-trap/Esc/backdrop-blur/
   scroll-lock), `ActionPill`, `Banner`, and design tokens. The job-progress +
   cancel flow (TASK-362) is unchanged.

Module toggles at create time are explicitly **deferred** (follow-up): modules
ship all-enabled and are toggled post-create in Config, which already works.
Wiring them at init would need a new endpoint + a `cos init` flag — out of scope
for this slice.

## Consequences

- The fast path drops from ~8 screens to ~3 interactions.
- The 8-step `wizardSteps()` state machine and its step tests are removed;
  `OnboardingWizard.test.tsx` is rewritten for the single-screen model.
- `HubHome` is unchanged — it still renders `<OnboardingWizard>` (default
  export, same props).
- A project can now be created with several adapters from the UI.
- Follow-up: surface module toggles in the Composer once `cos init` grows a
  module flag.
