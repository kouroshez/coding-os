<!-- domain:DOCS | layer:reference | ssot:false | updated:2026-05-21 -->
# Audit — Slash-command refs + stale command docs

Task: [TASK-005](../TASK-005-fix-broken-slash-command-refs-stale-command-docs.md)
Status: complete
Date: 2026-05-21

## Scope

Reviewed every `/`-slash-command file (9 workflow commands in `src/core/commands/`,
11 `/role-*` commands in `src/core/thinking_os/agents/`) and every command-facing
doc (README, AGENTS.md, workflow-guide). Goal: every referenced script /
make-target / CLI command must exist and resolve; docs must match the current
Scrumban + `cos` toolchain.

## Category table

| # | Category | Detection | Scope | Before | After | Verified |
|---|---|---|---|---|---|---|
| 1 | Stale pre-`src/` path to `classify.sh` in `/classify` | `grep -rn 'core/skills/thinking_os/scripts' src/core/commands/` | command files | 1 | 0 | yes |
| 2 | Dead `make` targets in command files (`cos-health`, `task-context`, `task-next`) | `grep -rnE 'make (cos-health\|task-context\|task-next)' src/core/commands/` | command files | 2 files (diagnose, task) | 0 | yes |
| 3 | Wrong gate path in kernel rule (`.claude/.thinking_os-gate` vs `$COS_AGENT_DIR/...`) | `grep -rn '\.claude/\.thinking_os-gate' src/core/rules/` | core rules | 1 | 0 | yes |
| 4 | Hook help-text names non-existent `$COS_AGENT_DIR/hooks/write-state.sh` | `grep -rn 'COS_AGENT_DIR}*/hooks/write-state' src/core/hooks/*.sh` | hooks | 7 (doc-anchor, memory-check×2, task-start, nudge, gate, zoom) | 0 | yes |
| 5 | `make cos-health` (no such target) in command docs | `grep -rln 'make cos-health' README.md AGENTS.md docs/workflow/ …scaffold…` | docs | 4 | 0 | yes |
| 6 | Legacy `make task-*` workflow documented in workflow-guide | `grep -rlnE 'make task-(context\|next\|done\|…)' docs/workflow/ …scaffold…` | docs | 2 files | 0 | yes |
| 7 | README has no slash-command discoverability | manual review | README.md | missing | added (`## Slash commands`) | yes |
| 8 | Non-existent `backlog` status referenced (canonical `STATUS_ENUM` has `icebox`, not `backlog`) | `grep -rn 'backlog' src/core/commands/ docs/workflow/` | board.md, workflow-guide | 3 | 0 | yes |

## Fixes applied

- `src/core/commands/classify.md` — step 3 now uses `write-state.sh` (the canonical
  gate writer the kernel rule documents); `classify.sh` is not shipped to consumers.
- `src/core/commands/diagnose.md` — `make cos-health` / `make diagnose` → `cos doctor` / `cos health`.
- `src/core/commands/task.md` — `make task-context` / `make task-next` → `cos task-show` / `cos task-pick`.
- `src/core/commands/board.md` — `backlog` column → `icebox` (canonical `STATUS_ENUM`).
- `src/core/rules/thinking_os.md` — Record Gate path corrected to `.coding-os/<agent>/.thinking_os-gate`.
- 7 hooks (`enforce-doc-anchor`, `enforce-memory-check`, `enforce-task-start`,
  `nudge-thinking-os`, `thinking_os-gate`, `enforce-zoom`) — help-text now points
  at `.${COS_AGENT}/hooks/write-state.sh` (real location) with the gate var expanded.
- `docs/workflow/workflow-guide.md` (+ `_base` scaffold copy) — rewritten to the
  Scrumban (`cos task-*`) flow.
- `AGENTS.md`, `README.md` — `make cos-health` → `cos health`.
- `README.md` — new `## Slash commands` section for GitHub discoverability.

## Deferred to follow-up — [TASK-006](../TASK-006-purge-legacy-make-task-workflow-from-governance-template-doc.md)

The exhaustive re-grep found the same legacy `make task-*` workflow in deeper
governance SSOT docs — `src/core/docs/task-lifecycle.md` (wholesale legacy: 6-line
`make task-*` command block + `docs/tasks.md` status index), `agent-workflow.md`
(2 isolated refs), and `src/templates/nextjs/scaffold/docs/playbooks/docs-governance.md`
(1 ref). These are canonical lifecycle docs a layer below the slash-command scope;
rewriting `task-lifecycle.md` is a deliberate governance edit, tracked as TASK-006.

## Out of scope (not defects)

- 11 `/role-*` command files — render correctly as slash commands; symlinked from
  `src/core/thinking_os/agents/` (a second, valid SSOT dir — not drift).
- 6 other workflow commands (`board`, `daily`, `memory-search`, `retro`, `review`,
  `verify`) — reviewed, all reference real commands; consumer-relative links resolve.

## Verification

- After-fix grep counts for categories 1–6 = 0 (see Work Log).
- `make verify-hooks` — hook syntax + shellcheck.
- `make dogfood-claude` — re-render `.claude/` symlinks.
- Golden parity regenerated via `scripts/capture_golden.py` (command/doc files are
  snapshotted per agent×stack).
