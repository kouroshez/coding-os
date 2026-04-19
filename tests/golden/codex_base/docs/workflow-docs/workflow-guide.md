<!-- domain:DOCS | layer:reference | ssot:true | updated:2026-01-01 -->
# Workflow Guide

Purpose: Quick-start guide for new contributors and AI agents joining the project.
Read when: First session in this repo, or when re-grounding after a long break.
Skip when: Already familiar with the workflow and have an active task.
Read next: `../governance/agent-workflow.md`, `../governance/task-lifecycle.md`

> Nav: [Docs Index](../00-index.md)

## TL;DR

This project uses **coding-os** — a documentation-driven workflow with SSOT files, structured tasks, and AI-agent enforcement hooks.

## Daily Workflow

1. **Start session**

    ```bash
    make session-init
    ```

    Shows current phase, recent changes, open task count.

2. **Pick a task**

    ```bash
    make task-next            # see next recommended task
    make task-list            # see all tasks
    make task-context TASK=003  # load full context for a task
    ```

3. **Start a task**

    ```bash
    make task-start TASK=003
    ```

    Creates the detail file (if missing), marks `[/]` in `docs/tasks.md`, and shows context.

4. **Classify (Thinking OS Complexity Gate)**

    Before writing code, classify the task:

    - CLEAR (1 dim) → just do it
    - COMPLICATED (2-4 dims) → Zoom cycle, plan first
    - COMPLEX (5+ dims) → full Zoom + experiments
    - CHAOTIC → stabilize first, classify after

    Record the classification:

    ```bash
    bash .coding-os/hooks/write-state.sh .coding-os/.thinking-os-gate "COMPLICATED 3"
    ```

5. **Implement**

    Follow the Core Loop in `AGENTS.md`. Hooks enforce skill loading, gate recording, and verification.

6. **Verify and close**

    ```bash
    make verify           # run domain verification
    make task-done TASK=003 TYPE=feat MSG="Add user auth" WHAT="Endpoints + tests" FILES="backend/auth.py backend/tests/test_auth.py"
    ```

## Key Files

- `AGENTS.md` — Routing protocol (read first every session)
- `docs/00-index.md` — Master navigation hub
- `docs/tasks.md` — Task index (status SSOT)
- `docs/foundation-map.md` — REF shortcodes for compact links
- `docs/governance/` — Workflow policies
- `docs/playbooks/` — Domain-specific routing maps (if installed)
- `docs/engineering/` — Coding standards (if installed)
- `changes.log` — Append-only change history

## Commands Cheat Sheet

| Command | What it does |
|---|---|
| `make session-init` | Project status snapshot |
| `make task-next` | Next recommended open task |
| `make task-start TASK=N` | Start a task |
| `make task-done TASK=N TYPE=t MSG="m" WHAT="w" FILES="f"` | Mark task done |
| `make task-block TASK=N REASON="r"` | Block a task |
| `make task-create NUM=N TITLE="[DOMAIN] desc"` | Create new task |
| `make task-context TASK=N` | Show task context |
| `make task-list [STATUS=open]` | List tasks |
| `make log-latest [N=5]` | Recent change log entries |
| `make log-search QUERY="auth"` | Search change log |
| `make verify` | Run domain verification |
| `make cos-health` | Check thinking-os DB health |

## Thinking OS — Memory and Learning

The MCP server (`coding-os` / `thinking-os`) provides 18 tools for memory, learning, metrics, routing, and graph queries. See `../governance/mcp-tool-inventory.md`.

Key flow: every tool use → captured to DB. Every task done → outcome recorded. Every 10 tasks → patterns extracted. Every session start → relevant past patterns suggested.
