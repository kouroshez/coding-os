<!-- domain:DOCS | layer:policy | ssot:true | updated:{{DATE}} -->
# Agent Workflow Policy

Purpose: Execution details and escalation rules that complement the Core Loop in AGENTS.md.
Read when: Task classification is ambiguous, minimal-read strategy needs clarification, or escalation is needed.
Skip when: Task is clearly routed and no domain ambiguity exists.
Read next: `task-lifecycle.md` and the matching playbook in `../playbooks/`

> Nav: [Docs Index](../00-index.md) | [Docs System](./docs-system.md)

## Reference

The canonical execution loop is in `AGENTS.md` § Core Loop. This file provides supporting detail only.

## Domain Classification Checklist

When a task spans multiple domains, resolve with this priority:

1. Security-sensitive? → Security overlay required regardless of primary domain.
2. Touches backend models or API? → Backend playbook (if installed)
3. Touches frontend components or pages? → Frontend playbook (if installed)
4. Touches content, copy, or SEO? → Content playbook (if installed)
5. Touches docs, governance, or workflow? → Docs Governance playbook (if installed)
6. Research or validation only? → Research & Validation playbook (if installed)

Multi-domain tasks: read architecture docs for **each** domain from the playbook's Task-to-File Mapping, not just one. If two domains share equal weight, route to the one with higher blast radius first.

**Blast radius ranking** (highest to lowest):

1. Database schema — affects all consumers, hard to roll back
2. Backend API contracts — affects frontend + external integrations
3. Backend business logic — affects data integrity, API responses
4. Frontend state/routing — affects user experience and navigation
5. Frontend UI/styling — affects appearance only
6. Documentation — no runtime impact

## Request Classification

Every incoming request passes through two gates (see AGENTS.md § Request Routing):

**Gate 1 — Complexity Gate:** Run Thinking OS Complexity Gate (Q1 Cynefin + Q2 Dimensions) on every non-trivial request. This determines HOW DEEP to think, regardless of request type.

**Gate 2 — Request Type:** Classify into one of the categories below. The complexity result from Gate 1 determines the action path within each category.

### Category A: Conversational (no task needed)

- Questions about codebase, architecture, or design
- Explaining how something works
- Research or analysis without code/doc changes
- Reviewing or auditing existing state
- Proposing a plan or comparing approaches

Action by complexity:

- **CLEAR** → Answer directly. Read relevant files as needed. No Core Loop.
- **COMPLICATED / COMPLEX** → Invoke `Skill skill: "thinking_os"`, run Zoom cycle, then provide structured answer. No Core Loop needed, but the answer benefits from systematic analysis.

### Category B: Task Execution

- User says "work on TASK-043" or "do the next task"
- An open task exists and is ready for implementation

Action: Enter Core Loop (Initialize → Classify → Orient → Plan → Execute → Verify & Close — see AGENTS.md § Core Loop).

### Category C: Ad-Hoc Implementation

- User requests code/doc changes without an existing task
- Examples: "refactor this module", "add feature Y", "fix this bug"

Action by complexity:

1. **CLEAR** trivial fixes (typos, 1-line, formatting) → proceed without a task
2. **COMPLICATED / COMPLEX** or non-trivial → propose `make task-create` first
3. Once task exists → Core Loop

### Category D: Verification or Audit

- "Check if API contracts match docs"
- "Run the linter and fix issues"
- "Security audit this module"

Action by complexity:

- **CLEAR** → Run relevant `make` command. Report results. Fixes follow Category C rules.
- **COMPLICATED / COMPLEX** → Invoke `Skill skill: "thinking_os"`, Zoom cycle first, then systematic review.

## Decision Priority

When constraints conflict, resolve in this order:

1. **Truth** — never fabricate; log unknowns in `docs/questions.md`
2. **Correct routing** — right mode, right playbook, right files
3. **Minimal context** — read only what changes the decision
4. **Safe execution** — stop before risky assumptions
5. **Conversational quality** — helpful and concise, never at cost of accuracy

## Task Start Protocol

Core Loop Initialize step 2: `make task-start TASK=<num>` where `<num>` is the user-specified task number, or the output of `make task-next` if none specified.

The script automates the transition from open to in-progress:

1. Checks if primary detail file exists
2. If missing → creates it from `docs/governance/templates/task-detail.md` with domain-aware REF codes
3. Marks `[/]` in `docs/tasks.md` (skips if already [/], warns if [x] or BLOCKED)
4. Runs `task-context` to display read-first refs, verification, and warnings

