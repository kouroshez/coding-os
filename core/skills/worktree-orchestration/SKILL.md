---
name: worktree-orchestration
description: >
  Use when dispatching subagents that write code in parallel.
  Covers worktree isolation patterns, merge strategy, conflict
  resolution, and result aggregation. Load when AGENTS.md
  Subagent Dispatch directs worktree usage.
---

# Worktree Orchestration — Parallel Write Dispatch

## Purpose

Guide the orchestrating agent through safe parallel code dispatch using Claude Code's built-in `isolation: "worktree"` parameter. This skill covers the full lifecycle: pre-dispatch validation, agent dispatch, result aggregation, merge, and cleanup.

**Key constraint:** AGENTS.md § Subagent Dispatch decides WHEN to use worktree. This skill covers HOW.

---

## Internal Mechanics

Understanding how Claude Code manages worktrees prevents repo corruption.

### Naming & Location

- **Branch pattern:** `worktree-<name>` (prefix is hardcoded, `<name>` is auto-generated random slug like `bright-running-fox` or user-specified)
- **Disk location:** `.claude/worktrees/<name>/` inside the repo root
- **Shared `.git`:** All worktrees share the same `.git` directory — commits, branches, and remote tracking are unified
- **`.gitignore`:** `.claude/worktrees/` MUST be in `.gitignore` (already configured) to prevent accidental commits

### Lifecycle

```
Dispatch with isolation: "worktree"
  → Claude Code creates .claude/worktrees/<slug>/ + branch worktree-<slug>
  → Agent works in isolated directory
  → Agent finishes
    ├─ No changes made → auto-cleanup (branch + directory deleted)
    └─ Changes exist → branch + directory persist for orchestrator to merge
```

### Safety Guarantees

- Worktrees branch from current HEAD, not from uncommitted state
- Each worktree has independent staging area and working directory
- Changes in one worktree NEVER affect another or the main working tree
- Claude Code does NOT auto-merge — orchestrator must merge explicitly

### Full Lifecycle (end-to-end)

```
1. DISPATCH    Orchestrator launches Agent with isolation: "worktree"
               → Claude Code creates .claude/worktrees/<slug>/ + branch worktree-<slug>
               → Agent starts working in isolated directory

2. EXECUTE     Agent edits files, runs verification in its worktree
               → Main working directory is untouched
               → Other worktree agents work independently

3. RETURN      Agent finishes and returns to orchestrator:
               → Branch name (e.g., worktree-bright-running-fox)
               → Changed files list
               → Verification pass/fail
               → Summary (max 2000 tokens)

4. COLLECT     Orchestrator waits for ALL agents to finish
               → Does NOT merge incrementally

5. MERGE       Orchestrator merges branches one by one (least risk first):
               → git merge --no-ff worktree-<slug>
               → Run Verification Matrix after each merge
               → If conflict: resolve or escalate to user

6. CLEANUP     After successful merge:
               → git branch -d worktree-<slug>
               → git worktree prune
               → Verify: git worktree list (only main should remain)

AUTO-CLEANUP:  If agent made NO changes → step 3 returns no branch
               → Claude Code auto-deletes worktree + branch (skip steps 5-6)
```

### What Can Go Wrong

| Scenario | Impact | Recovery |
| --- | --- | --- |
| Agent crashes mid-work | Orphaned worktree + branch on disk | `git worktree prune && git branch -D worktree-<name>` |
| Branch accumulation (many agents over time) | Stale branches clutter `git branch` output | `git worktree prune` then delete stale `worktree-*` branches |
| Accidental commit of worktree contents | Huge unrelated files in repo history | Already prevented by `.gitignore` entry |
| Two agents assigned same file | Merge conflict at integration time | Pre-dispatch checklist Q1 prevents this |

---

## Pre-Dispatch Checklist

Before dispatching worktree agents, answer ALL five questions. If any answer is NO (except Q5), fall back to single-agent execution.

