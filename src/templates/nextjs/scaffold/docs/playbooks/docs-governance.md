<!-- domain:DOCS | layer:playbook | ssot:true | updated:2026-03-17 -->
# Docs Governance Playbook

Purpose: Change the documentation system, agent workflow, SSOT routing, and validation tooling without creating duplicate truth.
Read when: The task edits `AGENTS.md`, playbooks, governance docs, task system files, doc scripts, or cross-doc structure.
Skip when: The task only consumes docs and does not change the docs system itself.
Read next: `docs/governance/docs-system.md`, `docs/governance/task-lifecycle.md`, `docs/governance/wrapper-derivation.md`, and `docs/engineering/formatting-rules.md`

> Nav: [Docs Index](../00-index.md) | [Docs System](../governance/docs-system.md)

## Read Selection Guide

> Complete lookup: AGENTS.md § Dimension Type Registry (auto-loaded). This section adds domain-specific detail for Orient phase.

The Classify phase generates a Read List. Use this mapping to select files — do NOT read all entries. Read only what matches your task's dimensions and unknowns.

### Always Read (for any docs governance task)

1. `AGENTS.md`
2. `docs/00-index.md`
3. `docs/governance/docs-system.md`

### Read Only If Relevant

- `docs/governance/task-lifecycle.md` — only if task system or status flow is affected
- `docs/workflow/workflow-guide.md` — only if Core Loop, playbooks, or scripts change
- `docs/governance/wrapper-derivation.md` — only if wrapper files or thin-wrapper policy is affected
- `docs/engineering/formatting-rules.md` — only if markdown formatting conventions change
- `docs/engineering/anti-ambiguity.md` — only if requirement language or specificity rules change

## Execution Rules

- Keep docs router-first and low-token.
- Every new doc must have one clear layer: `index`, `playbook`, `spec`, `policy`, `reference`, `adr`, or `task`.
- Index files link parent and children; playbooks define read selection guides and verification.
- Historical migration material belongs in `governance/archive/`, not evergreen architecture docs.
- Validation tooling must fail for real integrity errors, not print pass-only summaries.

## Verification

**Required** (enforced by `enforce-verify.sh` domain-aware hook):

1. `make docs-lint` — must show PASS in `.claude/.last-verify.json` within 30 min

**Additional**: `cos task-show TASK-NNN` for touched task flows, spot-check changed indexes for parent/child navigation. See AGENTS.md § Verification Matrix for full domain mapping.

## Stop and Escalate If

- a doc has no obvious canonical home
- a proposed move would break the SSOT hierarchy or duplicate another source
- a validation rule would create false positives against current canonical files
