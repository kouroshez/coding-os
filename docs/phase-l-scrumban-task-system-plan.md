<!-- domain:ALL | layer:reference | ssot:true | updated:2026-04-19 -->
# Phase L — Scrumban Task System (`cos-board`)

Purpose: Replace the current 12-section spec-style task files with an **agent-first Scrumban system** — Markdown as SSOT, SQLite as cache, WebGL board as visualization. Task files become lean *pointers* to docs (not re-specs of them), frontmatter carries workflow state (status / swimlane / priority / WIP), and a first-party web viewer renders a Silicon-Valley-style physical-whiteboard experience backed by real-time file-watching. The system is designed around solo-dev ergonomics (single person, multiple parallel projects, perfectionist tendencies, distractibility) while scaling cleanly to small teams.

Read when: Starting any `L.*` slice, designing a task template, adding a new board column or swimlane, wiring a workflow hook.

Read next: [core/thinking_os/task_parser.py](../core/thinking_os/task_parser.py), [core/thinking_os/task_sync.py](../core/thinking_os/task_sync.py), [templates/_base/task-detail.template.md](../templates/_base/task-detail.template.md), [docs/code-os-core-docs/scrumban/agile-scrum-guide.md](./code-os-core-docs/scrumban/agile-scrum-guide.md), [docs/phase-i-knowledge-graph-plan.md](./phase-i-knowledge-graph-plan.md) (graph edges produced_by_task / references_doc).

---

## 1. Why — The Problem Phase L Solves

### 1.1 Three concrete pains

1. **Token bloat.** Current task template has 12 sections (Goal, Read First, Source of Truth, Scope In/Out, Requirements, Dependencies, Open Questions, Rabbit Holes, Verification, Notes, ...). Every task re-states rules, conventions, and acceptance criteria that already live in `docs/**` and `core/rules/**`. A task file today is ~3,000–5,000 tokens; ~70% of that is duplicated content the agent already has in context. Over a session with three active tasks, this burns 10,000+ tokens on redundant spec.

2. **No workflow state.** The current system records only `open | wip | done | blocked` in `docs/tasks.md`. There is no **swimlane**, no **priority**, no **appetite**, no **WIP limit**, no **Work Log**, no **session-handoff trail**. Every session restart, the agent has to re-discover *where it was*.

3. **No visual agent.** As a solo perfectionist with multiple parallel projects (Zibaal, Moka, coding-os itself), the user needs the Silicon-Valley-S01E05 whiteboard experience — swimlanes, columns, WIP caps, emergency lane — in a form that is **(a)** agent-readable (primary consumer) **(b)** human-glanceable (secondary consumer, occasional editor).

### 1.2 Why the four existing systems don't replace tasks

A common and valid question: given `thinking-os` (memory), `cos_doc_search` (specs), `graph-os` (structure), do we still need tasks?

**Yes — they occupy a different axis of time and cognition:**

| System | Question answered | Time axis | Mutability |
|---|---|---|---|
| `docs/**` | What *should* the system be? | Timeless (spec) | Deliberate revisions |
| `graph-os` | What *is* connected to what right now? | Present | Continuously re-indexed |
| `thinking-os` memory | What *have* I tried before? | Past | Append-only observations |
| **tasks (Phase L)** | What *am I going to do next*? | **Future / work-in-flight** | **Active mutation per session** |

Without a task registry, the multi-session, multi-project, multi-agent handoff collapses. The task file is the **baton** between sessions. A solo developer with six parallel projects *cannot* operate without an externalized plan — that's literally what the `agile-scrum-guide.md` identifies as the solo-dev failure mode.

### 1.3 The revolutionary claim

No existing product — Linear, Jira, GitHub Projects, Shape Up tools, Notion, Trello, Miro, or the closed `TodoWrite` inside Claude Code — designs its task system **primarily for AI agents** with humans as secondary editors. Every existing tool treats agents as add-on API clients. Phase L inverts this: agents are the **default** consumer, humans the supplementary one. This is the unique positioning of coding-os and the reason Phase L matters for the >1M-star ambition.

---

## 2. Nature — What `cos-board` IS

```
core/
├── thinking-os/          ← cognition (unchanged)
├── graph-os/             ← structural graph (Phase I)
└── board-os/             ← NEW: Scrumban task system
    ├── parser.py         ← upgraded task_parser + frontmatter
    ├── sync.py           ← upgraded task_sync + DB v13
    ├── workflow.py       ← state machine + WIP enforcement
    ├── tools/            ← MCP tools (cos_task_board, _move, _pick, _daily, _retro, _wip)
    ├── viewer/           ← HTML + WebSocket Scrumban board
    ├── cli/              ← board subcommands (Click)
    └── migrations/       ← one-time migration from old 12-section format
```

- **SSOT = Markdown** at `docs/tasks/TASK-NNN-slug.md`. Git-versioned. Human-readable. Agent-editable.
- **Cache = SQLite** `tasks` table (extended via migration v13). MCP tools query the cache.
- **Viewer = HTML + WebSocket** at `cos board --web`. Real-time via file-watcher. Drag-drop writes back to MD frontmatter.
- **Workflow rules** live in `core/board-os/workflow.py` — the ONE place that knows valid state transitions + WIP caps. Hooks + CLI + MCP tools + web viewer all route through it.

Not a separate service; not a separate database; not a parallel SSOT. One store, three surfaces, one workflow engine.

---

## 3. Core Principles

- **P-L-1. MD is SSOT. DB is derived. Viewer is derived.** If SQLite and MD disagree, MD wins. `cos_task_sync` is idempotent — re-parsing a file produces identical rows.
- **P-L-2. Agent-first template.** Task files are ≤ ~1000 tokens of *pointers*, not re-specifications. Duplicated content = bug.
- **P-L-3. Workflow rules are code, not convention.** State machine in `workflow.py`; WIP caps in config; hooks enforce. No soft rules.
- **P-L-4. Solo-dev ergonomics by design.** WIP in_progress=1. Daily + Retro are first-class commands. Perfectionism defenses are hooks, not discipline.
- **P-L-5. Multi-session handoff via Work Log.** Every session appends one line; next agent reads last 5 lines to know "where I was". No memory hunt.
- **P-L-6. Multi-agent safe.** Two agents editing Work Log of same task is a real scenario (Claude + Codex). Concurrency model: append-only via file-locking.
- **P-L-7. Configurable swimlanes.** Per-project `.coding-os/scrumban-config.yaml`. `coding-os` itself has its own set; consumer Django+NextJS project has its own. No hardcoded values.
- **P-L-8. Zero-backend web viewer.** Board HTML + WebSocket = a single lightweight `cos board --serve` process. No Docker, no Vercel, no persistent daemon. Starts when you run it, dies when you close it.
- **P-L-9. Agent owns Work Log; human owns frontmatter.** Agent appends Work Log lines; the hook auto-captures on task transitions. Human (or agent via explicit `cos task-move`) transitions status. Frontmatter edits require hook validation.
- **P-L-10. Token efficiency is a first-class metric.** Every addition to the template or MCP tool response must justify its token cost. Rule 15 bans duplication.

---

## 4. Competitive Landscape

| System | Agent-first? | SSOT location | Visual board | WIP limits | Appetite/Cycle | Offline | Code-graph aware |
|---|---|---|---|---|---|---|---|
| **Linear** | No (API add-on) | Cloud DB | Yes | Configurable | Cycles | Requires sync | No |
| **Jira** | No | Cloud DB | Yes | Via extension | Sprints | No | No |
| **GitHub Projects** | Partial | GitHub | Yes | No | No | No | Repo-aware, no graph |
| **Notion** | No | Cloud DB | Configurable | Manual | No | No | No |
| **Trello** | No | Cloud DB | Simple | No | No | No | No |
| **Shape Up (Basecamp)** | No | Cloud | Yes | Implicit | **Appetite** | No | No |
| **Anthropic `TodoWrite`** | **Yes** | Session-scoped | No | No | No | N/A | No |
| **Miro / FigJam** | No | Cloud canvas | **Whiteboard** | Manual | No | No | No |
| **cos-board (Phase L)** | **Primary** | **Git MD** | **Physical-board feel** | **Enforced via hook** | **Appetite** | **100% local** | **Yes (graph-os)** |

**Concrete copies / inspirations:**

- **Silicon Valley S01E05 whiteboard** — column layout (ICE BOX → EMERGENCY → IN PROGRESS → TESTING → COMPLETE), swimlanes per domain, sticky-note colouring.
- **Linear** — cycle concept, keyboard-first UX, `cos task-pick` keyboard shortcut, command palette feel in the HTML viewer.
- **Shape Up (Basecamp)** — `appetite` field (not hour estimates). 6-week cycles vs. arbitrary sprints.
- **GitHub Projects** — frontmatter state, git-versioned workflow.
- **Claude's `TodoWrite`** — ephemeral task tracking that proves agents consume task data natively. Phase L persists it.

