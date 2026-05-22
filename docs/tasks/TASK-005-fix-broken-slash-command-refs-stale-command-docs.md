---
id: TASK-005
title: "Fix broken slash-command refs + stale command docs"
swimlane: core
kind: bug
epic: null
labels: [docs-update, governance]
status: complete
priority: P2
appetite: "1d"
created: 2026-05-21
started: null
completed: 2026-05-21
agent_session: ses-claude-20260521-183248-4524
depends_on: []
blocked_by: []
references: []
---
# TASK-005: Fix broken slash-command refs + stale command docs

**Outcome (one sentence):** All /-slash-command files invoke real commands; command docs (README, AGENTS.md, workflow-guide) match the current Scrumban + cos CLI; kernel-rule gate path matches what hooks actually read.

## Read First
- src/core/commands/
- src/core/rules/thinking_os.md
- docs/workflow/workflow-guide.md
- README.md

## Repro Steps
1. Run `/classify` → step 3 invokes `bash core/skills/thinking_os/scripts/classify.sh` — path `core/skills/` is a pre-`src/`-migration stale path; script actually lives at `src/core/skills/...`. Invocation fails.
2. Run `/diagnose` → step 1 runs `make cos-health` — no such Makefile target. `make diagnose` also absent.
3. Run `/task` → uses `make task-context` / `make task-next` — neither exists; Scrumban replaced them with `cos task-show` / `cos task-pick`.
4. `src/core/rules/thinking_os.md:85` tells the agent the gate path is `.claude/.thinking_os-gate`, but every hook reads `$COS_AGENT_DIR/.thinking_os-gate` = `.coding-os/<agent>/...`.
Expected: every slash command invokes a real command; docs match the current toolchain.
Actual: 3 commands invoke non-existent targets; kernel rule + several hook help strings name the wrong gate/hook path.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the 20 slash-command files and the command-facing docs (README, AGENTS.md, workflow-guide).
- **When** an agent invokes `/classify`, `/diagnose`, `/task` or reads the kernel gate instructions.
- **Then** every referenced script / make-target / CLI command exists and resolves; README documents the slash commands; workflow-guide describes the Scrumban (`cos task-*`) flow not the legacy `make task-*` flow; `make verify` + golden parity pass.

## Work Log
- 2026-05-21 [claude]: Status transitioned to complete via cos task-done.
