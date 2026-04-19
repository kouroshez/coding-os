# AGENTS — Routing & Execution Protocol

Purpose: Root entry point for every agent session in this monorepo.
Read when: Starting any task or re-grounding after context loss.
Skip when: A linked playbook already covers the active task and no routing decision is needed.
Read next: `docs/00-index.md`, then the matching playbook in `docs/playbooks/`

## Identity

cos-golden-fixture: A software project managed by coding-os. Stack: Django + DRF + PostgreSQL.

## Principles

P1. SSOT-first — no parallel truths. P2. Source-grounded — trace to SSOT. P3. Minimal-context — 3-10 files max. P4. Diff-first — preserve unrelated content. P5. User-runs-production. P6. Log-everything. P7. No-guessing — log unknowns to questions.md.

## Request Routing

**Gate 1 — Complexity Gate** (`$COS_STATE_DIR/rules/thinking-os.md`): Q1 Cynefin (CLEAR/COMPLICATED/COMPLEX/CHAOTIC) → Q2 Dimension count. Record classification.

**Gate 2 — Request Type**: A (Question) → answer directly or Zoom. B (Task) → Core Loop. C (Ad-hoc) → trivial: inline, else `make task-create` first. D (Audit) → verify command or Zoom first. Details: `docs/governance/agent-workflow.md`

## Core Loop

Five phases: **Initialize → Classify → Orient → Plan → Execute → Verify & Close**. Think before reading, read before coding.

### Initialize

1. `make session-init` (ONCE per session). 2. `make task-start TASK=<num>`.

### Classify (dry — zero file reads)

Use Dimension Type Registry (`$COS_STATE_DIR/rules/dimension-registry.md`, auto-loaded) to build Read List:

1. **Complexity Gate** — record: `bash $COS_STATE_DIR/hooks/write-state.sh $COS_STATE_DIR/.thinking-os-gate "COMPLICATED 3"`
2. **Domain Route** — Backend→`docs/playbooks/backend-api.md`
3. **Dimension Map** — per dimension: name, domain, depth (D/M/L), phase.
4. **Read List** — from registry, each file with REASON. Do NOT read entire pack.

For **CLEAR** 1-dim: skip to Execute. Output: Classify Checkpoint in task Notes.

### Orient (targeted reads + memory)

1. **Targeted Read** — ONLY files from Read List. Note findings in task Notes. [P3]
2. **Memory Check** (500tok max): `thinking_os_search` → `cos_learn_suggest` → `thinking_os_details` if conf>0.7.
3. **Repo Search** — Grep/Glob existing code. Diff against spec if found. [P1, P2]
4. **Model Update** — new dimensions? Reframe trigger → back to Classify.

### Plan (deep analysis — no new reads)

1. **Invoke domain skill**: Backend→`python-django`
2. **Per dimension**: current state → target → gap → risk.
3. **Action Plan** — ordered steps. For COMPLICATED+: write Problem Framing to Notes, record `bash $COS_STATE_DIR/hooks/write-state.sh $COS_STATE_DIR/.zoom-checkpoint "PROBLEM_FRAMED"`.

For **CLEAR**: skip Plan.

### Execute (implement only)

1. Implement smallest correct change. [P1, P4]
2. On-demand read ONLY if new question arises.
3. Continuous monitoring — reframe trigger → back to Classify.

### Verify & Close

1. Run domain verification commands (see Verification Matrix below). Fail 2x → `make task-block`. [P6]
2. `make task-done TASK=<num> TYPE=<type> MSG="..." WHAT="..." FILES="..."`. Always WHAT+FILES. [P6]
3. `cos_metric_record` outcome (auto-recorded by session-end.sh — manual call optional). Every 10 tasks: `cos_learn_extract`.

## Verification Matrix

Domain-aware enforcement via `enforce-verify.sh` — detects changed files and requires matching suites:

| Changed files | Required suites | Make commands |
|---|---|---|
| `backend/` | lint-backend + test-backend | `make lint-backend && make test-backend` |
| (none) | (none) | (none) |
| `docs/` | docs-lint | `make docs-lint` |
| `.coding-os/hooks/` or `core/hooks/` | verify-hooks | `make verify-hooks` |