1. **Independent work units?** — Can the task be split into groups where NO file appears in more than one group's write set? Shared read-only files (engineering docs, rules) are fine.
2. **No migration files?** — Does any group need to create or modify Django migrations? If yes: single-agent only. Migration ordering is inherently sequential.
3. **Clean git state?** — Does `git status` show no uncommitted changes? Worktree dispatch on a dirty tree risks losing work.
4. **Worth the overhead?** — Does the task span ≥5 files across ≥2 domains? For smaller tasks, single-agent is faster.
5. **Independent verification?** — Can each agent's output be verified in isolation? (Preferred but not blocking.)

---

## Dispatch Pattern

### Agent Tool Call Format

```
Agent tool call:
  subagent_type: "general-purpose" (or domain-specific)
  isolation: "worktree"
  prompt: |
    ## Task Context
    {task description and goal}

    ## File Boundary — WRITE-ALLOWED
    You may ONLY write to these files:
    - backend/apps/products/views.py
    - backend/apps/products/serializers.py
    - backend/apps/products/tests/test_views.py

    ## File Boundary — READ-ONLY
    You may read but NOT write:
    - docs/engineering/backend-rules.md
    - docs/api-contracts/products.md

    ## Verification
    Run: make lint-backend && make test-backend
    Report: pass/fail + changed file list
```

### Rules

- Max **3 workers** per task (inherited from AGENTS.md)
- Each agent prompt MUST include:
  - Explicit write-allowed file list
  - Read-only reference files
  - Verification command to run
  - Task context sufficient to work independently
- The orchestrating agent does NOT enter a worktree — it coordinates from the main working directory

---

## File Boundary Rules

### Partitioning Strategy

Split work by domain boundaries:

| Agent | Domain | Example Write Targets |
|-------|--------|-----------------------|
| Agent 1 | Backend | `backend/apps/{app}/` files |
| Agent 2 | Frontend | `frontend/src/app/{route}/` files |
| Agent 3 | Docs | `docs/` files (non-global) |

### Hard Rules

- **No overlapping write targets.** If two agents need the same file, keep it single-agent or assign the shared file to exactly one agent.
- **Global state files are orchestrator-only.** These files must NOT be in any worktree agent's write set:
  - `AGENTS.md`
  - `docs/tasks.md`
  - `changes.log`
  - `Makefile`
  - `docker-compose.yml`
  - `.env*` files
- **Lock files** (`package-lock.json`, `poetry.lock`, `requirements.txt`) — assign to at most one agent. If multiple agents add dependencies, the orchestrator regenerates the lock file after merge.

---

## Decision Tree

```
Q1: Does this task need subagent dispatch?
 │
 ├─ NO → Single-agent execution. STOP.
 │
 └─ YES
     │
     Q2: Are the subagents read-only (research, audit)?
     │
     ├─ YES → Dispatch WITHOUT isolation. No worktree needed. STOP.
     │
     └─ NO (agents will write code)
         │
         Q3: Can work be partitioned into groups with
             zero shared write targets?
         │
         ├─ NO → Single-agent execution. STOP.
         │
         └─ YES
             │
             Q4: Do groups span different domains?
             │
             ├─ NO → Likely coupled. Single-agent. STOP.
             │
             └─ YES
                 │
                 Q5: Any global state files in write set?
                 │
                 ├─ YES → Exclude them. Orchestrator writes
                 │        global state post-merge. Continue.
                 │
                 └─ NO → Continue.
                     │
                     Q6: Is git working tree clean?
                     │
                     ├─ NO → Commit or stash first. Then continue.
                     │
                     └─ YES
                         │
                         ✓ USE WORKTREE ISOLATION
```

---

## Result Aggregation

Each worktree agent returns to the orchestrator:

1. **Branch name** — if changes were made (auto-generated by Claude Code)
2. **Summary** — max 2000 tokens (per agent-workflow.md context hygiene)
3. **Changed files** — explicit list of files modified
4. **Verification result** — pass/fail with error details if failed