**Explicitly rejected patterns:**

- **Hours-based estimation.** Shape Up is right: agent and human both estimate badly in hours; appetite (how much am I willing to spend?) is the right question.
- **Cloud DB as SSOT.** We lose git diff, PR review, offline work, and auditability.
- **Mandatory sprints.** Solo dev with three projects can't parallel-sprint. Kanban flow + optional "this week" tagging.
- **Per-task assignment.** Solo → always you. In multi-agent mode, `agent_session` holder is the one currently editing.

---

## 5. Architecture — Three Surfaces, One SSOT

```
┌─────────────────────────────────────────────────────────────────┐
│                      Markdown SSOT (git)                         │
│                  docs/tasks/TASK-NNN-slug.md                     │
│     Frontmatter { status, swimlane, priority, ... } + Body       │
└───────────────┬──────────────────────────────┬──────────────────┘
                │                              │
       file-watcher (fsevents/              agent edits via
       inotify via watchdog)                Edit tool + hook
                │                              │
                ▼                              ▼
┌───────────────────────────────┐  ┌─────────────────────────────┐
│  task_sync.py (Phase C +      │  │  validate-task-frontmatter  │
│  Phase L extensions)          │  │  hook — rejects malformed    │
│  mtime-incremental → SQLite   │  │  state on Write/Edit         │
└───────────────┬───────────────┘  └─────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SQLite  (migration v13)                      │
│        tasks table (extended: status, swimlane, priority,        │
│        appetite, work_log_last_5, agent_session, ...)            │
└───────────┬─────────────────────────┬──────────────┬────────────┘
            │                         │              │
   MCP tools                   cos CLI commands     WebSocket server
   (cos_task_*)                (cos board, pick,    (cos board --serve)
            │                   daily, retro, ...)         │
            ▼                         ▼                    ▼
  agent reads board            user types cmd       HTML viewer
  via MCP envelope             in terminal           (drag-drop,
                                                     real-time)
```

**Two surfaces NEVER conflict:**
- Any surface (agent, CLI, web) that changes state calls `core/board-os/workflow.py::transition()`.
- `transition()` writes **only** to the MD frontmatter. Everything else re-syncs via the file-watcher → `task_sync.py`.
- Result: SSOT mutation is single-path. No race between DB and MD.

---

## 6. Data Model

### 6.1 Frontmatter schema (MD SSOT)

```yaml
---
# Identity
id: TASK-199                       # stable, zero-padded
title: "Implement Kuzu backend"    # ≤ 80 chars

# Four categorization axes (all independent)
swimlane: graph-os                 # DOMAIN — which subsystem/team; enum from scrumban-config.yaml
kind: feature                      # TYPE — what kind of work; enum: feature | bug | chore | spike | docs | refactor | test | security
epic: phase-l-scrumban             # INITIATIVE — optional; groups tasks across swimlanes (e.g. a phase, a release, a theme)
labels: [indexing, perf]           # FREE TAGS — arbitrary cross-cutting, no enum, no rendering impact

# Workflow state
status: in_progress                # enum: icebox | ready | emergency | in_progress | testing | complete | blocked | archive
priority: P1                       # enum: P0 | P1 | P2 | P3
appetite: "1d"                     # free-form time budget: "30m", "2h", "1d", "3d", "1w", "1cy"

# Time
created: 2026-04-19
started: 2026-04-20                # null until first transition into in_progress
completed: null                    # null until complete

# Session state
agent_session: ses-claude-20260420-abc   # most recent agent that touched; null when idle

# Relationships
depends_on: [TASK-180]             # hard block — can't start this until these complete
blocked_by: []                     # runtime block — external reason, filled by agent
references: [TASK-045, TASK-100]   # soft relationship
---
```

### 6.1.1 The four axes — clarified

Mixing "domain", "type", and "tags" into one field (the old `labels[0]=color` trick) is a bug magnet. Phase L separates them explicitly:

| Axis | Field | Constraint | Drives rendering? | Example |
|---|---|---|---|---|
| **Domain** (where/who) | `swimlane` | enum from config | Row placement + left-edge colour | `graph-os`, `backend`, `vpn-core` |
| **Type** (what kind) | `kind` | closed enum (8 values) | Card body colour | `feature`, `bug`, `chore`, `spike`, `docs`, `refactor`, `test`, `security` |
| **Initiative** (which theme) | `epic` | optional free string | Filter only (`cos board --epic X`) | `phase-l-scrumban`, `zibaal-mvp`, `oncall-q2` |
| **Tags** (free) | `labels` | free-form list | None | `indexing`, `perf`, `experimental` |

**Rules of thumb:**
- If a value belongs to one of the 8 known work-types → `kind`.
- If it belongs to a fixed set defined per-project → `swimlane`.
- If it's a time-bounded initiative grouping tasks across swimlanes → `epic`.
- Otherwise → `labels`.

**Why closed enum for `kind`?** Card colour stability. If `kind` were free-form, the same task type would get different colours in different projects (hash-based), breaking visual muscle memory. Closed enum + fixed palette = you always know a red card is a bug, in any repo you open.

**Schema validation** by `validate-task-frontmatter.sh` hook (PreToolUse on Write/Edit of `docs/tasks/*.md`):
- `status` ∈ enum
- `swimlane` exists in `scrumban-config.yaml::swimlanes`
- `kind` ∈ {feature, bug, chore, spike, docs, refactor, test, security}
- `priority` ∈ {P0, P1, P2, P3}
- `epic` matches `^[a-z0-9-]+$` if present; optional
- `labels` is a list of `^[a-z0-9-]+$` strings; no overlap with `kind` values (enforced — `kind` is the type)
- `depends_on` entries must be existing `TASK-###`
- `appetite` matches regex `^\d+[mhdwcy]$|^\d+cy$`
- `id` matches filename
- **Dependency cycle check (R-L-29):** DFS walk on the dependency graph including the proposed change; reject if any cycle is created. Error message shows the full cycle path: `TASK-A → TASK-B → TASK-C → TASK-A`. Cached per-session to avoid quadratic re-walk on rapid edits.

### 6.2 Body layout (minimal, pointer-based)

```markdown
# TASK-199: Implement Kuzu backend

**Outcome (one sentence):** SQLite fallback swappable with Kuzu via config; all 50 parity tests pass.

## Read First
- [docs/phase-i-knowledge-graph-plan.md#12](../phase-i-knowledge-graph-plan.md#12-storage-architecture) — backend architecture
- [core/graph-os/backend.py](../../core/graph-os/backend.py) — Protocol

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** `graph.backend: kuzu` in rag-config.yaml
- **When** agent calls `cos_graph_context("code:func:X")`
- **Then** result matches SQLite backend on 50 scenarios; P95 < 1s on 500k-symbol fixture

## Work Log
<!-- Agent appends ONE line per session. Never rewrites. -->
- 2026-04-20 [claude]: schema.kuzu loaded; insert_node done; 12/50 parity green
- 2026-04-21 [claude]: HNSW vector index wired; 35/50 green

## Rollback
Additive only. `.coding-os/graph-os.kuzu` isolated from SQLite state; revert commit.
```

**Required sections:** Outcome, Acceptance. Everything else optional.
**Forbidden:** duplicated rules, duplicated doc content, duplicated acceptance-criteria derivations. Rule 15 enforces (see §16).

**Definition of Done (DoD) mapping:** The "Acceptance (G/W/T)" section *is* the task's DoD — verbatim, not a separate concept. This is the agile-scrum-guide's anti-perfectionism rule: when the G/W/T passes, the task is Done. Not "perfect" — Done. Agent MUST NOT add extra scope beyond what G/W/T requires; if scope-creep is needed, create a follow-up task via `cos_task_create`.

### 6.3 DB migration v13