## Task Completion Protocol

`make task-done TASK=<num> TYPE=<type> MSG="title" WHAT="impact" FILES="changed files"` automates the transition from in-progress to done. Always provide WHAT and FILES for traceability.

1. Validates task exists and is open `[ ]` or in-progress `[/]`
2. Validates TYPE is one of: `feat`, `fix`, `refactor`, `docs`, `test`, `infra`
3. Marks `[x]` in `docs/tasks.md`
4. Appends structured entry to `changes.log`

## Task Block Protocol

`make task-block TASK=<num> REASON="why"` automates the transition to blocked:

1. Validates task exists and is open `[ ]` or in-progress `[/]`
2. Changes checkbox to `(BLOCKED: reason)` in `docs/tasks.md`
3. Appends an entry to `docs/questions.md`

## Session Initialization

`make session-init` runs ONCE per session (not per task). It grounds the agent with these outputs:

1. Current project phase from `docs/roadmap.md`
2. Recent changes from `changes.log`
3. Open tasks count and open questions count

For conversational requests, session-init is optional. For Core Loop execution, session-init is step 1.

## Minimal-Read Principle

- Do not read an entire domain folder when one file or index can route to the right source.
- Stop reading when a file no longer changes an implementation decision.
- Use `make task-context TASK=<num>` for task-oriented context assembly instead of manual wide scans.
- Playbook Read Selection Guides are 3-10 files max — Classify phase generates a Read List with reasons.

### Context Hygiene

- After reading a file for reference, note the extracted fact in the task detail file's Notes section. Do not rely on the raw file staying in context.
- After running a command (test, lint, build), extract pass/fail and key errors. Drop full output from working memory.
- Subagent results must be condensed summaries (max 2000 tokens), not raw exploration dumps.

### Script Output Format

All task and infrastructure scripts use standardized output prefixes:

- `OK: <message>` — success
- `ERROR: <message>` — fatal error (exits with code 1)
- `WARN: <message>` — non-fatal warning (to stderr)
- `INFO: <message>` — informational

## Escalation Rules

- Log contradictions or missing truth in `docs/questions.md`
- Stop when product intent is not derivable from SSOT
- Do not invent schema names, route shapes, or copy
- RETRY_LIMIT: On second identical failure with no new evidence → `make task-block`

## Execution Mode

- Default to single-agent execution.
- Dispatch subagents only for independent parallel **read-only** research, inventory, or verification branches.
- Use at most 3 workers on one task.
- Do not use subagents for normal sequential coding, single-file changes, or tightly coupled edits.
- **Never** pass `isolation: "worktree"` to the Agent tool. Write-capable parallel dispatch is disabled in coding-os projects — orphaned worktrees + locked branches caused recurring deadlocks. All write work runs single-agent on the main working tree.

### Hooks (Deterministic Compliance)

Hooks in `.claude/settings.json` enforce rules that prompt instructions cannot guarantee:

- **PostToolUse** (Write/Edit): Domain-specific verification reminders
- **PostToolUse** (Write/Edit): Auto-capture observations to coding-os.db (fire-and-forget)
- **PreToolUse** (Write/Edit): Complexity Gate blocks code writes until classification recorded
- **PreToolUse** (Write/Edit): Block protected files (changes.log, tasks.md status)
- **PreToolUse** (Bash): Blocks `git add .env` to prevent secret commits

Hooks provide deterministic enforcement. Do not rely on prompt instructions alone for security-critical rules.

## Memory & Learning (Thinking OS)

Self-learning layer built on thinking_os MCP server with SQLite backend (`.coding-os/coding-os.db`).

**Data flow:** Auto-Capture (every tool call) → Outcome Record (every task) → Learning Loop (every 10 tasks) → Memory Inject (next session).

**3-layer progressive disclosure** for memory queries:

1. `cos_search` — compact index (~50 tokens/result)
2. `cos_timeline` — chronological context (~150 tokens)
3. `cos_details` — full observation (~500 tokens)

**Learning Loop** (conditional, non-blocking): extracts patterns from outcomes, suggests rules when 3+ similar failures detected, tunes routing weights per domain/complexity. Runs every 10 completed tasks, not every task.

**Outcome types:** success, rework, partial, blocked. Recorded for every task including blocked tasks.