The orchestrator collects ALL results before proceeding to merge. Do not merge incrementally as agents finish — wait for all to complete.

---

## Merge Strategy

### Merge Order (least risk first)

1. Documentation-only changes
2. Test files
3. Backend code
4. Frontend code
5. Infrastructure/config

### Merge Protocol

1. The **orchestrating agent** performs all merges (not worktree agents).
2. For each worktree branch: `git merge --no-ff <branch>` into current working branch.
3. After each merge: run the **Verification Matrix** (AGENTS.md) for the changed domain.
4. If verification fails post-merge: compare with pre-merge verification result to isolate whether the merge caused the failure.
5. After all merges complete: run **full verification** across all changed domains (catches integration issues).

### Lock File Handling

If multiple agents added dependencies:
1. Merge the dependency declaration files (e.g., `pyproject.toml`, `package.json`)
2. Regenerate lock files: `pip-compile` / `npm install`
3. Verify the regenerated lock files

---

## Conflict Resolution

| Conflict Type | Resolution |
|---------------|------------|
| **Textual** — two agents added to the same file (e.g., `__init__.py` imports) | Orchestrator reads both branches, combines additions manually |
| **Semantic** — incompatible logic in shared dependency | **STOP.** Report to user. Pre-dispatch partitioning was wrong. |
| **Migration ordering** — two agents created migrations for same app | **NEVER** dispatch parallel worktrees for same Django app's migrations. This is a pre-dispatch checklist violation. |
| **Lock file** — conflicting dependency versions | Orchestrator regenerates lock file after merging all dependency declarations |

---

## Post-Merge Cleanup

1. Delete merged worktree branches: `git branch -d <worktree-branch>`
2. Prune stale worktree references: `git worktree prune`
3. If a worktree agent failed and left a branch:
   - Inspect the branch for partial useful work
   - Either merge partial work or discard: `git branch -D <failed-branch>`
4. Verify no stale worktrees remain: `git worktree list`

---

## Anti-Patterns

| Anti-Pattern | Why It Fails | Do Instead |
|--------------|-------------|------------|
| Worktree for model+serializer+view+test | These are a coupled chain — serializer depends on model, view depends on both | Single-agent for the full chain |
| More agents = faster | Coordination overhead exceeds parallelism benefit below ~5 files | Single-agent for small tasks |
| Skip pre-dispatch checklist for "obvious" cases | Hidden coupling surfaces at merge time | Always run the 5-question checklist |
| Worktree agents writing to `changes.log` or `docs/tasks.md` | Merge conflicts guaranteed on append-only files | Orchestrator writes global state |
| Merging as each agent finishes | Later merges may conflict with earlier ones; no full integration test | Wait for all, merge in priority order |
| Parallel migrations for the same Django app | Django migration graph requires linear ordering | Never parallelize same-app migrations |

---

## Concrete Examples

### Good: Backend + Frontend in parallel

```
Task: Implement product search (API + UI)

Agent 1 (worktree): Backend
  Write: backend/apps/products/views.py, serializers.py, services.py, tests/
  Verify: make lint-backend && make test-backend

Agent 2 (worktree): Frontend
  Write: frontend/src/app/products/search/, frontend/src/components/SearchBar/
  Verify: cd frontend && npm run lint

Orchestrator: merge backend first, then frontend, run full verification
```

### Good: Two independent Django apps

```
Task: Add analytics tracking + notification preferences

Agent 1 (worktree): backend/apps/analytics/
Agent 2 (worktree): backend/apps/notifications/

No shared models, no shared migrations → safe to parallelize
```

### Bad: Same-app coupled work

```
Task: Add product reviews feature

DON'T parallelize:
  - Agent 1: models.py + migrations
  - Agent 2: views.py + serializers.py + tests

WHY: views.py imports from models.py. Agent 2 can't work without Agent 1's output.
DO: Single-agent for the full feature chain.
```