```sql
-- Extends the Phase C tasks table. Append-only (Rule 10).
ALTER TABLE tasks ADD COLUMN swimlane TEXT;                 -- domain
ALTER TABLE tasks ADD COLUMN kind TEXT;                     -- work type enum
ALTER TABLE tasks ADD COLUMN epic TEXT;                     -- initiative grouping (nullable)
ALTER TABLE tasks ADD COLUMN labels_json TEXT DEFAULT '[]'; -- free tags
ALTER TABLE tasks ADD COLUMN priority TEXT;
ALTER TABLE tasks ADD COLUMN appetite TEXT;
ALTER TABLE tasks ADD COLUMN started_at INTEGER;
ALTER TABLE tasks ADD COLUMN completed_at INTEGER;
ALTER TABLE tasks ADD COLUMN agent_session TEXT;
ALTER TABLE tasks ADD COLUMN work_log_last_5 TEXT DEFAULT '[]';  -- JSON array of last-5 lines

-- New status enum mapping (existing 4 statuses still supported as aliases)
CREATE TABLE task_status_history (
  id            INTEGER PRIMARY KEY,
  task_id       TEXT NOT NULL,
  old_status    TEXT NOT NULL,
  new_status    TEXT NOT NULL,
  agent_session TEXT,
  reason        TEXT,
  transitioned_at INTEGER NOT NULL,
  FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);
CREATE INDEX idx_tsh_task ON task_status_history(task_id, transitioned_at);

-- Swimlane + priority indices for board queries
CREATE INDEX idx_tasks_swimlane_status ON tasks(swimlane, status);
CREATE INDEX idx_tasks_kind_status ON tasks(kind, status);
CREATE INDEX idx_tasks_epic ON tasks(epic) WHERE epic IS NOT NULL;
CREATE INDEX idx_tasks_priority_status ON tasks(priority, status) WHERE status IN ('ready', 'in_progress', 'emergency');
```

### 6.4 Status enum (8 values + legacy mapping)

| New status | Legacy from Phase C | Meaning | Valid transitions FROM |
|---|---|---|---|
| `icebox` | (none) | Backlog; unscheduled | → ready, archive |
| `ready` | `open` | Up-next; dependencies resolved | → in_progress, icebox, emergency |
| `emergency` | (none) | Urgent; skip queue | → in_progress, icebox |
| `in_progress` | `wip` | Active work | → testing, blocked, ready, emergency |
| `testing` | (none) | Implementation done, verifying | → complete, in_progress (failed), blocked |
| `complete` | `done` | Acceptance criteria met | → archive (auto after 30d) |
| `blocked` | `blocked` | External dependency | → in_progress, emergency, icebox |
| `archive` | (none) | Frozen; read-only | (terminal) |

Legacy status strings in existing `docs/tasks.md` index file are **silently upgraded** on first parse. The index file itself is retired in L.6 — status lives in frontmatter.

---

### 6.5 Priority vs. Emergency — Two Independent Axes

A common confusion worth pre-empting:

| Concept | What it is | Example |
|---|---|---|
| **`priority: P0–P3`** | Static ranking; how important is this task overall? | A P0 architectural debt task sits in `icebox` with P0 priority — important but not urgent |
| **`status: emergency`** | Dynamic workflow column; what needs attention *right now*? | A P2 bug becomes emergency when production breaks; still P2 priority but top of board |

`cos_task_pick` sorts `emergency` column first, then within `ready` uses `priority`. An emergency P3 beats a ready P0 for "what to do now". Perfectionism defense: keeping these separate prevents priority inflation (not everything can be P0).

---

## 7. Workflow Engine — `core/board-os/workflow.py`

One module, one SSOT for transition rules + WIP caps + validation.

```python
# Pseudocode signature
def transition(
    task_id: str,
    to_status: Literal["icebox","ready","emergency","in_progress","testing","complete","blocked","archive"],
    reason: str | None = None,
    agent_session: str | None = None,
    bypass_wip: bool = False,
) -> TransitionResult:
    """
    PURPOSE:      Central state machine for all Scrumban transitions.
    INPUT:        task_id, target status, optional reason + session.
    OUTPUT:       TransitionResult{ok, previous_status, new_status, warnings, wip_state}
                  or error envelope {category: validation|permission|unavailable, ...}
    DEPENDENCIES: board-os/parser, board-os/sync, task_status_history table.
    NOTES:
      - Rejects invalid transitions (raises TransitionError with suggested paths).
      - Checks WIP cap BEFORE mutation; bypass_wip=True requires --force on CLI.
      - Writes frontmatter via atomic rename (temp file + rename).
      - Appends to task_status_history.
      - Fires hooks: pre-transition + post-transition.
      - File-watcher will pick up the MD change and re-sync DB (self-healing).
    """
```

Single callers:
- CLI `cos task-move TASK=N TO=testing`
- MCP `cos_task_move(id, to, reason)`
- Web viewer drag-drop → WebSocket command → same function
- Hook `enforce-wip-limit.sh` calls in dry-run mode (`validate_only=True`) to pre-check

**WIP cap source of truth:** `.coding-os/scrumban-config.yaml::wip_limits`. Defaults:
```yaml
wip_limits:
  in_progress: 1      # perfectionism defense
  testing: 3
  emergency: 2        # if >2, you're on fire — alert
```

**Override mechanism:** `COS_WIP_OVERRIDE=1` env var (for exceptional CI runs only; fires a `cos_metric_record("wip.override.count")` so drift is observable).

---

## 8. MCP Tool Surface — Eight New Tools (`cos_task_*`)

All follow Rule 14 envelope. Existing four (`cos_task_search`, `_dependencies`, `_dependents`, `_by_filter`) remain — Phase L adds eight.

### 8.1 `cos_task_create(title, swimlane, kind, priority='P2', appetite='1d', epic?, labels=[], parent_task?, outcome?, read_first=[], status='icebox')`

- Creates a new `docs/tasks/TASK-NNN-slug.md` file from the lean template + writes frontmatter + inserts into DB cache.
- Auto-assigns next `TASK-NNN` id (monotonic; reads existing max).
- Validates `swimlane` against `scrumban-config.yaml` and `kind` against the 8-value enum.
- If `parent_task` given, adds `references: [parent]` to frontmatter.
- If `epic` not given and `parent_task` has an `epic`, inherits parent's epic (by default; opt-out via `inherit_epic=False`).
- Returns `{task_id, file_path, url_in_board}`.
- **When to use:** agent exploring code finds a bug or debt → creates task immediately without interrupting flow; `cos task-create` CLI wraps this; F7 debug flow auto-creates bug tasks with `kind=bug`.
- **Token budget:** ~300 (tiny — just confirmation).

### 8.2 `cos_task_board(swimlane?, kind?, epic?, status_filter?, include_archive=False, limit=50)`

- Returns board state: tasks grouped by `(swimlane, status)` with counts and WIP violations.
- Filters: by `swimlane` (domain), by `kind` (type — e.g. "show me only bugs"), by `epic` (e.g. "only phase-l tasks").
- Default: only `icebox / ready / emergency / in_progress / testing / blocked` (complete paginated separately).
- Returns card-sized payload per task: `{id, title, kind, priority, epic, labels, appetite, agent_session, last_log_line}`.
- **Token budget:** ~2.5k default / 8k cap. For large boards, returns `meta.cursor` for pagination.
- **When to use:** Agent starting a session: "what's the state of work?". UI load. `cos daily` summary. `cos_task_board(epic="phase-l")` → only phase-L tasks.

### 8.3 `cos_task_move(id, to, reason?, bypass_wip=False)`

- Calls `workflow.transition()`. Returns `{ok, previous_status, new_status, warnings[]}` or validation error with suggested paths.
- **When to use:** Agent explicitly changes state. After completing tests: `cos_task_move("TASK-199", "complete")`.

### 8.4 `cos_task_pick(swimlane?, priority_min='P2', max_candidates=5)`

- "What should I work on now?" — ranks `ready | emergency` tasks by:
  1. `priority` (P0 > P1 > P2 > P3)
  2. `depends_on` all complete
  3. Related to the current active session's recent `cos_search` observations (boost)
  4. Appetite fits remaining session budget (optional `session_remaining_min` param)
- Returns top N candidates, not just one — agent picks.
- **When to use:** Start of a work session; `cos daily` morning check-in.

### 8.5 `cos_task_daily(since='24h', agent_session?)`

- Produces the standup summary (auto-generated from status-history + work_log):

```json
{
  "yesterday": [{"task_id", "transitions", "log_lines"}],
  "today_candidates": [...],                 // from cos_task_pick
  "blockers":  [{"task_id", "since", "reason"}],
  "wip_state": {"in_progress": 1, "cap": 1, "violation": false},
  "suggested_focus": "TASK-199"
}
```

- **When to use:** Morning session start. CLI `cos daily` wraps this. Hook `remind-daily.sh` fires if no daily in >24h.

### 8.6 `cos_task_retro(since='7d')`

- Weekly retrospective:

```json
{
  "completed":    [...],
  "cycle_time_avg_hours": 9.3,
  "emergency_count": 2,                       // "fire frequency"
  "blocked_time_avg_hours": 4.1,              // how long tasks sat blocked
  "swimlane_throughput": {"graph-os": 4, "thinking-os": 2, ...},
  "impediment_themes": [...],                 // from blocked reasons (NLP-lite)
  "one_improvement": "..."                    // agent suggests one focus for next week
}
```

- **When to use:** Friday `cos retro` or on-demand. Can optionally persist to `docs/retros/YYYY-MM-DD.md`.

### 8.7 `cos_task_wip_check()`