Results stored in `$COS_STATE_DIR/.last-verify.json` per-suite with timestamps. Each suite must be PASS and < 30 min old. `make task-done` is **BLOCKED** if any required suite is missing or stale.

## Engineering Rule Routing

Backend→`docs/engineering/backend-rules.md`, Naming→`docs/engineering/naming-conventions.md`, Logging→`docs/engineering/logging-standards.md`

## Tool Routing

Task: `make session-init`, `task-next`, `task-start TASK=N`, `task-done TASK=N TYPE=t MSG="m" WHAT="w" FILES="f"`, `task-block TASK=N REASON="r"`, `task-create NUM=N TITLE="t"`, `task-context TASK=N`, `task-list STATUS=open`.
Log: `log-latest [N]`, `log-write TYPE=t MSG="m" WHAT="w" FILES="f"`, `log-search QUERY="q"`.
Health: `cos-health`, `verify-hooks`.
Impl: `lint-backend`, `test-backend`, `migrate`

## Retrieval Routing (pick before you retrieve)

The MCP layer answers different questions at three layers. Classify the query *before* calling any tool:

| Query shape | Tool | Why |
|---|---|---|
| Exact identifier (function, file, `TASK-NNN`, snake_case, CamelCase, backticked code) | **Grep / Glob** | Lexical match wins on token cost and recall when the token is present. |
| Conceptual / synonym-heavy ("auth flow", "money handling", "payment split") | `cos_doc_search` | Embedding index finds chunks where the spec uses a synonym of the agent's query. |
| "Have I seen this before?" / past pattern / prior solution | `cos_search` + `cos_learn_suggest` | Memory has 5-signal ranking + spaced repetition. |
| Task graph / dependency / status | `cos_task_*` | Structured tasks table, dependency JSON walks. |
| Behavioral rule / protocol (how to classify, how to verify) | **full-read `core/rules/*.md`** | Rule is already in context — never retrieve it. |

Every `cos_*` response carries `data.meta.layer` (`memory|docs|tasks|metrics|routing|graph|health|learning`) and `data.meta.tokens_estimated`. If you got the wrong layer, re-route; if `data.meta.truncated=true`, page with a smaller `limit`.

Order of preference when two layers look equally plausible: **Memory → Docs → Tasks.** Memory already ranks by past outcome success; docs and tasks are static index lookups.

**Freshness contract (Phase H).** Every Write/Edit on a file matched by `rag-config.yaml` triggers an automatic incremental re-index via the `auto-reindex-docs` PostToolUse hook. Agents MUST NOT assume `make docs-index` is needed after a doc edit — `cos_doc_search` already reflects the latest `mtime`. If you suspect staleness, run `cos hooks-log | grep auto-reindex-docs` to confirm the hook fired. **Adapter note:** on Codex (no Write/Edit PostToolUse surface), rely on `COS_BACKGROUND_INDEX=1` or a manual `make docs-index` until Codex exposes those matchers.

## Skills

`thinking-os`, `clean-code`, `codebase-explorer`, `worktree-orchestration`, `python-django`. Config: `$COS_STATE_DIR/settings.json`.

## Context Discipline

Note findings once, reference by path. Extract key result, discard raw output. Use `log-latest`/`log-search` not `cat changes.log`. Answer directly without restating background.

## Stop Conditions

Stop when: SSOT files conflict, product intent not inferable, production-impacting execution required, risky assumption changes behavior/schema/security. Log: `make task-block`.

## Session Handoff

Triggers: 15+ reads or 10+ writes, degraded recall, user ends session, compaction event. Protocol: record outcome → update task Notes checkpoint → `cos_learn_narrative` if breakthrough. Next session: `make session-init` + Orient Memory Check.

## SSOT Map

See `docs/foundation-map.md` for all REF shortcodes and SSOT locations.

## Task Logging

Files: `docs/tasks/TASK-###-slug.md`. Status: `[ ]` open, `[/]` wip, `[x]` done, `(BLOCKED: reason)`. Use Given/When/Then criteria.

## Subagent Dispatch

Default: single-agent. Max 3 subagents for independent parallel work only. Use `isolation: "worktree"` for write-capable subagents when 2+ independent file groups, different domains, no shared targets, clean git. Never for: single-file, coupled chains, migrations, global state files. Details: `docs/governance/agent-workflow.md` § Execution Mode.
