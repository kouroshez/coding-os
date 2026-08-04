<!-- domain:DOCS | layer:reference | ssot:true | updated:2026-01-01 -->
# Workflow Guide

Purpose: Quick-start guide for new contributors and AI agents joining the project.
Read when: First session in this repo, or when re-grounding after a long break.
Skip when: Already familiar with the workflow and have an active task.
Read next: `../governance/agent-workflow.md`, `../governance/task-lifecycle.md`

> Nav: [Docs Index](../00-index.md)

## TL;DR

> **How much of this applies to you?** coding-os is modular. This guide is
> rendered for the subsystem modules this project enabled at create time —
> `cos module list` shows the current set, `cos module enable|disable <id>`
> changes it. Disabling one takes its tools, commands, and hooks with it; the
> kernel's safety and task-hygiene gates stay on either way.

This project uses **coding-os** — a documentation-driven workflow with SSOT files,
a Scrumban task board, and AI-agent enforcement hooks. Work flows through tasks:
`icebox → in_progress → testing → complete` (plus `blocked` / `archive`). The `cos` CLI and slash
commands drive the board; hooks enforce the discipline.

## Daily Workflow

1. **Start the session**

    ```bash
    cos daily
    ```

    Shows yesterday's progress, today's candidate tasks, blockers, and WIP status.
    (Also available as a slash command — see the Commands section below.)

2. **Pick or create a task**

    ```bash
    cos task-pick                 # top recommended tasks to work on next
    cos board                     # full Scrumban board (add --web for the Hub UI)
    cos task-create --title "..." --swimlane <lane> --kind <type>
    ```

    Reconcile against existing tasks first — never create a duplicate. If a
    matching open task exists, use it.

3. **Start the task**

    ```bash
    cos task-start TASK-NNN
    ```

    Enforces the WIP cap, sets the `.task-current` session marker, and moves the
    task to `in_progress`.

4. **Classify (Thinking OS Complexity Gate)**

    Before writing code, classify the task and record the gate:

    - CLEAR (1 dim) → just do it
    - COMPLICATED (2-4 dims) → Zoom cycle, plan first
    - COMPLEX (5+ dims) → full Zoom + experiments
    - CHAOTIC → stabilize first, classify after

    ```bash
    bash .claude/hooks/write-state.sh .coding-os/claude/.thinking_os-gate "COMPLICATED 3"
    ```

    (Replace `.claude` / `claude` with your adapter dir — `.codex` / `codex` for
    Codex. Slash-command equivalent: `/classify COMPLICATED 3`.) A hook BLOCKS
    code writes until the gate is recorded.

5. **Implement**

    Follow the Core Loop in `AGENTS.md` (Classify → Orient → Plan → Execute →
    Verify). Hooks enforce skill loading, gate recording, doc anchors, and
    verification along the way.

6. **Verify and close**

    ```bash
    cos verify                    # matrix-targeted verification for changed files
    cos task-move TASK-NNN --to testing
    cos task-done TASK-NNN
    ```

    (Slash-command equivalent for verification: `/verify`.) Never close a task
    straight from `in_progress` — move to `testing`, run checks, then complete.

## Slash Commands

Type `/` in the agent to run a packaged workflow. Project commands live in
`.claude/commands/` (and `.codex/commands/`) and are version-controlled:

| Command | What it does |
|---|---|
| `/board` | Show the Scrumban board grouped by swimlane × status |
| `/daily` | Daily standup — yesterday, today's candidates, blockers, WIP |
| `/retro` | Retrospective for a period (default 14 days) |
| `/task TASK-NNN` | Load + summarize a task |
| `/classify Q1 Q2` | Record the Complexity Gate |
| `/verify` | Run matrix-targeted verification for changed files |
| `/review` | Review current changes against project standards |
| `/diagnose` | Run system health diagnostics (`cos doctor`) |
| `/memory-search <query>` | Search agent memory for cross-session context |
| `/role-<name>` | Invoke one of the 11 semantic roles (researcher, architect, …) |

## Key Files

- `AGENTS.md` — Routing protocol + Core Loop (read first every session)
- `docs/00-index.md` — Master navigation hub
- `docs/tasks/TASK-NNN-*.md` — Task detail files (the board's source of truth)
- `docs/governance/` — Workflow policies (`agent-workflow.md`, `task-lifecycle.md`, `critical-rules.md`)
- `docs/playbooks/` — Domain-specific routing maps (if installed)
- `docs/engineering/` — Coding standards (if installed)

## Commands Cheat Sheet

| Command | What it does |
|---|---|
| `cos daily` | Standup view — last 24h + today's candidates + blockers |
| `cos board [--web]` | Scrumban board (ASCII, or Hub UI) |
| `cos task-pick` | Next recommended task |
| `cos task-create --title "..." --swimlane <lane> --kind <type>` | Create a task |
| `cos task-start TASK-NNN` | Start a task (sets WIP + `.task-current`) |
| `cos task-move TASK-NNN --to <status>` | Move a task between statuses |
| `cos task-done TASK-NNN` | Complete a task |
| `cos task-show TASK-NNN` | Show a task's full content |
| `cos retro` | Weekly retrospective — throughput + cycle time |
| `cos verify` | Matrix-targeted verification for changed files |
| `cos doctor` | Deep health check (scaffold, DB, adapter, symlinks) |
| `cos health` | Fast health summary |

## Thinking OS — Memory and Learning

The `coding-os` MCP server provides tools for memory, learning, metrics, routing,
and graph queries. See `../governance/mcp-tool-inventory.md` for the full inventory.

Key flow: every tool use → captured to the DB. Every task done → outcome recorded.
Every 10 tasks → patterns extracted. Every session start → relevant past patterns
suggested.