- Light health ping: "am I exceeding WIP right now?"
- Returns per-column current vs. cap. Called by `enforce-wip-limit.sh` in dry-run.
- **Token budget:** ~200 (tiny).

### 8.8 `cos_work_log_append(task_id, summary, agent_session?, source='manual'|'auto')`

- Append-only Work Log entry without going through the file-Edit + hook path.
- Critical for Codex sessions where PostToolUse `capture-work-log.sh` is not delivered (R-L-26).
- Takes the same `flock` lock as the hook → multi-agent safe.
- Truncates `summary` to 120 chars; auto-prefixes `YYYY-MM-DD [agent | session-suffix]:`.
- `source='auto'` flagged for entries from the polling fallback (`cos_work_log_append --auto-from-git-diff` at session-end summarizes `git diff --stat` since session-start).
- Returns `{ok, task_id, line_appended, total_lines}`.
- **When to use:** Codex agent at end of any meaningful edit; Claude only as backup if PostToolUse failed; CLI `cos task-log-add` wraps this.
- **Token budget:** ~150 (tiny — confirmation only).

### Token budgets table

| Tool | Default | Cap |
|---|---|---|
| `_create` | ~300 | 1k |
| `_board` | ~2.5k | 8k |
| `_move` | ~300 | 1k |
| `_pick` | ~1.2k | 3k |
| `_daily` | ~1.5k | 4k |
| `_retro` | ~2k | 6k |
| `_wip_check` | ~200 | 500 |
| `_work_log_append` | ~150 | 500 |

---

## 9. CLI Surface

```bash
# Board views
cos board                           # ASCII Scrumban in terminal
cos board --web [--port 9000] [--autocommit]  # start WebSocket server + open browser
cos board --swimlane graph-os       # filter by domain (single lane)
cos board --kind bug                # filter by type ("show only bugs")
cos board --epic phase-l            # filter by initiative
cos board --priority P0,P1          # filter by priority
cos board --group my-platform       # cross-repo group board (uses graph-group from Phase I)

# Workflow
cos task-create SWIMLANE=graph-os KIND=feature TITLE="..." APPETITE=1d PRIORITY=P1 [EPIC=phase-l] [LABELS=indexing,perf]
cos task-move TASK=199 TO=testing [REASON="..."] [--force]
cos task-start TASK=199             # shortcut for TO=in_progress + WIP check
cos task-done TASK=199              # shortcut for TO=complete
cos task-block TASK=199 REASON="..." # shortcut for TO=blocked
cos task-cancel TASK=199 REASON="..." # shortcut for TO=icebox + labels+=[cancelled]
cos task-pick                       # prints top 3 candidates
cos task-archive --older-than 30d   # bulk archive complete tasks

# Workflow rituals
cos daily                           # morning standup (prints cos_task_daily output)
cos retro                           # Friday retro (prints + optionally persist)

# Introspection
cos task-show TASK=199              # full task content + status history
cos task-log TASK=199 [--full]      # just Work Log (default last 5, --full = all)
cos task-history TASK=199           # status-history entries
cos wip                             # current WIP state (wraps cos_task_wip_check)

# Admin
cos task-migrate [--dry-run]        # one-time: old 12-section → new frontmatter+lean
cos task-validate                   # lint all task files: frontmatter schema, broken links
cos board-config --init             # generate .coding-os/scrumban-config.yaml
```

---

## 10. Hooks — Five New

All registered in `core/hooks/registry.yaml`; generated adapter templates follow (Rule 11).

| Hook | Event | Purpose | Blocking? |
|---|---|---|---|
| `validate-task-frontmatter.sh` | PreToolUse: Write/Edit on `docs/tasks/*.md` | Reject malformed frontmatter (schema, enums, FK to swimlanes/task-refs) | Yes |
| `enforce-wip-limit.sh` | PreToolUse: before transition to `in_progress` or `emergency` | Block if WIP cap exceeded; allow with `COS_WIP_OVERRIDE=1` | Yes |
| `capture-work-log.sh` | PostToolUse: after significant Edit/Write on code when `.task-current` is set | Append one-line entry to active task's Work Log, agent-prefixed | No (fire-and-forget) |
| `remind-daily.sh` | SessionStart | If last `cos daily` > 24h ago, print banner reminder | No (warning) |
| `auto-task-sync.sh` | PostToolUse: Write/Edit on `docs/tasks/*.md` | Re-sync single file to DB cache (mtime-incremental) | No |

**Concurrency model for `capture-work-log.sh`:**
- Uses `flock(2)` on `.coding-os/<agent>/.task-log.lock` to serialize appends.
- Timeout 2s; on failure, logs to `.coding-os/.task-log-contention.log` and skips (fail-soft).
- Line format: `- YYYY-MM-DD [agent-id | ses-NNNN]: <summary>` where `<summary>` is truncated to **120 chars** (hard); the session-id suffix (truncated to 8 chars) helps trace which specific session did the work.
- **Per-line truncation + per-task cap:** a single line exceeding 120 chars is hard-truncated with `…`. The "last 5 lines" shown in MCP context = **max ~600 chars ≈ 150 tokens**, predictable regardless of how verbose a specific session was. Full history still in the MD file.

---

## 11. Web Scrumban Viewer

> **Distinction from Phase I viewer:** The graph-os viewer (Sigma.js + WebGL force-directed) and the board-os viewer (Sortable.js + Kanban layout) are **two separate HTML files** with two separate CLIs: `cos graph-viz` vs `cos board --web`. They share no code and no port. A future slice (Phase M?) may unify them behind one `cos viz` hub, but for Phase L they stay independent — different mental models, different dependencies, different WebSocket servers.

### 11.1 Stack

- **HTML + vanilla JS** — no build pipeline, single self-contained file produced by `cos board --web`.
- **Sortable.js** (pinned CDN + SRI hash) — proven, 30KB, handles drag-drop across columns and swimlanes.
- **HTMX or a minimal custom WebSocket client** — keep JS footprint small; real-time updates via server-push.
- **aiohttp** — Python WebSocket + HTTP server (`cos board --serve`). Binds to `127.0.0.1:9000` by default.
- Offline: `--bundled` inlines Sortable.js into the HTML, no CDN required.

### 11.2 Backend (`cos board --serve`)

- aiohttp app with:
  - `GET /` → static HTML shell
  - `GET /api/board` → wraps `cos_task_board()` MCP tool output
  - `WS /ws` → bidirectional: server pushes change events, client sends drag-drop commands
- File-watcher (`watchdog` library) on `docs/tasks/` → emits `board-changed` event on the WebSocket.
- Drag-drop command: `{type: "move", task_id, to_status, to_swimlane}` → calls `workflow.transition()` → writes MD → file-watcher picks up → broadcasts to all connected clients.

### 11.3 Security

- **127.0.0.1 only** by default. `--bind 0.0.0.0` requires `--auth-token` which writes a random token to `.coding-os/.board-token` (600 perms).
- Every WebSocket message validated against a JSON schema before reaching `workflow.transition()`.
- CSP header forbids inline scripts except nonce-signed ones; no remote resource fetches.
- Rate limit: 10 mutations / second per connection.
- No auto-commit — drag-drop updates MD, user/agent commits explicitly.

### 11.4 UI features

- Columns + swimlanes exactly as §8.
- **Card body colour by `kind`** — fixed palette; never free-form:
  - `bug`=🔴 red, `feature`=🟡 yellow, `chore`=🟢 green, `spike`=🔵 blue, `docs`=🟣 purple, `refactor`=🟦 teal, `test`=🟧 amber, `security`=🟠 orange
- **Left-edge band colour by `swimlane`** — from `scrumban-config.yaml::swimlanes[].color`.
- **Priority border:** P0 red solid double, P1 orange solid, P2 gray dashed, P3 dim dotted.
- **Epic badge:** if `epic` set, small pill at top-right of card (e.g. `phase-l`).
- **Labels:** rendered as tiny gray chips below the title; click-to-filter; no colour.
- WIP violation: column header flashes red; `cos_task_move` rejections show toast.
- Keyboard: `/` focuses search; `j/k` navigates cards; `enter` opens task; `m` opens move menu.
- Accessibility: full keyboard nav; ARIA roles; screen-reader list view as fallback.
- **RTL / bidi support:** The viewer detects task titles containing RTL scripts (Persian, Arabic, Hebrew) per-card and sets `dir="auto"` on each card's text node. Board layout itself stays LTR (Scrumban convention — ICE BOX is leftmost), but individual cards with Persian/Arabic titles render right-aligned with Persian digits preserved. Tested against fixture set of mixed Persian/English task titles.

### 11.5 Rendering budget

- Max 500 cards in view (rest paginated) — solo dev won't have more; teams filter by swimlane.
- Incremental rendering (only changed cards re-render via surgical DOM updates).
- First paint < 200ms on 200-task board.

