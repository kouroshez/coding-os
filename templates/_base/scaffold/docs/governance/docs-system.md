<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-05-08 -->
# Documentation System Policy

Purpose: Define the canonical documentation taxonomy, naming rules, file headers, and navigation contract for all active docs.
Read when: Creating, moving, splitting, or validating documentation files.
Skip when: You only need to consume a playbook or domain doc without changing the docs system.
Read next: [docs-first-protocol.md](docs-first-protocol.md), [agent-workflow.md](agent-workflow.md), [task-lifecycle.md](task-lifecycle.md)

> Nav: [Docs Index](../00-index.md)

## SSOT Direction — Docs First, Code Follows

Docs are the source of truth; code is the implementation that must match. The full read-anchor-edit procedure lives in [docs-first-protocol.md](docs-first-protocol.md) and is enforced by:

- **Rule 0** ([critical-rules.md#rule-0](critical-rules.md#rule-0--docs-first)) — `enforce-doc-anchor.sh` BLOCKS code Write/Edit without a populated `.doc-anchor`.
- **Rule 19** ([critical-rules.md#rule-19](critical-rules.md#rule-19--docs-are-the-contract--never-extend-code-beyond-doc-spec)) — `enforce-doc-sync.sh` WARNs PostToolUse when code drift leaves docs stale.
- **`nudge-docs-first.sh`** — UserPromptSubmit nudge that recommends `cos_doc_search` / `cos_doc_header` when a code-edit intent is detected and no anchor exists.

If you are about to edit code, stop here and read [docs-first-protocol.md](docs-first-protocol.md) first.

## Layer Model

- `index` — navigation hub, parent/child routing only
- `playbook` — task workflow with read selection guide and verification
- `spec` — canonical product/content requirements
- `policy` — process or governance rules
- `reference` — supporting factual reference, not primary truth
- `adr` — immutable decision record
- `task` — execution log for a specific work item

## Naming Rules

- Root index: `docs/00-index.md` (master navigation hub).
- Sub-directory indexes: `00-index.md` in directories that have many files (architecture, playbooks, api-contracts).
- Per-file `<file>.INDEX.md` sidecars are NOT canonical — only `00-index.md` and `section-index.md` are recognized index forms.
- Task SSOT: `docs/tasks/TASK-###-slug.md` (one detail file per active or completed task). Live board view: `cos board` (DB-mirrored from these files). There is no flat `docs/tasks.md` index.
- Playbooks: `kebab-case.md`
- ADRs: `ADR-###-kebab-case.md`
- Tasks: `TASK-###-slug.md`
- Historical archive docs: `YYYY-MM-topic.md` under `governance/archive/`
- Other active docs: `kebab-case.md`
- No version suffixes in filenames (`*-V1.md`, `*-v2.md`). Versioning lives in frontmatter `updated:` only.

## Header Contract

Every file inside `docs/` starts with:

```html
<!-- domain:XXX | layer:index|playbook|spec|policy|reference|adr|task | ssot:true|ref | updated:YYYY-MM-DD -->
```

## Opening Block Contract

Immediately after the H1, every active doc includes these four lines. Two equivalent forms are accepted; pick one per file.

**Long form** (default):

- `Purpose:`
- `Read when:`
- `Skip when:`
- `Read next:`

**Short form** (token-tight, ~30% fewer header bytes — recommended for high-traffic routing files):

- `> P:`
- `> R:`
- `> S:`
- `> N:`

`docs-lint` accepts either form. `cos_doc_header` (MCP) parses both into the same structured response (`opening_block.purpose` / `read_when` / `skip_when` / `read_next`). The `md_links` graph extractor emits `read_next` edges from either.

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

**Single SSOT (Scrumban):**

- `docs/tasks/TASK-###-slug.md` — **canonical detail file**. One per active or completed task. Holds frontmatter (swimlane / kind / epic / labels / status / priority / appetite / depends_on / blocked_by / references), Outcome, Read First, Acceptance, Work Log, Rollback. Authored from `docs/governance/templates/task-detail.md`. Token cap: warn ≥1.5k, block ≥3k (Rule 14).
- `cos board` (or `cos board --web`) — **live view** rendered from `core/board_os/db.py`. The DB is a derived mirror of the detail files (mtime-incremental sync); the file is SSOT, the DB is the index.
- Status transitions go through `cos task-move` / `cos task-start` / `cos task-done` (or the MCP `cos_task_*` family). These write the detail-file frontmatter and the DB atomically — never edit status by hand in only one place.
- There is no flat `docs/tasks.md` index. The legacy index file has been retired in favor of `cos board` + per-task detail files.

**Lifecycle:**

- A task is created via `cos task-create` (writes both the detail file and the DB row).
- Once a task is in_progress, completed, or blocked → the detail file under `docs/tasks/` is REQUIRED. DB-only mode exists in `core/board_os/workflow.py` but is reserved for migrations and tests, never normal authoring.
- Companion docs (checklists, research annexes that would break the 3k cap) use `layer:reference`, link back to the parent task, and never carry canonical status.
- `docs/governance/templates/task-detail.md` is a template reference, not a live task record. Do not edit it as if it were a task.

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

## Authoring a NEW Doc — Read This First

Before creating any new file under `docs/`, read [`templates/doc-cheat-sheet.md`](templates/doc-cheat-sheet.md). It contains:

- The decision tree (intent → layer → directory → token budget).
- Mandatory frontmatter + opening block contract.
- Required sections per layer (adr · playbook · runbook · post-mortem · spec · policy · reference · task).
- Anti-patterns (code dumps, version-suffix files, "future work" sections).
- Token-efficiency rules — the audience is the next agent that has to act on the doc.

Available templates under `docs/governance/templates/`:

- `task-detail.md` — task execution log.
- `runbook-template.md` — operational SOP for an alert / incident type.
- `post-mortem-template.md` — blameless retrospective for a specific incident.
- `playbook-template.md` — repeatable workflow.
- `security-review-template.md` — OWASP-aligned per-change checklist.
- `doc-cheat-sheet.md` — decision guide for new docs (read first).

## Audit Trail

Every doc edit can be appended to the immutable `doc_audit_trail` table via `cos_audit_log_record` MCP tool. Reverts are modeled as a new row with `action='reverted'` + `supersedes_id` pointing at the prior decision — never a row rewrite. The hub UI surfaces the per-doc timeline via `cos_audit_log_timeline`.

Use cases:
- Investigating "why did we change X back to Y?" — `cos_audit_log_query --doc-path <path>`.
- Detecting agent hallucination drift — `cos_audit_log_query --only-reverted` shows decisions the team explicitly walked back.
- Onboarding context — a doc's full decision history travels with the file.
