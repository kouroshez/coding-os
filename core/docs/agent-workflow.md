<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-03-18 -->
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

1. Security-sensitive? → Security overlay required regardless of primary domain. Read ALL applicable sub-files (04a auth, 04b web, 04c download, 04d compliance), not just one.
2. Touches backend models or API? → Backend API playbook
3. Touches frontend components or pages? → Frontend UI playbook
4. Touches content, copy, or SEO? → Content & SEO playbook
5. Touches docs, governance, or workflow? → Docs Governance playbook
6. Research or validation only? → Research & Validation playbook

Multi-domain tasks (e.g. admin APIs spanning products + orders + auth): read architecture docs for **each** domain from the playbook's Task-to-File Mapping, not just one. If two domains share equal weight, route to the one with higher blast radius first.

**Blast radius ranking** (highest to lowest):

1. Database schema — affects all consumers, hard to roll back
2. Backend API contracts — affects frontend + external integrations
3. Backend business logic — affects data integrity, API responses
4. Frontend state/routing — affects user experience and navigation
5. Frontend UI/styling — affects appearance only
6. Documentation — no runtime impact

- Code quality concern (error handling, testing gaps, clean code) → domain engineering rules (§ Error Handling, § Edge Case Testing)

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
- **COMPLICATED / COMPLEX** → Invoke `Skill skill: "thinking_os"`, run Zoom cycle (map dimensions, identify risks/actors/rules), then provide structured answer informed by Zoom output. No Core Loop needed, but the answer benefits from systematic analysis.

### Category B: Task Execution

- User says "work on TASK-043" or "do the next task"
- An open task exists and is ready for implementation

Action: Enter Core Loop (Initialize → Classify → Orient → Plan → Execute → Verify & Close — see AGENTS.md § Core Loop). Classify is dry (no file reads). Orient reads only what Classify identified. Plan synthesizes findings.

### Category C: Ad-Hoc Implementation

- User requests code/doc changes without an existing task
- Examples: "refactor this module", "add feature Y", "fix this bug"

Action by complexity:

1. **CLEAR** trivial fixes (typos, 1-line, formatting) → proceed without a task
2. **COMPLICATED / COMPLEX** or non-trivial → propose `make task-create` first. Classify phase helps scope the task.
3. Once task exists → Core Loop

### Category D: Verification or Audit

- "Check if API contracts match docs"
- "Run the linter and fix issues"
- "Security audit this module"

Action by complexity:

- **CLEAR** → Run relevant `make` command. Report results. Fixes follow Category C rules.
- **COMPLICATED / COMPLEX** → Invoke `Skill skill: "thinking_os"`, Zoom cycle first (map: which systems? what risks? what scope? what dimensions?), then systematic review. Report findings with structured analysis. Fixes follow Category C rules.

## Decision Priority

When constraints conflict, resolve in this order:

1. **Truth** — never fabricate; log unknowns in `docs/questions.md`
2. **Correct routing** — right mode, right playbook, right files
3. **Minimal context** — read only what changes the decision
4. **Safe execution** — stop before risky assumptions
5. **Conversational quality** — helpful and concise, never at cost of accuracy

## Task Start Protocol

See `task-lifecycle.md` for the canonical task start / resume / close flow. The points below supplement it.

## Hook & Skill Enforcement — What Fires, What Blocks

Hooks are the **deterministic guardrail layer** (Rule 1.4 of Claude Certified Architect Foundations — programmatic enforcement beats prompt-based guidance whenever business rules matter). SSOT for registration: [core/hooks/registry.yaml](../hooks/registry.yaml). Adapter template files are generated from it via `make regen-adapter-templates`.

Three classes of hook by effect:

| Effect | Example hooks | What the agent sees |
|---|---|---|
| **BLOCK** (`exit 2`) | `enforce-skill`, `enforce-zoom`, `enforce-doc-anchor`, `enforce-task-start`, `block-protected-files`, `block-migration-conflict`, `block-hardcoded-literals`, `block-uv-heredoc`, `block-bad-patterns`, `block-secrets`, `block-dangerous-commands`, `block-prod-writes` | stderr appears in agent context — the tool call is refused; agent must fix before retrying |
| **WARN** (`exit 0` + stderr) | `remind-dogfood`, `regen-reminder`, `warn-mcp-down`, `warn-template-drift`, `remind-learn-validate`, `test-first-reminder`, `playwright-reminder` | advisory stderr in agent context; action proceeds |
| **SILENT** (`exit 0`, log-only) | `capture-observation`, `session-context`, `session-end`, `check-capture-worked`, `check-agents-md-size`, `check-agents-md-refs`, `enforce-memory-check` | nothing in agent context — traces go to `.coding-os/.hooks.log` |

**Why silent hooks feel invisible:** By design. SILENT hooks never interrupt the agent's flow. To see them live, open a second terminal:

```bash
cos hooks-log --follow          # real-time tail
cos hooks-list --agent claude   # what's registered for this agent
```

Zero hook-log entries for a hook you expected → the agent runtime isn't delivering the event, typically because `.claude/settings.json` or `.codex/hooks.json` changed mid-session and the runtime didn't reload. Restart the agent.

### Skill enforcement — the "loaded skill proves the hook works" pattern

`enforce-skill.sh` + `enforce-zoom.sh` are the loudest BLOCK hooks. When you hit them:

- **`enforce-skill` blocked** — you tried to Write/Edit a code file without first invoking the matching skill (`clean-code`, `python-django`, `nextjs-react`, ...). This is NOT a false positive — the skill contains guardrails (fail-closed errors, no PII in logs, typed exceptions) that must shape the code you're about to write. Load the skill, then retry. The block proves the regime caught a real policy violation.
- **`enforce-zoom` blocked** — you recorded a `COMPLICATED` or `COMPLEX` Complexity Gate but did not record a Plan checkpoint (`.coding-os/.zoom-checkpoint`). Thinking-OS requires Problem Framing before code writes for non-CLEAR tasks. Record the checkpoint with `bash core/hooks/write-state.sh .coding-os/.zoom-checkpoint "PROBLEM_FRAMED"`, then retry.

Blocks are a feature, not a bug. If you see one, do not bypass — the hook almost always caught a skipped step.

## Session Lifecycle — Memory, Learning, and Abandonment

Three session events drive the cognitive layer. Understanding them is essential for anyone using multiple chats in parallel or abandoning one mid-task.

### On every Write / Edit — `capture-observation` (PostToolUse)

- Fires in <1 ms, spawns [capture.py](../thinking_os/capture.py) in a background process.
- Records an `observations` row per edit (session_id, tool, file_path, content excerpt).
- Errors from the background process land in `.coding-os/.capture-errors.log`; the Stop hook surfaces them at session end so silent capture failures can't swallow an entire session invisibly.

### On session start — `session-context` (SessionStart)

Behavior depends on `source`:

- **`startup`** — fresh session. In order:
  1. **Orphan recovery** — reads the previous session_id from `.coding-os/session-id` and calls `session_summary.py` for it. This is idempotent (UPSERT) so clean-Stop sessions are unaffected; abandoned sessions finally get their summary row. Logged as `[session-context] [recovered] prev_session=...`.
  2. Generates a new `session_id` (format `ses-YYYYMMDD-HHMMSS-xxxx`) and writes it to `.coding-os/session-id`.
  3. **Clears stale state files** from the previous session: `.thinking_os-gate`, `.task-current`, `.zoom-checkpoint`, `.active-skill`. This is why gate/task markers from yesterday's chat don't leak into today's.
- **`compact`** / **`resume`** — existing session continues. Re-injects the critical workflow rules (task management, Verification Matrix, Complexity Gate, Domain skill) so the post-compaction agent doesn't forget them. Session ID is preserved.

### On session end — `session-end` (Stop)

- Runs [session_summary.py](../thinking_os/session_summary.py) — aggregates the session's observations, files touched, and breakthroughs into one `session_summaries` row.
- Runs [session_enrich.py](../thinking_os/session_enrich.py) — links this session to the previous one for episode chaining (outcome_history narrative).
- Fire-and-forget: never blocks, never errors visibly.

### What if the user abandons a chat mid-task?

Scenario: user opens tab A, does 10 edits, closes the tab without a clean Stop, opens tab B.

| Artifact | Survives? | Why |
|---|---|---|
| **Observations** (per-edit rows in `observations`) | ✅ YES | captured on PostToolUse, already in DB before the tab closed |
| **Task state** (`.task-current`, gate, checkpoint) | ✅ Cleared cleanly | tab B's `session-context` on `startup` rm's them before work begins |
| **Session summary** (`session_summaries` row) | ✅ Auto-recovered on next startup | `session-context` on `startup` calls `session_summary.py` for the previous session_id before overwriting it — idempotent UPSERT builds the row from observations if Stop never fired |
| **Episode chain** (previous-session pointer) | ⚠️ Partial | basic previous-session pointer is set by the recovered summary, but `session_enrich` semantic fields (domain counts derived from `.thinking_os-gate`) may be empty if the gate file was already cleared |

**Concrete recovery for a "reclaimed" task:** tab B's agent can still resurrect everything by:

1. `cos_timeline limit=50` — see observations from the orphaned session grouped by timestamp.
2. `cos_search "<task keywords>"` — pull the concrete patterns the old session wrote.
3. `make task-context TASK=<num>` — rehydrate the task detail file and its `Session Checkpoint` (if the abandoning agent wrote one to the task body, it persists regardless of hooks).

**Mitigation for important work:** write the Session Checkpoint block in the task detail file before long pauses — it lives in git, not in ephemeral hook state, so it survives even hard crashes.

### What the learning layer does per message

No hook writes to the learning layer on every user prompt — that would produce too much noise. Instead:

- **Observations** accumulate silently on every Write/Edit (the raw signal).
- **Learned patterns** are extracted on demand via `cos_learn_extract` (scans `task_outcomes` for recurring rework/skill/complexity patterns with ≥3 occurrences).
- **Pattern confidence** updates only via `cos_learn_validate` — the agent must tell thinking_os whether a suggested pattern actually helped. Without this feedback loop the ranking never improves.
- **Breakthroughs** are recorded via `cos_learn_narrative` after a rework→success cycle. This is the single highest-value thing an agent can do at the end of a hard task.

If you close a chat mid-task **before calling `cos_learn_validate` / `cos_learn_narrative`**, the one-off learning signal for that task is lost — but the raw observations aren't, so a future session can still mine them.