---

## 12. Integration with `thinking-os`

- `cos_search` boosts observations linked to the currently active `task-current`.
- `cos_learn_suggest` called at `task-start` — returns past patterns relevant to the task's Read First docs.
- DB migration v13 appends to the same SQLite file that hosts memory / docs / graph. Single source-of-truth file.
- `cos_health` reports WIP state + stale Daily + unmatched blockers.

---

## 13. Integration with `graph-os` (Phase I)

- `task:file` nodes from graph-os §5.1 gain richer metadata: status + swimlane + priority from DB cache.
- New edge types on task nodes: `produced_by_task` (code → task), `references_doc` (task → doc), `depends_on` (task → task).
- `cos_graph_impact(uid=<doc>)` includes "tasks currently referencing this doc" — agent sees which tasks' Read First will break if the doc is restructured.
- Web viewer can optionally show a sidecar panel: "this card's graph context" (calls, refs) via `cos_graph_context(<task_uid>)`.
- `enforce-graph-context.sh` hook (from Phase I.14) and Phase L `capture-work-log.sh` are ordered: graph-context first (PreToolUse), work-log after (PostToolUse).

---

## 14. Integration with Formulas (11-formula framework)

| Formula | Step / Section | Phase L contribution |
|---|---|---|
| **F2 — Analysis** | Step 12 (Leaf decomposition) | Leaves become task files with `appetite ≤ "1d"`; parent tracked via `references` |
| **F3 — Architecture** | Step 6 (ADRs) | Any new task with label `architecture` auto-linked to `docs/adr/` |
| **F5 — Implementation** | Step 1 (Pre-Implementation) | `cos task-start` enforces Rule 0 doc-anchor + writes task_current + loads Read First |
| **F6 — Testing/Review** | Section A | Acceptance G/W/T in task file is the test-case source; `cos task-move TO=testing` is the gate |
| **F7 — Debugging** | Step 1 (Reproduce) | Bug tasks auto-created in `emergency` column with label `bug` + P0 |
| **F11 — Refactoring** | Step 1 (Debt identification) | `cos_graph_similar` + `_impact` output → chore tasks in `icebox`; prioritization via Retro |

---

## 15. Token Efficiency — Rule 15 (new)

### 15.1 The rule

> **Rule 15 — Task files are pointers, not specs.**
>
> A task file MUST NOT inline content already present in `docs/**`, `core/rules/**`, `AGENTS.md`, or `CLAUDE.md`. The "Read First" section lists *paths*; the body describes *delta* (outcome + acceptance + work log). Duplicated content is a bug: fix by (a) replacing with a link, (b) promoting to a real doc if no doc exists yet, or (c) removing the duplication if it was noise.
>
> **Why:** Agent context startup today is ~18k tokens across CLAUDE.md + active task + its re-spec. Rule 15 targets ~11k (~40% savings). Over a 10-turn session, this compounds to 70k tokens saved.
>
> **How to apply:** Before writing any prose in a task body, ask: "is this already in a doc?" If yes, link. If no, ask: "should this be in a doc?" If yes, write the doc and link. If it's truly task-local (acceptance, work log, rollback), write it in the task.

### 15.2 Enforcement

- `lint-task.sh` hook (PostToolUse on Write): flags task files > 1500 tokens with a warning; > 3000 tokens blocks.
- `cos task-validate` CLI: reports duplication (fuzzy-match task body lines against doc chunks via `cos_doc_search`) in dry-run.
- CLAUDE.md "Task Editing" section documents Rule 15 for agents.

---

## 16. Migration Strategy — Zero Existing Files

Audit (2026-04-19): `docs/tasks/` contains **0 files** in this repo. Migration burden: near-zero.

For consumer projects that adopted coding-os earlier and have old 12-section tasks:

### 16.1 `cos task-migrate --dry-run`

- Walks `docs/tasks/*.md`. For each file:
  - Extracts H1 → `id`, `title`
  - Infers `status` from `docs/tasks.md` index
  - Infers `swimlane` from filename prefix or H1 `[DOMAIN]` tag
  - Maps legacy sections → new layout:
    - "Goal" → `Outcome` (first sentence only; rest discarded with warning)
    - "Read First" / "Source of Truth" → new `Read First` (deduplicated)
    - "Acceptance Criteria" → `Acceptance (G/W/T)`
    - "Notes" + "Open Questions" + "Rabbit Holes" → archived to `docs/tasks/archive/pre-l/<id>.md` (preserved verbatim for reference)
  - Writes to temp file. Dry-run stops here.

### 16.2 `cos task-migrate --apply` — Two-Phase Atomic (R-L-27)

- **Phase 0 — Backup:** create `.coding-os/migration-backup-YYYY-MM-DD-HHMMSS.tar.gz` containing every `docs/tasks/*.md` BEFORE any change. Always runs first.
- **Phase 1 — Validate:** parse all N source files into a temp directory `.coding-os/migration-staging/`. If ANY file fails (parse error, broken frontmatter inference, swimlane mapping miss) → abort with clear report (`failed: 3/50, see migration-staging/.errors.log`). Zero writes to real paths.
- **Phase 2 — Apply (atomic):** only after Phase 1 fully succeeds, atomic rename per file from staging → final path; archives originals to `docs/tasks/archive/pre-l/`. If a single rename fails (extremely rare — disk full, permissions), rollback all renames and restore from backup tarball; no half-migrated state.
- **Phase 3 — Commit:** generates git commit `"Phase L migration: N tasks migrated; originals in archive/pre-l/"`. User reviews and either keeps or reverts.
- **Idempotent:** re-running on already-migrated files is a no-op (frontmatter detected → skip).
- **Resumable:** `cos task-migrate --resume` continues from a partially-validated staging dir if user interrupted mid-Phase-1.

### 16.3 Retiring `docs/tasks.md` index

- Index file becomes *generated*, not hand-edited. Regenerated on every `cos task-sync` or frontmatter change.
- Legacy files that still hand-edit the index keep working — migration makes frontmatter authoritative, and the generator respects any additional freeform text between markers.

---

## 17. Multi-Agent Concurrency

### 17.1 Conflict scenarios

1. **Two agents append Work Log simultaneously.** → `flock` in `capture-work-log.sh` serializes; 2s timeout; both entries preserved.
2. **Two agents transition same task.** → `workflow.transition()` reads current `status` from MD frontmatter just before write (optimistic concurrency); if status differs from `expected_from` arg → returns `fail("transient", retryable=True)` with current state in payload; loser retries with refreshed state. Belt-and-suspenders: `task_status_history` has a unique partial index on `(task_id, transitioned_at)` rounded to 100ms windows so simultaneous identical transitions can't both insert.
3. **Human drags in web UI while agent transitions via MCP.** → `workflow.transition()` reads current status fresh; web UI refetches on rejection; eventual consistency within one refresh cycle.
4. **File-watcher misses a change due to editor atomic-save patterns.** → `cos task-validate` catches drift at session start; `task_sync.py` full re-scan on demand.
5. **Agent writes frontmatter wrong (YAML syntax error).** → `validate-task-frontmatter.sh` rejects PreToolUse; clear error to agent; file never committed in broken state.

### 17.2 File-lock protocol

- Locks live under `.coding-os/<agent>/locks/TASK-NNN.lock`.
- Acquired for 2s max during Work Log append or frontmatter write.
- Released explicitly; automatic on process exit.
- `cos task-locks` CLI command lists active locks (debugging).

---

## 18. Observability

### 18.1 Metrics (via `cos_metric_record`)

- `board.wip.in_progress`, `board.wip.testing`, `board.wip.emergency`
- `board.wip.violations.count` (cumulative)
- `board.transition.count` tagged by `from_status`, `to_status`
- `board.cycle_time.minutes` per completed task
- `board.emergency.count` (fire frequency)
- `board.daily.streak_days` (gamification-adjacent, used for observability not shame)
- `board.work_log.append.count`
- `board.ws.connections` (web viewer active)

### 18.2 Logs

- `.coding-os/.board.log` — transitions, WIP rejects, daily/retro runs
- `.coding-os/.task-log-contention.log` — lock timeouts
- `.coding-os/.board-ws.log` — WebSocket server

### 18.3 Doctor checks (added to `cos doctor`)

- **C20** — WIP state is within cap (or flagged warning if active violation).
- **C21** — No stale `in_progress` tasks. Stale = (no Work Log append in > 3 days) **OR** (elapsed > 2× `appetite`). A task with `appetite: 6w` legitimately on day 30 with weekly Work Log entries does NOT trigger; one with `appetite: 1d` and 3 days of silence does (R-L-30).
- **C22** — Frontmatter schema valid on every `docs/tasks/*.md`.
- **C23** — `docs/tasks.md` index in sync with frontmatter (derived file up to date).

---

