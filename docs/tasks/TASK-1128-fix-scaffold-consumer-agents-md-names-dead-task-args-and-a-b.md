---
id: TASK-1128
title: "fix(scaffold): consumer AGENTS.md names dead task args and a blocked fallback; shipped rules cite src/core paths"
swimlane: templates
kind: bug
epic: null
labels: [governance, docs-update, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-25
started: 2026-11-24
completed: 2026-11-24
agent_session: ses-claude-20261124-204737-f93d
depends_on: []
blocked_by: []
references: []
---
# TASK-1128: fix(scaffold): consumer AGENTS.md names dead task args and a blocked fallback; shipped rules cite src/core paths

**Outcome (one sentence):** A fresh consumer's AGENTS.md and always-on rules name only commands that do what they say and paths that exist in that project.

## Read First
- src/core/rules/api-contract-discipline.md
- src/core/rules/timestamp-discipline.md
- docs/architecture/meta-project.md

## Repro Steps
cos init -a claude,codex -t fastapi -n probe --yes --no-register --no-git; rg -n 'WHAT=|MCP outage|Rule 15' probe/AGENTS.md; rg -n 'src/core/' probe/.claude/rules/api-contract-discipline.md probe/.claude/rules/timestamp-discipline.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh fastapi scaffold, **When** AGENTS.md is read, **Then** it names one task workflow (cos task-*), no make task-* args the wrapper drops, and no hand-Edit fallback for task status.
- **Given** the shipped api-contract-discipline and timestamp-discipline rules, **When** grepped for src/core/, **Then** nothing matches in the consumer copy.
- **Given** the same scaffold before and after, **When** always-on tokens are measured, **Then** both figures are recorded.

## Work Log
- 2026-11-25 [claude]: Moved coding-os producer table to meta rule api-contracts.md (paths-scoped): right layer, consumers keep generic rule
- 2026-11-25 [claude]: fresh fastapi rescaffold: no make task-*/Rule 15/hand-Edit/Phase in AGENTS; no src/core in shipped rules
- 2026-11-25 [claude]: always-on chars/4 before 14098 after 13927 (AGENTS 3110->3037, api-contract 893->817, timestamp 971->949)
- 2026-11-25 [claude]: green: golden+rules_fresh 10, template_scaffold 152, modularity 11, make lint, size budget, docs-lint
- 2026-11-25 [claude]: commit de8a86b6f6 — fix(rules): shipped contract and timestamp rules stop sending consumers to src/core paths
- 2026-11-25 [claude]: review r1 rework: rule_audit map entry (audit rc 1->0); invariant test 25 pass, fails on pre-fix goldens
- 2026-11-25 [claude]: kept tests/**/*.py glob on meta-api-contracts: path-scoped, ~300 tok only on test edits; envelope tests live anywhere
- 2026-11-25 [claude]: commit 9129cbc452 — test(scaffold): consumer AGENTS.md and shipped rules name no dead task commands or src/core paths
- 2026-11-25 [claude]: Status transitioned to complete via cos task-done.
