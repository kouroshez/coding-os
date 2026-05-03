<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-01-01 -->
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

## Task Protocol (`make` targets)

| Transition | Command | Effect |
|---|---|---|
| Open → in-progress | `make task-start TASK=<num>` | Creates detail file from `governance/templates/task-detail.md` (with domain REF codes), marks `[/]` in `docs/tasks.md`, runs `task-context`. |
| in-progress → done | `make task-done TASK=<num> TYPE=<type> MSG="title" WHAT="impact" FILES="…"` | Validates type ∈ {feat,fix,refactor,docs,test,infra}, marks `[x]`, appends entry to `changes.log`. |
| → blocked | `make task-block TASK=<num> REASON="why"` | Marks `(BLOCKED: reason)`, appends entry to `docs/questions.md`. |
| Session bootstrap | `make session-init` | Once per session — surfaces phase from `roadmap.md`, recent `changes.log`, open task + question counts. |

Always provide `WHAT` and `FILES` on completion for traceability. For Phase L scrumban, prefer `cos task-*` (see `task-lifecycle.md`).

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

- Log contradictions and missing truth in `docs/questions.md`.
- Stop when product intent is not derivable from SSOT — never invent schema names, route shapes, or copy.
- RETRY_LIMIT — second identical failure with no new evidence → `make task-block`.

## Memory & Learning (Thinking OS)

Self-learning layer on the thinking_os MCP server (`.coding-os/coding-os.db`).

**Data flow:** Auto-Capture (per tool call) → Outcome Record (per task) → Learning Loop (every 10 tasks) → Memory Inject (next session).

**3-layer progressive disclosure** (memory queries):

1. `cos_search` — compact index (~50 tokens/result).
2. `cos_timeline` — chronological context (~150 tokens).
3. `cos_details` — full observation (~500 tokens).

**Learning Loop** (conditional, non-blocking): extracts patterns from outcomes, suggests rules at 3+ similar failures, tunes routing weights per domain × complexity. Runs every 10 completed tasks.

**Outcome types:** `success`, `rework`, `partial`, `blocked` — recorded for every task including blocked.