## 19. Roadmap — Ten Slices

Target: ship usable board after L.3 (CLI + MCP), web viewer after L.5, full polish by L.9.

| Slice | Scope | LOC | Ship gate | Dependencies |
|---|---|---|---|---|
| **L.0** | Migration v13 + `scrumban-config.yaml` schema + validator + docs for config + **lean task template files** (`templates/_base/task-detail.template.md` + `templates/_base/scaffold/docs/governance/templates/task-detail.md` rewritten with frontmatter + Outcome + Read First + Acceptance + Work Log + Rollback) + **default `scrumban-config.yaml` per stack** in `templates/_base/scaffold/.coding-os/` (per-stack overrides in `templates/<stack>/scaffold/.coding-os/scrumban-config.yaml`: django=backend/frontend/ai-service; nextjs=frontend/api/e2e; coding-os=8-lane set) + manifest-regen for both new files | ~500 | migration round-trip + 30 config fixtures + `cos init` produces correct per-stack config + lean template renders in golden test + `make manifest-regen` clean | — |
| **L.1** | `core/board-os/parser.py` upgrade — frontmatter parsing, schema validation, legacy fallback. `sync.py` upgrade — new columns, status-history writes | ~550 | 40 unit tests; legacy + new templates both parse; zero-file repo still syncs | L.0 |
| **L.2** | `core/board-os/workflow.py` — state machine + WIP engine + transition hook registry | ~500 | 60 transition tests covering all enum×enum × WIP states; property-based test on transition idempotence | L.1 |
| **L.3** | 6 MCP tools (`_board`, `_move`, `_pick`, `_daily`, `_retro`, `_wip_check`) | ~700 | envelope compliance (Rule 14); token-budget tests; dogfood: agent can run full day with no CLI | L.2 |
| **L.4** | Hooks: `validate-task-frontmatter`, `enforce-wip-limit`, `capture-work-log`, `remind-daily`, `auto-task-sync`. `registry.yaml` entries + generated adapter templates | ~400 | hook unit tests + integration test (file-locking under simulated contention) | L.2 |
| **L.5** | Web viewer: aiohttp server + Sortable.js HTML + WebSocket + file-watcher (`watchdog`). `--bundled` offline mode. Auth token path | ~900 | renders 200-task fixture at 60 FPS drag; WebSocket survives 1000 rapid moves; security: CSP, SRI, 127.0.0.1 default | L.3 |
| **L.6** | CLI commands (`board`, `task-move`, `task-start`, `task-done`, `task-block`, `task-pick`, `daily`, `retro`, `task-archive`, `task-log`, `task-show`, `task-history`, `wip`, `task-validate`, `board-config`, `task-migrate`) via Click | ~600 | 30 CLI integration tests; Windows CI + POSIX CI both green | L.3 |
| **L.7** | Migration tooling: `cos task-migrate --dry-run/--apply/--resume` (two-phase atomic per §16.2) + archive/pre-l/ + rollback test on 50-task fixture + intentionally-broken-file fixture (Phase-1 abort test) + dependency cycle detection in validator | ~550 | round-trip test: 50 legacy tasks migrated → valid frontmatter → agent can query via `cos_task_board`; abort test: 1 broken file aborts whole migration cleanly; cycle test: A→B→A rejected with clear path | L.1, L.6 |
| **L.8** | Integration: `graph-os` task-node enrichment (produced_by_task, references_doc edges); `thinking-os` `cos_learn_suggest` on task-start; formula-mapping docs | ~300 + docs | 3 cross-subsystem tests (agent starts task → learn_suggest called → graph edges written) | L.2, Phase I |
| **L.9** | Rule 15 + `lint-task.sh` hook + **AGENTS.md fragment `templates/_base/fragments/task-authoring.md.tmpl`** (composed into both AGENTS.md and CLAUDE.md via `base.yaml::agents_md_sections`) + skill `core/skills/task-driver/SKILL.md` + `cos doctor` C20–C23 | ~200 code + docs | docs lint + lint-task fires on dogfood edits + agent successfully runs complete task lifecycle per fragment guidance + skill auto-invokes when agent edits `docs/tasks/*.md` | L.3, L.5, L.6 |

**Total:** ~4,850 LOC + ~120 new tests (target ~1,320 tests passing post-Phase L; currently 1,083).

### Parallelization

- L.0 ships first.
- L.1 → L.2 sequential (workflow depends on parser).
- L.3 + L.4 parallel after L.2.
- L.5 parallel with L.6 after L.3.
- L.7 waits on L.6.
- L.8 requires Phase I shipped (graph-os).
- L.9 finalizes.

### Minimum viable ship point

After **L.3 + L.4 + L.6**: a solo dev has a working Scrumban loop via CLI + MCP, with hooks enforcing WIP and capturing work log. Web viewer (L.5) is ergonomic bonus.

---

