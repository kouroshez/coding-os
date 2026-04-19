<!-- domain:DOCS | layer:policy | ssot:true | updated:{{DATE}} -->
# Documentation System Policy

Purpose: Define the canonical documentation taxonomy, naming rules, file headers, and navigation contract for all active docs.
Read when: Creating, moving, splitting, or validating documentation files.
Skip when: You only need to consume a playbook or domain doc without changing the docs system.
Read next: `agent-workflow.md`, `task-lifecycle.md`

> Nav: [Docs Index](../00-index.md)

## Layer Model

- `index` — navigation hub, parent/child routing only
- `playbook` — task workflow with read selection guide and verification
- `spec` — canonical product/content requirements
- `policy` — process or governance rules
- `reference` — supporting factual reference, not primary truth
- `adr` — immutable decision record
- `task` — execution log for a specific work item

## Naming Rules

- Root index: `docs/00-index.md` (master navigation hub)
- Sub-directory indexes: `00-index.md` in directories that have many files (architecture, PRD, api-contracts, pages-content-spec)
- Task list: `docs/tasks.md` (SSOT for task status)
- Playbooks: `kebab-case.md`
- ADRs: `ADR-###-kebab-case.md`
- Tasks: `TASK-###-slug.md`
- Historical archive docs: `YYYY-MM-topic.md` under `governance/archive/`
- Other active docs: `kebab-case.md`

## Header Contract

Every file inside `docs/` starts with:

```html
<!-- domain:XXX | layer:index|playbook|spec|policy|reference|adr|task | ssot:true|ref | updated:YYYY-MM-DD -->
```

## Opening Block Contract

Immediately after the H1, every active doc includes these four lines:

- `Purpose:`
- `Read when:`
- `Skip when:`
- `Read next:`

These lines must let an agent decide within the first screenful whether to keep reading.

## Playbook Read-Pack Limit

Playbook read packs must not exceed 10 files. Most tasks need 3-6; complex multi-domain tasks may reach 10. If more are needed, split into a sub-playbook or a domain-specific routing hub.

## Navigation Rules

- `docs/00-index.md` is the single master navigation hub.
- Directories with many files (architecture, PRD, api-contracts, pages-content-spec) keep their own `00-index.md`. Smaller directories (engineering, design, governance, playbooks, ops) may not need an index.
- Every file should include a `> Nav:` breadcrumb on the line after the opening block.
  - Files inside a directory with a local index → Nav links to `./00-index.md`.
  - Files inside a directory without an index → Nav links to the root `../00-index.md`.
  - Index files → Nav links to parent index or root.
- Use relative links only.
- Use `REF:*` shortcodes from `docs/foundation-map.md` in task `Read First` sections where shorter references improve readability.

## Task File Rules

- `docs/governance/templates/task-detail.md` is the canonical template reference, not a live task record.
- A started or completed task has exactly one primary detail file: `docs/tasks/TASK-###-slug.md`.
- Optional companion docs may exist when a task needs a checklist, appendix, or research annex that would otherwise break length limits.
- Companion docs use `layer:reference`, link back to the parent task, and do not carry canonical status for the task lifecycle.
- A backlog index entry may exist without a detail file until execution begins; once a task is marked `[/]`, `- [x]`, or `(BLOCKED: reason)`, the primary detail file is required.

## Architecture Boundary

- `docs/architecture/` contains evergreen architecture and ADRs only.
- Temporary migration history and audit trails live under `docs/governance/archive/`.
- Open risks and blind spots live in `docs/governance/risk-register.md`.

## Changes Log Policy

- `changes.log` lives at repo root and tracks completed task summaries.
- Max 5 lines per task entry: title + reason + key changes + files.
- Detailed breakdowns belong in the task file, not changes.log.
- When changes.log exceeds 200 lines, archive entries older than 30 days to `docs/governance/archive/YYYY-MM-changes.md`.

## Extension Protocol

When adding a new domain to the project, follow this order:

1. Architecture doc → `docs/architecture/NN-<domain>.md`
2. Playbook → `docs/playbooks/<domain>.md`
3. API contracts → `docs/api-contracts/<domain>-endpoints.md` (if applicable)
4. Routing entry → `AGENTS.md` Core Loop § Execute
5. REF codes → `docs/foundation-map.md`
6. Index updates → `docs/00-index.md`
7. Run `make docs-lint` to verify
