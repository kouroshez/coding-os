---
id: TASK-935
title: "docs-update: split clean-code SKILL.md along its error-handling seam to cut the always-loaded token tax"
swimlane: docs
kind: refactor
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-08-11
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-935: docs-update: split clean-code SKILL.md along its error-handling seam to cut the always-loaded token tax

## Outcome

clean-code/SKILL.md drops from 760 lines to under 500 by moving the error-handling contract (sections 1, 1b, 1c, 2, 3) and the error-path test examples (section 6) into `references/error-handling.md`, keeping every normative rule stated inline. No rule text is lost and `make docs-lint` passes.

## Read First

- [src/core/skills/clean-code/SKILL.md](../../src/core/skills/clean-code/SKILL.md)
- [docs/architecture/raptor-consolidation.md](../architecture/raptor-consolidation.md)
- [src/core/rules/anti-overengineering.md](../../src/core/rules/anti-overengineering.md)

## Why

`clean-code` is loaded on every code edit in every session, in this repo and in every consumer project. At 760 lines it is the single largest always-on prose cost in the system — Raptor principle 3 (parasitic mass) applied to the instruction layer, the same finding that took the rules layer from 25.2KB to 14.7KB with zero normative loss.

No gate is violated today: `block-bad-patterns.sh` and `make check-file-size` scan code extensions only, and the CI ratchet scans `git ls-files "*.py"`. That is exactly why this needs a task — nothing will catch it.

The seam is cohesion, not line count: the error-handling contract (fail-closed, no internal details in responses, typed exceptions, error-path tests) changes independently of naming, code shape, and efficiency. The `performance` and `deployment-cicd` skills already use the SKILL-is-the-gate / references-carry-the-depth split.

## Acceptance

- **Given** the split has landed, **When** `wc -l src/core/skills/clean-code/SKILL.md` runs, **Then** it reports under 500 lines.
- **Given** any rule stated inline before the split, **When** the new SKILL.md is read, **Then** the rule is still stated there — only its BAD/GOOD example pairs moved to `references/`.
- **Given** the change, **When** `make docs-lint` runs, **Then** it passes with no new errors.
- **Given** the moved sections, **When** `references/error-handling.md` is read, **Then** every Python and TypeScript example pair from the original sections is present.

## Notes

Do not thin the *rules* while moving the *examples* — the Post-Code Checklist references section numbers, so either keep the numbering or update every cross-reference in the same commit. `src/core/rules/*.md`, `docs/governance/critical-rules.md`, and the stack `skill-enforcement` table all link into this skill.

## Work Log