## 20. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **R-L-1: Frontmatter corruption by agent** | Parser breaks; DB stale | `validate-task-frontmatter.sh` PreToolUse rejects; on parse error, `parser.py` falls back to section-mode (current behavior) + flags task as `parse_error=true` |
| **R-L-2: SSOT drift (DB vs. MD)** | Agent sees stale state; wrong decisions | `auto-task-sync.sh` hook on every MD write; `cos doctor` C23; full re-scan on `cos task-validate` |
| **R-L-3: Race: two agents edit Work Log** | Lost entries or interleaved lines | `flock` serialization in `capture-work-log.sh`; fail-soft with contention log |
| **R-L-4: WIP bypass via raw MD edit** | User/agent sidesteps state machine | `validate-task-frontmatter.sh` also runs `enforce-wip-limit.sh` when status transitions to `in_progress`/`emergency` |
| **R-L-5: Web viewer RCE via WebSocket** | Remote code exec from malicious peer | 127.0.0.1 bind by default; token auth for network bind; strict JSON-schema validation; rate limit; CSP + SRI |
| **R-L-6: File-watcher perf on 1000-task repo** | UI lag; missed updates | `watchdog` with 200ms debounce; batch re-sync; threshold warning at 500 tasks |
| **R-L-7: Work Log bloat → token pollution** | Task file > 10k tokens over months | MCP `_board` returns only last 5 log lines; `cos task-archive` moves >30d-complete tasks to archive; `lint-task.sh` blocks > 3k tokens |
| **R-L-8: Perfectionism loophole (icebox grows unbounded)** | User creates 500 icebox items, ignores them | `cos retro` flags icebox > 50; `cos board` header shows icebox count red if > 100 |
| **R-L-9: Solo-dev adherence drift** | Tool exists, user stops using it | `remind-daily.sh` fires on SessionStart after 24h idle; `cos daily` shows streak; NOT gamification — transparent observability |
| **R-L-10: Migration version conflicts** | Audited 2026-04-19: db.py is at v12 (Phase I.0 shipped). Phase L uses **v13**. NOT v8 — that's already `_migrate_v8_validation_throttle`. | First action of L.0 is `grep _migrate_v core/thinking_os/db.py` to confirm next free version; append-only (Rule 10); `block-migration-conflict.sh` hook catches duplicates |
| **R-L-11: Auto-commit breaks user's git hooks** | Commit stuck; confusing UX | No auto-commit by default; drag-drop leaves changes uncommitted; user commits explicitly |
| **R-L-12: Swimlane mismatch between repos** | Task created in wrong swimlane | `validate-task-frontmatter.sh` checks config; clear error listing valid swimlanes |
| **R-L-13: Agent confusion on multi-session handoff** | Repeats prior work or misses state | Work Log last-5 shown via MCP; `cos_task_daily` summary on session start; `task-current` marker |
| **R-L-14: WebSocket disconnect mid-drag** | State ambiguous | Server SSOT; optimistic UI; refetch on reconnect; write-back only confirmed after server ACK |
| **R-L-15: Token budget violated in `_board`** | Agent context blown on large boards | Hard 8k cap; default excludes `complete/archive`; cursor pagination |
| **R-L-16: Daily/Retro accumulates crud files** | `docs/retros/*.md` grows forever | `cos retro --ephemeral` (default) prints only; `--persist` opt-in saves file |
| **R-L-17: New status enum breaks downstream consumers** | External tools that read `docs/tasks.md` fail | Status index file regenerated in old 4-status form for backward compatibility; frontmatter is the new truth |
| **R-L-18: Hook ordering bug (`enforce-wip` vs. `enforce-task-start`)** | Inconsistent blocks | `registry.yaml` declares explicit `order:` field; integration tests cover permutations |
| **R-L-19: Migration destroys user-edited legacy content** | Custom sections lost | Migration archives originals verbatim to `docs/tasks/archive/pre-l/`; revertible via git |
| **R-L-20: `cos task-pick` biases toward recent observations only** | Ignores overall priority | Ranking algorithm 70% priority + 20% dependencies + 10% session-context; weights in config |
| **R-L-21: Agent creates too many tasks via `cos_task_create`** | Icebox explodes during exploratory session | Per-session cap (default 5 new tasks/session, override via flag); exceeds → warns + requires human confirmation |
| **R-L-22: Persian/RTL title breaks frontmatter YAML parsing** | YAML treats UTF-8 fine but display is inconsistent | Test fixture with Persian titles in L.0; parser uses UTF-8 strict mode; viewer auto-detects dir via `dir="auto"` |
| **R-L-23: Agent confuses `kind` vs `labels` vs `epic`** | Inconsistent tagging across repos; filter queries break | `validate-task-frontmatter.sh` enforces: `kind` ∈ enum; `labels` ∩ enum = ∅ (labels can't contain kind values); AGENTS.md "Tagging Taxonomy" section gives concrete mapping examples |
| **R-L-24: Template drift between master + scaffold copy** | `templates/_base/task-detail.template.md` and `templates/_base/scaffold/docs/governance/templates/task-detail.md` diverge over time | L.0 ships them identical; CI test (`tests/test_template_parity.py`) asserts byte-equality (modulo allowed header-comment differences); `warn-template-drift.sh` hook exists from Phase E and applies here too |
| **R-L-25: AGENTS.md fragment composition order wrong** | "Task Authoring" section appears before "Identity" or rule sections, confusing the agent | `templates/_base/base.yaml::agents_md_sections` is the SSOT for ordering; new fragment registered at index ~12 (after rules, before subagent-dispatch); `cos doctor` C24 verifies composition produces a parsable AGENTS.md with all expected sections in order |
| **R-L-26: Codex sessions miss Work Log auto-capture** | PostToolUse hooks not delivered → no work log entries → next session blind | Two-track design: (a) Claude path = `capture-work-log.sh` PostToolUse (default); (b) Codex path = explicit MCP tool `cos_work_log_append(task_id, summary)` that the AGENTS.md fragment instructs Codex to call after significant edits + a polling fallback (`cos_work_log_append --auto-from-git-diff` runs at session-end) |
| **R-L-27: Migration partially fails (file 25/50 corrupt)** | Half-migrated repo, can't tell which is which | Two-phase atomic commit: (1) parse all 50 to temp dir; if any fails → abort, no writes; (2) atomic rename of all temp → final paths; (3) tar.gz backup BEFORE phase 1; CLI shows "validated 50/50, applying..." progress |
| **R-L-28: MCP server unavailable mid-session** | Agent calls `cos_task_move`, gets connection error, doesn't know what to do | Tool envelopes return `fail("transient", retryable=True)` per Rule 14; AGENTS.md fragment instructs: retry once after 2s; on second failure, fallback to direct MD frontmatter edit via Edit tool (validate-task-frontmatter.sh hook still runs at file-system layer, so safety preserved); subsequent `cos doctor` reports the inconsistency on next reachable MCP |
| **R-L-29: Dependency cycle in `depends_on`** | TASK-A → TASK-B → TASK-A → infinite loop in dependency walks; `cos_task_pick` hangs | `validate-task-frontmatter.sh` runs DFS walk on the dependency graph after every Write/Edit to `docs/tasks/*.md`; rejects any edit that would introduce a cycle, with clear error showing the cycle path |
| **R-L-30: Stale `in_progress` vs legitimate long task** | C21 fires false alarms on legitimately long tasks (e.g. 6-week Shape Up bet) | C21 refined: stale = (no Work Log append in > 3 days) **OR** (elapsed > 2× `appetite`); a 6-week task with `appetite: 6w` and weekly Work Log entries does NOT trigger; one with `appetite: 1d` and zero entries for 3 days does |

---

## 21. Ship Checklist (per slice + phase)

Each slice:
- [ ] Code + tests in `core/board-os/` (Rule 13 function-header convention)
- [ ] Envelope compliance (Rule 14) on MCP tools
- [ ] `make verify` green
- [ ] `uv run pytest core/board-os/tests/ -q` green
- [ ] Hook registration in `registry.yaml`; `make regen-adapter-templates` clean
- [ ] Docs-lint green
- [ ] Scale check on `coding-os` repo itself

Phase L done when:
- [ ] All 10 slices (L.0 – L.9) shipped
- [ ] Agent can run full lifecycle (create → pick → start → work log → testing → complete) via MCP alone, no CLI
- [ ] User can run full lifecycle via web viewer alone, no MCP
- [ ] `cos daily` and `cos retro` functional with persisted history
- [ ] Rule 15 enforced (`lint-task.sh` blocks task files > 3k tokens)
- [ ] `coding-os` repo dogfooding: all Phase I slices tracked as TASK files
- [ ] Token cost baseline measured (pre-K: ~18k startup; post-L: target ~11k)
- [ ] 1,300+ tests passing (current 1,083 + ~140 + Phase I's ~120)
- [ ] `cos doctor` C20–C23 all green
- [ ] Migration round-trip on legacy fixture works (50 tasks, zero content loss)
- [ ] CLAUDE.md + AGENTS.md "Scrumban Workflow" + "Task Editing" + Rule 15 sections land

---

## 22. Design Decisions (finalized 2026-04-19)

1. **SSOT location** — ✅ Markdown in git. Non-negotiable for diff/PR/offline/auditability.
2. **Cache location** — ✅ SQLite, extending the existing `tasks` table via migration v13.
3. **Status enum** — ✅ 8 values (icebox, ready, emergency, in_progress, testing, complete, blocked, archive); legacy 4 statuses aliased on read.
4. **WIP cap defaults** — ✅ in_progress=1, testing=3, emergency=2. Configurable per-project.
5. **Swimlane config** — ✅ Per-project `.coding-os/scrumban-config.yaml`. coding-os itself: core / thinking-os / graph-os / adapters / templates / cli / docs / infra.
6. **Appetite (not hours)** — ✅ Shape Up-style; regex `\d+[mhdwcy]|\d+cy`.
7. **Work Log ownership** — ✅ Agent appends via `capture-work-log.sh` (automatic); human edits via Edit tool (validated).
8. **Frontmatter vs body** — ✅ Frontmatter = machine state (status, swimlane, priority, ...); body = human-first content (outcome, Read First, acceptance, work log).
9. **Index file `docs/tasks.md`** — ✅ Demoted to *generated*; frontmatter becomes authoritative.
10. **Web viewer stack** — ✅ Sortable.js + vanilla JS + aiohttp + watchdog. Zero build pipeline. `--bundled` offline mode.
11. **Auto-commit on drag-drop** — ✅ No. Drag updates MD; user commits explicitly.
12. **Multi-agent safety** — ✅ `flock` serialization in hooks; `task_status_history` uniqueness constraint; fail-soft on lock contention.
13. **Rule 15 enforcement** — ✅ PostToolUse `lint-task.sh` blocks > 3k tokens; warns > 1.5k.
14. **Daily & Retro** — ✅ First-class CLI + MCP; `--ephemeral` default (no file); `--persist` opt-in.
15. **Migration** — ✅ `cos task-migrate --dry-run` → `--apply`; originals archived to `docs/tasks/archive/pre-l/`; idempotent.
16. **`cos_task_create` as MCP tool** — ✅ Agent must be able to spawn new tasks during exploratory work without leaving the session. Per-session rate limit (default 5) prevents icebox explosion.
17. **Priority vs Emergency are orthogonal** — ✅ Priority is ranking (P0-P3, static); Emergency is a column (dynamic, "now"). `cos_task_pick` sorts emergency first.
18. **Definition of Done = Acceptance (G/W/T)** — ✅ Not two concepts. When the G/W/T passes, task is Done. Scope-creep goes to a new task via `cos_task_create`.
19. **RTL / Persian support** — ✅ `dir="auto"` per card; UTF-8 strict in parser; fixtures include Persian titles.
20. **Board viewer separate from graph viewer** — ✅ Two HTML files, two CLIs (`cos board --web` vs `cos graph-viz`). Possible future unification but out of scope for Phase L.
21. **Default scrumban-config per stack** — ✅ Ships in `templates/<stack>/scaffold/.coding-os/scrumban-config.yaml`. Django: backend/frontend/ai-service. NextJS: frontend/api/e2e. coding-os: 8-lane set.
22. **Four separate categorization axes** — ✅ `swimlane` (domain, config-enum), `kind` (type, 8-value enum), `epic` (initiative, optional free string), `labels` (free tags). Mixing them is explicitly a bug (§6.1.1). `kind` is closed-enum so card colour is stable across all repos — a red card is ALWAYS a bug. `epic` enables Phase/Release/Theme grouping without polluting swimlane or labels.
23. **Template + agent guidance distribution is explicit** — ✅ §24 maps each of the 5 artifacts (master template, scaffold template, scrumban-config, AGENTS.md fragment, skill) to its file path AND its slice. L.0 ships the templates + config; L.9 ships the fragment + skill. Per-stack variation = `scrumban-config.yaml::swimlanes` only — body template + frontmatter schema + skill are universal. Master + scaffold templates kept in byte-parity by CI test (R-L-24).
24. **Codex Work Log path** — ✅ Two-track: PostToolUse `capture-work-log.sh` for Claude (default); explicit `cos_work_log_append` MCP tool for Codex (instructed by AGENTS.md fragment); polling fallback `--auto-from-git-diff` at session-end as belt-and-suspenders.
25. **Migration is two-phase atomic** — ✅ §16.2: backup → validate-all-to-staging → atomic-rename-all → commit. No half-migrated states. Resumable.
26. **Dependency cycles rejected at write-time** — ✅ `validate-task-frontmatter.sh` does DFS walk on every Write/Edit; cycle path shown in error.
27. **Stale detection respects appetite** — ✅ C21 logic: stale = no-Work-Log > 3d OR elapsed > 2× appetite. 6-week Shape Up bets with weekly logs do not false-fire.
28. **MCP outage has explicit fallback** — ✅ Tools return `transient/retryable=true`; agent retries once after 2s; second failure → fallback to direct MD edit (frontmatter validator hook still runs at FS layer); `cos doctor` reports drift on next reachable MCP.
29. **Optimistic concurrency for transitions** — ✅ `workflow.transition()` reads current status pre-write; if changed → `transient/retryable`; uniqueness index on `(task_id, transitioned_at@100ms)` as backstop.
30. **Daily streak is observability not shame** — ✅ Fragment instructs agent: NEVER use streak data to pressure user; show only when user asks; ADHD-friendly default.

---

## 23. Why Phase L, Not Embedded in Phase I

- **Scope distinctness.** Phase I builds the structural graph engine. Phase L builds the temporal task engine. Shared SQLite file, entirely different cognitive axis.
- **Dependency order.** Phase L's `task:file` node enrichment (§13) depends on graph-os taxonomy from I.0–I.3. Ship I first, K extends.
- **Testability.** Each phase ~1000+ tests. Combining them would create a 200-test PR that nobody can review.
- **Risk isolation.** A rollback of Phase L does not touch graph-os; a rollback of Phase I does not touch the task board.
- **Dogfood order.** Once graph-os is live, Phase L uses it to track its own slices (meta-dogfood) — `docs/tasks/TASK-L-0-migration-v13.md` becomes the first consumer.

---

## 24. Template & Agent Guidance Distribution — Where Each Artifact Lives

The previous version of this plan was ambiguous about where the new lean template files land and which slice ships them. This section is the SSOT.

### 24.1 The five artifacts that teach the agent how to write tasks

| # | Artifact | Path | Ships in slice | Audience |
|---|---|---|---|---|
| 1 | **Master lean template** | `templates/_base/task-detail.template.md` | **L.0** | Internal — used by `cos task-create` to generate task files in *this* repo |
| 2 | **Scaffolded lean template** | `templates/_base/scaffold/docs/governance/templates/task-detail.md` | **L.0** | Consumer projects — copied by `cos init` into `<project>/docs/governance/templates/task-detail.md` |
| 3 | **Default scrumban-config** | `templates/_base/scaffold/.coding-os/scrumban-config.yaml` + per-stack overrides at `templates/<stack>/scaffold/.coding-os/scrumban-config.yaml` | **L.0** | Consumer projects — defines swimlanes/WIP/labels per stack |
| 4 | **AGENTS.md fragment** | `templates/_base/fragments/task-authoring.md.tmpl` (registered in `templates/_base/base.yaml::agents_md_sections`) | **L.9** | Always-loaded agent context — explains the 4 axes, Rule 15, when to use which MCP tool, **MCP outage retry policy** (R-L-28), **Codex must call `cos_work_log_append` explicitly** (R-L-26), **surface stale-task warnings to the human** (G-ι), **Daily streak is observability NOT shame** (G-κ) |
| 5 | **Skill** | `core/skills/task-driver/SKILL.md` | **L.9** | On-demand agent context — full philosophy + examples, triggered when agent touches `docs/tasks/*.md` |

### 24.2 Per-stack: what differs, what doesn't

| Aspect | Per-stack? | Why |
|---|---|---|
| Lean task template body | ❌ No | Outcome / Acceptance / Read First / Work Log are universal — same for django, nextjs, go-fiber. Stack-specific verification commands belong in `core/rules/` already. |
| Frontmatter schema (kind/priority/appetite enums) | ❌ No | Same closed enums everywhere — guarantees colour stability across all repos (a red card is always a bug). |
| `scrumban-config.yaml::swimlanes` | ✅ **Yes** | django=backend/frontend/ai-service; nextjs=frontend/api/e2e; go-fiber=handlers/middleware/db; coding-os=core/thinking_os/graph-os/... |
| `scrumban-config.yaml::wip_limits` | ⚠️ Override-able | Default 1/3/2 (in_progress/testing/emergency); team can raise testing cap for parallel review. |
| `scrumban-config.yaml::label_families` | ⚠️ Override-able | Default 8-colour palette; team can add custom families with custom colours (still stable per-project). |
| Skill `task-driver` | ❌ No | Same skill, same philosophy — universal. |
| AGENTS.md fragment | ❌ No | Same fragment composes into every project's AGENTS.md via `base.yaml::agents_md_sections`. |

**Rule of thumb:** *what* a task looks like = universal. *Where* it goes (which swimlane) = per-stack.

### 24.3 Composition order — how the agent sees this

```
session start
   │
   ▼
[CLAUDE.md / AGENTS.md loads] ────► §"Task Authoring" fragment is here
                                    (composed at cos init time from the .tmpl)
   │
   ▼
agent receives: "create task for X"
   │
   ▼
[skill task-driver auto-triggered by description match]
   │
   ▼
agent calls cos_task_create(...)
   │
   ▼
[server reads templates/_base/task-detail.template.md OR
 the consumer's docs/governance/templates/task-detail.md]
   │
   ▼
template rendered with frontmatter + Outcome placeholder + AGENT: comments
   │
   ▼
file written → validate-task-frontmatter.sh hook → DB sync → board update
```

Five-layer defense:
1. AGENTS.md fragment (ambient context)
2. Skill `task-driver` (on-demand deeper context)
3. `cos_task_create` MCP tool (preferred path — no manual YAML)
4. Template inline `<!-- AGENT: ... -->` comments (fallback when editing manually)
5. Validation hooks (`validate-task-frontmatter.sh` + `lint-task.sh`) — the safety net

If layers 1-4 are bypassed, layer 5 still rejects malformed tasks at the file system boundary. **The agent cannot ship a broken task even if it ignores all guidance.**

### 24.4 What gets DELETED from the old templates

When L.0 ships:
- `templates/_base/task-detail.template.md` — **fully rewritten** (old 12-section format archived under git history). Master template.
- `templates/_base/scaffold/docs/governance/templates/task-detail.md` — **fully rewritten** to match.
- `templates/_base/scaffold/docs/governance/templates/task-list.md` — **kept** but updated header to note "this file is now generated; do not hand-edit; see frontmatter SSOT in individual task files."

When L.7 (migration) runs in a consumer project:
- Existing `docs/tasks/TASK-NNN.md` files → migrated in place; originals → `docs/tasks/archive/pre-l/TASK-NNN.md`.
- Existing `docs/governance/templates/task-detail.md` (already-scaffolded copy in consumer) → updated by `cos update` (or rewritten on next `cos init`); old copy archived to `.coding-os/template-backup/<date>/`.

### 24.5 Manifest registration

After editing template files in L.0, MUST run:
```
make manifest-regen        # updates core/scaffold_manifest.json
make regen-rules           # if scrumban-config.yaml affects rules (e.g. swimlane registry)
```

The `regen-reminder.sh` hook (Phase E) will already nag if you forget. Tested in L.0 ship gate.

---

## 25. Why `cos-board` (Module Naming)

- Parallel to `graph-os`, `thinking-os`. Three cognitive subsystems.
- "Board" is the visible metaphor (Silicon Valley whiteboard) — every user touches the board, not the `task_sync` or `workflow` internals.
- Short; matches CLI first command: `cos board`.
- Python package: `board_os.*`.
- MCP prefix stays `cos_task_*` (backward compatible with Phase C tools).

**Alternatives rejected:**
- `task-os` — too bureaucratic, less visual.
- `scrumban-os` — hyper-specific to methodology; if we later support Shape Up or Basecamp cycles, the name ages badly.
- `kanban` — missing the "scrum" half (cycles, planning, retro).

Decision: **`board-os`** (module), **`cos board`** (CLI), **Scrumban** (methodology in docs).
