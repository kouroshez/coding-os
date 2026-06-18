<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-05-08 -->
# Agent Workflow Policy

Purpose: Domain routing, task protocol, escalation, and memory contract — supplements `AGENTS.md` § Core Loop.
Read when: Multi-domain task, blast-radius doubt, escalation, or memory-flow question.
Skip when: Task clearly routed; AGENTS.md fragments suffice.
Read next: `task-lifecycle.md`, the matching playbook in `../playbooks/`.

> Nav: [Docs Index](../00-index.md) | [Docs System](./docs-system.md)

> Canonical execution loop is in `AGENTS.md` § Core Loop and `AGENTS.md` § Request Routing. This file holds policy detail not repeated there.

## Domain Classification Checklist

Multi-domain task — resolve by priority:

1. Security-sensitive? → security overlay required regardless of primary domain.
2. Backend models or API? → backend playbook (if installed).
3. Frontend components or pages? → frontend playbook (if installed).
4. Content, copy, or SEO? → content playbook (if installed).
5. Docs, governance, or workflow? → docs governance playbook (if installed).
6. Research / validation only? → research & validation playbook (if installed).

When two domains share weight, route to the higher blast-radius domain first.

**Blast radius ranking** (highest → lowest):

1. Database schema — affects all consumers, hard to roll back.
2. Backend API contracts — affects frontend + external integrations.
3. Backend business logic — data integrity, API responses.
4. Frontend state/routing — UX + navigation.
5. Frontend UI/styling — appearance only.
6. Documentation — no runtime impact.

## Task Protocol (Scrumban)

| Transition | Command | Effect |
|---|---|---|
| icebox → in_progress | `cos task-start TASK-<id>` | Marks the detail file `in_progress`, writes `.coding-os/<agent>/.task-current`, mirrors to the board DB, enforces WIP cap. |
| in_progress → testing | `cos task-move TASK-<id> --to testing` | Signals that the change is built and awaiting verification. |
| → done | `cos task-done TASK-<id>` | Validates Acceptance, appends Work Log, mirrors to the board DB, appends a `changes.log` entry. |
| → blocked | `cos task-move TASK-<id> --to blocked --reason "why"` | Records the blocker on the detail file and on the board. |
| Session bootstrap | `cos daily` | Surfaces WIP, blockers, age, and roadmap phase. |

The board state lives in `docs/tasks/TASK-<id>-<slug>.md` (canonical) and is mirrored to `.coding-os/coding-os.db` (derived index). There is no flat `docs/tasks.md` index; `cos board` renders the current state on demand.

`make task-*` wrappers exist only as thin aliases for the `cos task-*` commands; new automation should call `cos` directly.

## Change Initiation Path

Every non-trivial change follows this order — no skipping:

1. **PRD/spec** — define *what* and *why* (edit the doc first; Rule 19)
2. **Requirements / acceptance criteria** — atomic, testable
3. **Schema / migrations** — data shape before any code
4. **Code** — implement against spec
5. **Docs sync** — update any doc that drifted (`enforce-doc-sync.sh` surfaces these)

If two sources conflict: higher blast-radius wins (see Blast Radius ranking above). Update the lower-rank doc — never the higher.

## Minimal-Read & Context Hygiene

- Do not read an entire domain folder when one index file routes correctly.
- Stop reading when a file no longer changes the decision.
- Playbook Read Selection Guide caps at 10 files (most tasks 3–6).
- After reading: extract the fact into the task detail's Notes; drop the raw file from working memory.
- After commands (test/lint/build): keep pass/fail + key errors only; discard full output.
- Subagent results must be condensed summaries (≤2000 tokens), never raw dumps.

## Script Output Format

Task and infrastructure scripts use standardized prefixes:

- `OK: <message>` — success
- `ERROR: <message>` — fatal (exits 1)
- `WARN: <message>` — non-fatal (stderr)
- `INFO: <message>` — informational

## Escalation Rules

- Log contradictions and missing truth in `docs/_meta/questions.md`.
- Stop when product intent is not derivable from SSOT — never invent schema names, route shapes, or copy.
- RETRY_LIMIT — second identical failure with no new evidence → `cos task-move TASK-NNN --to blocked`.

## Memory & Learning (Thinking OS)

Self-learning layer on the thinking_os MCP server (`.coding-os/coding-os.db`).

**Data flow:** Auto-Capture (per tool call) → Outcome Record (per task) → Learning Loop (every 10 tasks) → Memory Inject (next session).

**3-layer progressive disclosure** (memory queries):

1. `cos_search` — compact index (~50 tokens/result).
2. `cos_timeline` — chronological context (~150 tokens).
3. `cos_details` — full observation (~500 tokens).

**Learning Loop** (conditional, non-blocking): extracts patterns from outcomes, suggests rules at 3+ similar failures, tunes routing weights per domain × complexity. Runs every 10 completed tasks.

**Outcome types:** `success`, `rework`, `partial`, `blocked` — recorded for every task including blocked.
